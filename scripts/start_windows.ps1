param(
    [switch]$Build,
    [switch]$Open
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

$ImageName = "finally"
$ContainerName = "finally"
$VolumeName = "finally-data"
$Port = 8000

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is not installed or not in PATH."
    exit 1
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker daemon is not running. Please start Docker Desktop and try again."
    exit 1
}

$imageExists = $true
docker image inspect $ImageName *> $null
if ($LASTEXITCODE -ne 0) {
    $imageExists = $false
}

if ($Build -or -not $imageExists) {
    Write-Host "Building Docker image '$ImageName'..."
    docker build -t $ImageName $ProjectRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$runningId = docker ps -q --filter "name=^/${ContainerName}$"
if ($runningId) {
    if ($Build) {
        Write-Host "Restarting '$ContainerName' with rebuilt image..."
        docker rm -f $ContainerName | Out-Null
    } else {
        Write-Host "FinAlly is already running at http://localhost:$Port"
        exit 0
    }
} else {
    $stoppedId = docker ps -aq --filter "name=^/${ContainerName}$"
    if ($stoppedId) {
        docker rm $ContainerName | Out-Null
    }
}

$runArgs = @(
    "run", "-d",
    "--name", $ContainerName,
    "-v", "${VolumeName}:/app/db",
    "-p", "127.0.0.1:${Port}:8000"
)

$envFile = Join-Path $ProjectRoot ".env"
if (Test-Path $envFile) {
    $runArgs += @("--env-file", $envFile)
} else {
    Write-Host "Note: .env not found in project root; starting with default simulator settings."
}

$runArgs += $ImageName

Write-Host "Starting FinAlly container '$ContainerName'..."
& docker @runArgs | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ready = $false
Write-Host -NoNewline "Waiting for FinAlly to become ready"
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        # Keep waiting
    }
    Write-Host -NoNewline "."
    Start-Sleep -Seconds 1
}
Write-Host ""

if (-not $ready) {
    Write-Error "FinAlly failed to become healthy within 30s."
    docker logs --tail 40 $ContainerName
    exit 1
}

Write-Host "FinAlly is running at http://localhost:$Port"

if ($Open) {
    Start-Process "http://localhost:$Port"
}
