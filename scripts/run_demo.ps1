Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$dataset = if ($args.Count -gt 0 -and $args[0]) { $args[0] } else { "data/demo_metrics.json" }

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

function Import-DotEnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            return
        }

        $parts = $line.Split('=', 2)
        if ($parts.Count -ne 2) {
            return
        }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($name) {
            [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}

Set-Location $projectRoot
Import-DotEnvFile -Path (Join-Path $projectRoot '.env')
python src/main.py --input $dataset
