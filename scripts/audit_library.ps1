[CmdletBinding()]
param (
    [switch]$Json = $false
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot

Push-Location $BaseDir
try {
    if ($Json) {
        uv run python -m retrogame_lab.cli audit --json-output
    } else {
        uv run python -m retrogame_lab.cli audit
    }
    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
