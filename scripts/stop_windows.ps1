$ErrorActionPreference = "Stop"

$ContainerName = "finally"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is not installed or not in PATH."
    exit 1
}

$containerId = docker ps -aq --filter "name=^/${ContainerName}$"
if ($containerId) {
    Write-Host "Stopping and removing container '$ContainerName'..."
    docker rm -f $ContainerName | Out-Null
    Write-Host "FinAlly stopped. Persistent data volume 'finally-data' was preserved."
} else {
    Write-Host "FinAlly container '$ContainerName' is not running."
}
