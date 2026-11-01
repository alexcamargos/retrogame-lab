[CmdletBinding()]
param (
    [string]$Platform = "snes",
    [string]$Query = "",
    [string]$Identifier = ""
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot

Push-Location $BaseDir
try {
    $cliArgs = @("fetch-roms", "--platform", $Platform)
    if ($Query) {
        $cliArgs += @("--query", $Query)
    }
    if ($Identifier) {
        $cliArgs += @("--identifier", $Identifier)
    }

    uv run python -m retrogame_lab.cli @cliArgs

    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
