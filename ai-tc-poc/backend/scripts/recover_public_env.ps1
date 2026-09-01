[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$envPath = Join-Path $projectRoot ".env.public"
$composePath = Join-Path $projectRoot "compose.public-demo.yml"
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$docker = if ($dockerCommand) { $dockerCommand.Source } else { "C:\Program Files\Docker\Docker\resources\bin\docker.exe" }
if (-not (Test-Path -LiteralPath $docker)) { throw "Docker CLI를 찾지 못했습니다." }
if (-not (Test-Path -LiteralPath $envPath)) { throw ".env.public 파일이 없습니다." }

function Get-ServiceEnvironment([string]$service) {
    $projectName = Split-Path $projectRoot -Leaf
    $containerId = @(& $docker ps --filter "label=com.docker.compose.project=$projectName" --filter "label=com.docker.compose.service=$service" --format '{{.ID}}') | Select-Object -First 1
    $containerId = "$containerId".Trim()
    if (-not $containerId) { throw "$service 컨테이너가 실행 중이 아니어서 비밀값을 복구할 수 없습니다." }
    $result = @{}
    foreach ($entry in (& $docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' $containerId)) {
        if ($entry -notmatch '=') { continue }
        $key, $value = $entry -split '=', 2
        $result[$key] = $value
    }
    return $result
}

$postgres = Get-ServiceEnvironment "postgres"
$minio = Get-ServiceEnvironment "minio"
$api = Get-ServiceEnvironment "api"
$recovered = @{
    "POSTGRES_PASSWORD" = $postgres["POSTGRES_PASSWORD"]
    "MINIO_ROOT_USER" = $minio["MINIO_ROOT_USER"]
    "MINIO_ROOT_PASSWORD" = $minio["MINIO_ROOT_PASSWORD"]
    "DEMO_AUTH_USERNAME" = $api["DEMO_AUTH_USERNAME"]
    "DEMO_AUTH_PASSWORD" = $api["DEMO_AUTH_PASSWORD"]
    "DEMO_SESSION_SECRET" = $api["DEMO_SESSION_SECRET"]
}
if (@($recovered.GetEnumerator() | Where-Object { [string]::IsNullOrWhiteSpace($_.Value) }).Count -gt 0) {
    throw "실행 중인 컨테이너에 필요한 비밀값이 모두 존재하지 않습니다."
}

$lines = [Collections.Generic.List[string]]::new()
$seen = @{}
foreach ($line in [IO.File]::ReadAllLines($envPath)) {
    if ($line -match '^([^#=\s]+)=(.*)$' -and $recovered.ContainsKey($Matches[1])) {
        $key = $Matches[1]
        $lines.Add("$key=$($recovered[$key])")
        $seen[$key] = $true
    } else {
        $lines.Add($line)
    }
}
foreach ($key in $recovered.Keys) {
    if (-not $seen.ContainsKey($key)) { $lines.Add("$key=$($recovered[$key])") }
}
$tempPath = "$envPath.tmp"
[IO.File]::WriteAllLines($tempPath, $lines, [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $tempPath -Destination $envPath -Force
Write-Host ".env.public 필수 비밀값 6개를 실행 중인 컨테이너에서 복구했습니다. 값은 출력하지 않았습니다."
