[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [string]$SourceDirectory,

    [ValidateSet("cd", "dvd", "auto")]
    [string]$MediaType = "auto"
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot
$Chdman = Join-Path $BaseDir "tools\chdman.exe"

if (-not (Test-Path $Chdman)) {
    Write-Error "chdman.exe não encontrado em tools\. Execute o bootstrap ou copie chdman para tools\ primeiro."
}

if (-not (Test-Path $SourceDirectory)) {
    Write-Error "Diretório de origem não encontrado: $SourceDirectory"
}

Get-ChildItem -Path $SourceDirectory -Include *.cue, *.iso, *.bin -Recurse | ForEach-Object {
    $OutFile = [System.IO.Path]::ChangeExtension($_.FullName, ".chd")
    if (Test-Path $OutFile) {
        Write-Host ">>> Arquivo já convertido, pulando: $(Split-Path $OutFile -Leaf)" -ForegroundColor Gray
        return
    }

    $Ext = $_.Extension.ToLower()

    # Mídias de GameCube e Wii devem utilizar RVZ via Dolphin, não CHD
    if ($_.DirectoryName -match "\\gc" -or $_.DirectoryName -match "\\wii") {
        Write-Warning "Ignorando $($_.Name): Mídias de GameCube/Wii devem ser convertidas para .rvz via Dolphin, não .chd."
        return
    }

    $Command = "createcd"
    if ($MediaType -eq "dvd" -or ($MediaType -eq "auto" -and $Ext -eq ".iso" -and $_.DirectoryName -match "\\ps2")) {
        $Command = "createdvd"
    }

    Write-Host ">>> Comprimindo ($Command): $($_.Name) -> $(Split-Path $OutFile -Leaf)" -ForegroundColor Cyan
    & $Chdman $Command -i $_.FullName -o $OutFile
}
