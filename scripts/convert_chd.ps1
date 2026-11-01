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

# Localiza candidatos válidos para conversão preservando a integridade de faixas multi-track
$Candidates = Get-ChildItem -Path $SourceDirectory -Include *.cue, *.gdi, *.iso, *.bin -Recurse | Where-Object {
    $Ext = $_.Extension.ToLower()
    $Dir = $_.DirectoryName

    # Mídias de GameCube e Wii devem utilizar RVZ via Dolphin, não CHD
    if ($Dir -match "[\\/](gc|wii)($|[\\/])") {
        Write-Warning "Ignorando $($_.Name): Mídias de GameCube/Wii devem ser convertidas para .rvz via Dolphin, não .chd."
        return $false
    }

    # Previne corrupção e CHDs órfãos: se for .bin, verifica se há descritor .cue/.gdi associado na pasta
    if ($Ext -eq ".bin") {
        $HasDescriptor = Get-ChildItem -Path $Dir -Filter "*.cue" -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $HasDescriptor) {
            $HasDescriptor = Get-ChildItem -Path $Dir -Filter "*.gdi" -ErrorAction SilentlyContinue | Select-Object -First 1
        }
        if ($HasDescriptor) {
            # Arquivo .bin é uma trilha de dados/áudio já referenciada pelo .cue ou .gdi
            return $false
        }
    }

    return $true
}

foreach ($File in $Candidates) {
    $OutFile = [System.IO.Path]::ChangeExtension($File.FullName, ".chd")
    if (Test-Path $OutFile) {
        Write-Host ">>> Arquivo já convertido, pulando: $(Split-Path $OutFile -Leaf)" -ForegroundColor Gray
        continue
    }

    $Ext = $File.Extension.ToLower()
    $Command = "createcd"
    if ($MediaType -eq "dvd" -or ($MediaType -eq "auto" -and $Ext -eq ".iso" -and ($File.DirectoryName -match "[\\/]ps2($|[\\/])" -or $SourceDirectory -match "[\\/]ps2($|[\\/])"))) {
        $Command = "createdvd"
    }

    Write-Host ">>> Comprimindo ($Command): $($File.Name) -> $(Split-Path $OutFile -Leaf)" -ForegroundColor Cyan
    & $Chdman $Command -i $File.FullName -o $OutFile
}
