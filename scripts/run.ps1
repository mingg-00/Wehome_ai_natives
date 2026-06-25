param(
  [switch]$Execute
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$args = @()
if ($Execute) {
  $args += '--execute'
}

python .\orchestrator\main.py @args

