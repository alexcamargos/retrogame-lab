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
    # Fallback transparente para chdman presente no PATH do sistema
    $ChdmanCmd = Get-Command "chdman.exe" -ErrorAction SilentlyContinue
    if (-not $ChdmanCmd) {
        $ChdmanCmd = Get-Command "chdman" -ErrorAction SilentlyContinue
    }
    if ($ChdmanCmd) {
        $Chdman = $ChdmanCmd.Source
    } else {
        Write-Error "chdman.exe não encontrado em tools\ nem no PATH do sistema. Copie chdman.exe (do pacote MAME) para tools\ ou adicione-o ao PATH."
    }
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
        if (-not $HasDescriptor) {
            Write-Warning "Ignorando $($_.Name): arquivo .bin sem descritor .cue/.gdi associado."
        }
        # Arquivo .bin não deve ser passado diretamente ao chdman createcd sem descritor
        return $false
    }

    return $true
}

$Conversions = @()
$OutputPaths = @{}
foreach ($File in $Candidates) {
    # Higieniza o nome do arquivo de saída (converte para minúsculas, substitui espaços por '_' e remove aspas e caracteres especiais)
    $BaseName = [System.IO.Path]::GetFileNameWithoutExtension($File.FullName).ToLower()
    $SanitizedBase = $BaseName -replace "['""`~^!?\:;*<>|#]", ""
    $SanitizedBase = $SanitizedBase -replace "\s+", "_"
    $SanitizedBase = $SanitizedBase -replace "_+", "_"
    $SanitizedBase = $SanitizedBase.Trim("_")

    $OutFile = Join-Path $File.DirectoryName "$SanitizedBase.chd"
    $Ext = $File.Extension.ToLower()
    if ($MediaType -eq 'auto' -and $Ext -eq '.iso') {
        throw "Tipo de mídia ambíguo para '$($File.FullName)'. Informe -MediaType cd ou dvd."
    }
    if ($MediaType -eq 'dvd' -and $Ext -ne '.iso') {
        throw "DVD exige ISO de dados, não '$($File.Name)'."
    }
    $Command = if ($MediaType -eq 'dvd') { 'createdvd' } else { 'createcd' }
    $OutputKey = $OutFile.ToLowerInvariant()
    if ($OutputPaths.ContainsKey($OutputKey)) {
        throw "Colisão de saída entre '$($OutputPaths[$OutputKey])' e '$($File.FullName)': $OutFile"
    }
    $OutputPaths[$OutputKey] = $File.FullName
    if (Test-Path -LiteralPath $OutFile) {
        throw "Saída já existe e sua origem não pode ser verificada: $OutFile"
    }
    $Conversions += [PSCustomObject]@{ File = $File; OutFile = $OutFile; Command = $Command }
}

foreach ($Conversion in $Conversions) {
    $File = $Conversion.File
    $OutFile = $Conversion.OutFile
    $Command = $Conversion.Command
    $TempOut = "$OutFile.partial_$PID"
    if (Test-Path -LiteralPath $TempOut) { throw "Arquivo temporário já existe: $TempOut" }
    Write-Host ">>> Comprimindo ($Command): $($File.Name) -> $(Split-Path $OutFile -Leaf)" -ForegroundColor Cyan
    try {
        & $Chdman $Command -i $File.FullName -o $TempOut
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $TempOut)) {
            throw "Falha ao converter '$($File.Name)' (código: $LASTEXITCODE)."
        }
        & $Chdman verify -i $TempOut
        if ($LASTEXITCODE -ne 0) { throw "Falha na verificação do CHD: $TempOut" }
        Move-Item -LiteralPath $TempOut -Destination $OutFile
    } finally {
        if (Test-Path -LiteralPath $TempOut) { Remove-Item -LiteralPath $TempOut -Force }
    }
}
