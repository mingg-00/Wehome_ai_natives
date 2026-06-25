$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$outputDir = Join-Path $root 'output'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$archivePath = Join-Path $outputDir 'wehome-integration-deploy.zip'
if (Test-Path $archivePath) {
  Remove-Item $archivePath -Force
}

Compress-Archive -Path @(
  'README.md',
  'env.example',
  'docs',
  'orchestrator',
  'scripts'
) -DestinationPath $archivePath

Write-Host "Created $archivePath"
