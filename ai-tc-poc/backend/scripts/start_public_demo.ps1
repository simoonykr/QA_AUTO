[CmdletBinding()]
param(
    [ValidateSet("up", "config")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$envPath = Join-Path $projectRoot ".env.public"
$composePath = Join-Path $projectRoot "compose.public-demo.yml"
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$docker = if ($dockerCommand) { $dockerCommand.Source } else { "C:\Program Files\Docker\Docker\resources\bin\docker.exe" }
if (-not (Test-Path -LiteralPath $docker)) { throw "Docker CLI를 찾지 못했습니다." }

if (-not (Test-Path -LiteralPath $envPath)) {
    throw ".env.public 파일이 없습니다. .env.public.example을 복사하고 로컬 비밀값을 입력하세요."
}

$values = @{}
foreach ($line in [IO.File]::ReadAllLines($envPath)) {
    if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
    $key, $value = $line -split '=', 2
    $values[$key.Trim()] = $value.Trim()
}

$required = @("POSTGRES_PASSWORD", "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "DEMO_AUTH_USERNAME", "DEMO_AUTH_PASSWORD", "DEMO_SESSION_SECRET")
$invalid = @($required | Where-Object {
    -not $values.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($values[$_]) -or $values[$_] -like "replace-with-*"
})
if ($invalid.Count -gt 0) {
    throw "Compose를 시작하지 않았습니다. .env.public 필수값을 복구하세요: $($invalid -join ', ')"
}
if ($values["DEMO_SESSION_SECRET"].Length -lt 32) {
    throw "Compose를 시작하지 않았습니다. DEMO_SESSION_SECRET은 32자 이상이어야 합니다."
}
if ($values["AI_ENABLED"] -eq "true") {
    $aiRequired = @("OPENAI_API_KEY", "AI_MAX_CALLS_PER_RUN", "AI_DAILY_BUDGET_USD")
    $aiInvalid = @($aiRequired | Where-Object { -not $values.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($values[$_]) })
    if ($aiInvalid.Count -gt 0 -or $values["AI_MAX_CALLS_PER_RUN"] -ne "1") {
        throw "AI가 활성화된 경우 키·예산과 AI_MAX_CALLS_PER_RUN=1이 필요합니다."
    }
}

& $docker compose --env-file $envPath -f $composePath config --quiet
if ($LASTEXITCODE -ne 0) { throw "Docker Compose 설정 검증에 실패했습니다." }
if ($Action -eq "up") {
    & $docker compose --env-file $envPath -f $composePath up --build -d
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose 시작에 실패했습니다." }
}
Write-Host "비밀값 사전 검증과 Compose $Action 작업이 완료되었습니다."
