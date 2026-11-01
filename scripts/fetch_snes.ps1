[CmdletBinding()]
param (
    [string]$Query = ""
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot

Push-Location $BaseDir
try {
    if ($Query) {
        uv run python -m retrogame_lab.cli fetch-snes --query $Query
    } else {
        uv run python -m retrogame_lab.cli fetch-snes
    }
    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
