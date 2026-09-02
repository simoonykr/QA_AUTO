[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$envPath = Join-Path $projectRoot ".env.public"
$fixturePath = Join-Path $projectRoot "backend\tests\temporary_staging_single_tc.txt"

$values = @{}
foreach ($line in [IO.File]::ReadAllLines($envPath)) {
    if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
    $key, $value = $line -split '=', 2
    $values[$key.Trim()] = $value.Trim()
}

function Invoke-Api {
    param([string]$Method, [string]$Path, $Body = $null, [hashtable]$Headers = @{})
    $parameters = @{
        Uri = "$BaseUrl$Path"
        Method = $Method
        WebSession = $script:session
        Headers = $Headers
        SkipHttpErrorCheck = $true
    }
    if ($null -ne $Body) {
        $parameters.ContentType = "application/json"
        $parameters.Body = $Body | ConvertTo-Json -Depth 20 -Compress
    }
    Write-Host "API $Method $Path"
    $response = Invoke-WebRequest @parameters
    $json = if ($response.Content) { $response.Content | ConvertFrom-Json } else { $null }
    return [pscustomobject]@{ Status = [int]$response.StatusCode; Body = $json }
}

function Wait-Execution {
    param([string]$ExecutionId)
    $terminal = @("PASS", "FAIL", "BLOCKED", "NEEDS_REVIEW", "CANCELLED", "SYSTEM_ERROR")
    for ($index = 0; $index -lt 60; $index++) {
        $response = Invoke-Api GET "/api/v1/executions/$ExecutionId"
        if ($terminal -contains $response.Body.status) { return $response.Body }
        Start-Sleep -Seconds 1
    }
    throw "Execution $ExecutionId did not finish in 60 seconds."
}

$script:session = [Microsoft.PowerShell.Commands.WebRequestSession]::new()
$health = Invoke-WebRequest -Uri "$BaseUrl/health" -SkipHttpErrorCheck
$unauthorized = Invoke-WebRequest -Uri "$BaseUrl/api/v1/environments" -SkipHttpErrorCheck
$login = Invoke-Api POST "/api/v1/auth/login" @{
    username = $values["DEMO_AUTH_USERNAME"]
    password = $values["DEMO_AUTH_PASSWORD"]
}
if ($login.Status -ne 200) { throw "Demo login failed: HTTP $($login.Status)" }

$importResponse = Invoke-RestMethod -Uri "$BaseUrl/api/v1/test-cases/import" -Method Post -WebSession $script:session -Form @{
    file = Get-Item -LiteralPath $fixturePath
}
$environments = (Invoke-Api GET "/api/v1/environments").Body
$accounts = (Invoke-Api GET "/api/v1/test-accounts").Body
$environment = $environments | Where-Object { $_.baseUrl -match 'demo-target' } | Select-Object -First 1
if (-not $environment) { $environment = $environments | Select-Object -First 1 }
$account = $accounts | Where-Object { $_.status -eq "ACTIVE" } | Select-Object -First 1
if (-not $account) { $account = $accounts | Select-Object -First 1 }
if (-not $environment -or -not $account) { throw "Environment or test account is missing." }

$structured = (Invoke-Api POST "/api/v1/test-case-versions/current/structure" @{
    title = "Temporary Staging imported TC"
    rawText = $importResponse.rawText
}).Body
$planBeforeApproval = (Invoke-Api GET "/api/v1/test-case-versions/$($structured.versionId)/execution-plan?environmentId=$($environment.id)").Body
$approval = Invoke-Api POST "/api/v1/test-case-versions/$($structured.versionId)/approve"
if ($approval.Status -ne 200) { throw "Approval failed: HTTP $($approval.Status)"
}
$plan = (Invoke-Api GET "/api/v1/test-case-versions/$($structured.versionId)/execution-plan?environmentId=$($environment.id)").Body
if (-not $plan.executable) { throw "Approved plan is not executable."
}

$executionRequest = @{
    testCaseVersionId = $structured.versionId
    environmentId = $environment.id
    browser = "Chromium"
    accountId = $account.id
    viewport = "1440x900"
    locale = "ko-KR"
    limits = @{ timeoutMinutes = 5; maxAiCalls = 0; retryCount = 0 }
    requireRiskApproval = $true
}
$created = Invoke-Api POST "/api/v1/executions" $executionRequest @{ "Idempotency-Key" = [guid]::NewGuid().ToString() }
if ($created.Status -ne 202) { throw "Execution creation failed: HTTP $($created.Status), code=$($created.Body.code), message=$($created.Body.message)" }
$success = Wait-Execution $created.Body.id
$successDetails = (Invoke-Api GET "/api/v1/executions/$($created.Body.id)/details").Body

$failureStructured = (Invoke-Api POST "/api/v1/test-case-versions/current/structure" @{
    title = "Temporary Staging intentional failure"
    rawText = "navigate 접속`n[data-testid=`"email`"] 입력 `"qa@example.test`"`n[data-testid=`"login`"] 클릭`n[data-testid=`"welcome`"] 문구 `"의도적으로 존재하지 않는 값`" 확인"
}).Body
$failureApproval = Invoke-Api POST "/api/v1/test-case-versions/$($failureStructured.versionId)/approve"
if ($failureApproval.Status -ne 200) { throw "Failure plan approval failed: HTTP $($failureApproval.Status)" }
$failureCreated = Invoke-Api POST "/api/v1/executions" (@{
    testCaseVersionId = $failureStructured.versionId
    environmentId = $environment.id
    browser = "Chromium"
    accountId = $account.id
    viewport = "1440x900"
    locale = "ko-KR"
    limits = @{ timeoutMinutes = 5; maxAiCalls = 0; retryCount = 0 }
    requireRiskApproval = $true
}) @{ "Idempotency-Key" = [guid]::NewGuid().ToString() }
if ($failureCreated.Status -ne 202) { throw "Failure execution creation failed: HTTP $($failureCreated.Status), code=$($failureCreated.Body.code), message=$($failureCreated.Body.message)" }
$failure = Wait-Execution $failureCreated.Body.id
$failureDetails = (Invoke-Api GET "/api/v1/executions/$($failureCreated.Body.id)/details").Body
$artifactCheck = $null
if ($failureDetails.artifacts.Count -gt 0) {
    $artifact = $failureDetails.artifacts[0]
    $artifactResponse = Invoke-WebRequest -Uri "$BaseUrl/api/v1/executions/$($failureCreated.Body.id)/artifacts/$($artifact.id)" -WebSession $script:session
    $signature = [Convert]::ToHexString($artifactResponse.Content[0..7])
    $artifactCheck = @{ id = $artifact.id; type = $artifact.type; sizeBytes = $artifact.sizeBytes; pngSignature = $signature }
}

$editableStructured = (Invoke-Api POST "/api/v1/test-case-versions/current/structure" @{
    title = "Temporary Staging editable plan"
    rawText = "navigate 접속`n#email 입력`n#submit 클릭`n#welcome 문구 `"환영합니다`" 확인"
}).Body
$editablePlanBefore = (Invoke-Api GET "/api/v1/test-case-versions/$($editableStructured.versionId)/execution-plan?environmentId=$($environment.id)").Body
$editablePlanAfter = (Invoke-Api PATCH "/api/v1/test-case-versions/$($editableStructured.versionId)/steps/step-2?environmentId=$($environment.id)" @{
    selector = '[data-testid="email"]'
    value = "qa@example.test"
}).Body
$editableApproval = Invoke-Api POST "/api/v1/test-case-versions/$($editableStructured.versionId)/approve"
$approvedDelete = Invoke-Api DELETE "/api/v1/test-case-versions/$($editableStructured.versionId)/steps/step-2?environmentId=$($environment.id)"

$deletableStructured = (Invoke-Api POST "/api/v1/test-case-versions/current/structure" @{
    title = "Temporary Staging deletable plan"
    rawText = $importResponse.rawText
}).Body
$deletablePlanBefore = (Invoke-Api GET "/api/v1/test-case-versions/$($deletableStructured.versionId)/execution-plan?environmentId=$($environment.id)").Body
$deletablePlanAfter = (Invoke-Api DELETE "/api/v1/test-case-versions/$($deletableStructured.versionId)/steps/step-2?environmentId=$($environment.id)").Body
$emptyPlan = $deletablePlanAfter
foreach ($remainingStepId in @("step-1", "step-3", "step-4")) {
    $emptyPlan = (Invoke-Api DELETE "/api/v1/test-case-versions/$($deletableStructured.versionId)/steps/${remainingStepId}?environmentId=$($environment.id)").Body
}

$invalidStructured = (Invoke-Api POST "/api/v1/test-case-versions/current/structure" @{
    title = "Temporary Staging invalid plan"
    rawText = "navigate 접속`n#email 입력`n#submit 클릭`n#welcome 문구 `"환영합니다`" 확인"
}).Body
$invalidPlan = (Invoke-Api GET "/api/v1/test-case-versions/$($invalidStructured.versionId)/execution-plan?environmentId=$($environment.id)").Body
$invalidApproval = Invoke-Api POST "/api/v1/test-case-versions/$($invalidStructured.versionId)/approve"

if ($success.status -ne "PASS") { throw "Success execution did not pass: $($success.status)" }
if ($successDetails.plan.testCaseVersionId -ne $structured.versionId -or
    $successDetails.plan.planHash -ne $plan.planHash -or
    $successDetails.plan.plannedStepCount -ne $plan.steps.Count -or
    -not $successDetails.plan.stepCountMatches) {
    throw "Execution plan snapshot does not match the actual execution."
}
if (@($successDetails.steps | Where-Object { -not $_.planStepId }).Count -gt 0) {
    throw "An actual step is missing planStepId."
}
if ($failure.status -ne "FAIL" -or $failureDetails.errorCode -ne "ASSERTION_FAILED" -or -not $artifactCheck) {
    throw "Intentional failure evidence validation failed."
}
if ($editablePlanBefore.executable -or
    $editablePlanAfter.revision -ne ($editablePlanBefore.revision + 1) -or
    -not $editablePlanAfter.executable -or
    -not $editablePlanAfter.planHash -or
    $editableApproval.Status -ne 200 -or $approvedDelete.Status -ne 409 -or
    $approvedDelete.Body.code -ne "TC_VERSION_NOT_REVIEWABLE") {
    throw "Editable plan PATCH validation failed."
}
if ($deletablePlanAfter.revision -ne ($deletablePlanBefore.revision + 1) -or
    $deletablePlanAfter.steps.Count -ne ($deletablePlanBefore.steps.Count - 1) -or
    $deletablePlanAfter.planHash -eq $deletablePlanBefore.planHash -or
    ($deletablePlanAfter.steps.stepNo -join ',') -ne '1,2,3' -or
    $emptyPlan.steps.Count -ne 0 -or $emptyPlan.executable -or $emptyPlan.warnings.Count -eq 0) {
    throw "Plan step DELETE validation failed."
}
if ($invalidPlan.executable -or $invalidApproval.Status -ne 422) {
    throw "Invalid plan was not blocked."
}

[ordered]@{
    baseUrl = $BaseUrl
    healthStatus = [int]$health.StatusCode
    unauthorizedStatus = [int]$unauthorized.StatusCode
    loginStatus = $login.Status
    imported = @{ fileName = $importResponse.fileName; format = $importResponse.format; rawTextLength = $importResponse.rawText.Length }
    environmentId = $environment.id
    success = @{
        versionId = $structured.versionId
        source = $structured.aiUsage.source
        aiCallCount = $structured.aiUsage.callCount
        aiCostUsd = $structured.aiUsage.costUsd
        statusBeforeApproval = $planBeforeApproval.status
        executable = $plan.executable
        planHash = $plan.planHash
        revision = $plan.revision
        planSteps = $plan.steps
        executionId = $created.Body.id
        executionStatus = $success.status
        detailsPlan = $successDetails.plan
        actualSteps = $successDetails.steps
    }
    failure = @{
        versionId = $failureStructured.versionId
        source = $failureStructured.aiUsage.source
        aiCallCount = $failureStructured.aiUsage.callCount
        aiCostUsd = $failureStructured.aiUsage.costUsd
        executionId = $failureCreated.Body.id
        executionStatus = $failure.status
        errorCode = $failureDetails.errorCode
        failedSteps = @($failureDetails.steps | Where-Object status -eq "FAIL")
        artifact = $artifactCheck
    }
    editable = @{
        versionId = $editableStructured.versionId
        executableBefore = $editablePlanBefore.executable
        revisionBefore = $editablePlanBefore.revision
        missingFieldsBefore = $editablePlanBefore.warnings[0].missingFields
        executableAfter = $editablePlanAfter.executable
        revisionAfter = $editablePlanAfter.revision
        planHashAfter = $editablePlanAfter.planHash
        approvalStatus = $editableApproval.Status
        approvedDeleteStatus = $approvedDelete.Status
        approvedDeleteError = $approvedDelete.Body.code
    }
    deleted = @{
        versionId = $deletableStructured.versionId
        revisionBefore = $deletablePlanBefore.revision
        revisionAfter = $deletablePlanAfter.revision
        planHashBefore = $deletablePlanBefore.planHash
        planHashAfter = $deletablePlanAfter.planHash
        remainingStepNumbers = $deletablePlanAfter.steps.stepNo
        emptyRevision = $emptyPlan.revision
        emptyExecutable = $emptyPlan.executable
        emptyWarning = $emptyPlan.warnings[0].code
    }
    invalid = @{
        versionId = $invalidStructured.versionId
        executable = $invalidPlan.executable
        warnings = $invalidPlan.warnings
        approvalStatus = $invalidApproval.Status
        approvalError = $invalidApproval.Body.code
    }
} | ConvertTo-Json -Depth 20
