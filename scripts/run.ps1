param(
  [switch]$Worker
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($Worker) {
  python -m orchestrator.main --worker
  exit $LASTEXITCODE
}

python -m discord_bot.main

