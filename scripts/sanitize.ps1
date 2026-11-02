[CmdletBinding()]
param (
    [Parameter(Position = 0)]
    [string]$Path = "",

    [switch]$Apply = $false
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot

Push-Location $BaseDir
try {
    $cliArgs = @("sanitize")
    if ($Path) {
        $cliArgs += @("--path", $Path)
    }
    if ($Apply) {
        $cliArgs += @("--apply")
    } else {
        $cliArgs += @("--dry-run")
    }

    uv run python -m retrogame_lab.cli @cliArgs

    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
