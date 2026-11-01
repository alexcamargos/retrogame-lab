[CmdletBinding()]
param (
    [switch]$SkipWinget = $false
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot
$BinDir   = Join-Path $BaseDir "bin"
$ToolsDir = Join-Path $BaseDir "tools"
$DataDir  = Join-Path $BaseDir "data"
$TplDir   = Join-Path $BaseDir "templates\config"

Write-Host "=== Provisionamento do Pipeline Retrogaming no Windows 11 ===" -ForegroundColor Green

# 1. Instalação de Runtimes e Ferramentas via Winget
if (-not $SkipWinget) {
    Write-Host "`n>>> Verificando Runtimes e Ferramentas via winget..." -ForegroundColor Cyan
    
    # Runtimes que exigem elevação (avisa se não for Administrador)
    $IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $IsAdmin) {
        Write-Warning "Aviso: Para instalar os runtimes de sistema (VCRedist e DirectX), execute este script como Administrador caso ainda não estejam presentes."
    }

    $Packages = @(
        "Microsoft.VCRedist.2015+.x64",
        "Microsoft.DirectX",
        "Microsoft.PowerShell",
        "Git.Git",
        "7zip.7zip",
        "Google.PlatformTools",
        "Syncthing.Syncthing",
        "Astral-sh.uv"
    )

    foreach ($Pkg in $Packages) {
        Write-Host "Verificando/Instalando: $Pkg..." -ForegroundColor Gray
        winget install --id $Pkg -e --source winget --silent --accept-package-agreements --accept-source-agreements 2>$null
    }
}

# 2. Criação da Estrutura de Diretórios
Write-Host "`n>>> Criando estrutura hierárquica..." -ForegroundColor Cyan
$Folders = @(
    "$DataDir\bios\ps1", "$DataDir\bios\ps2", "$DataDir\bios\dc",
    "$DataDir\roms\snes", "$DataDir\roms\ps1", "$DataDir\roms\ps2", "$DataDir\roms\psp", "$DataDir\roms\gc", "$DataDir\roms\dc",
    "$DataDir\saves\snes", "$DataDir\saves\ps1", "$DataDir\saves\ps2", "$DataDir\saves\psp", "$DataDir\saves\gc", "$DataDir\saves\dc",
    "$DataDir\states",
    "$BinDir\retroarch", "$BinDir\duckstation", "$BinDir\pcsx2", "$BinDir\ppsspp", "$BinDir\dolphin", "$BinDir\flycast", "$BinDir\es-de",
    $ToolsDir
)
foreach ($Folder in $Folders) {
    if (-not (Test-Path $Folder)) {
        New-Item -ItemType Directory -Path $Folder -Force | Out-Null
    }
}

# 3. Criação dos Marcadores de Portabilidade Oficiais
New-Item -ItemType File -Path (Join-Path $BinDir "duckstation\portable.txt") -Force | Out-Null
New-Item -ItemType File -Path (Join-Path $BinDir "pcsx2\portable.txt") -Force | Out-Null
New-Item -ItemType File -Path (Join-Path $BinDir "dolphin\portable.txt") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BinDir "ppsspp\memstick") -Force | Out-Null

# 4. Injeção de Templates de Configuração Inicial (Cold Start Protection)
if (Test-Path $TplDir) {
    Write-Host "`n>>> Injetando templates de configuração de saves e BIOS..." -ForegroundColor Cyan
    if (Test-Path "$TplDir\retroarch.cfg") { Copy-Item "$TplDir\retroarch.cfg" "$BinDir\retroarch\" -Force }
    if (Test-Path "$TplDir\duckstation_settings.ini") { Copy-Item "$TplDir\duckstation_settings.ini" "$BinDir\duckstation\settings.ini" -Force }
    if (Test-Path "$TplDir\PCSX2.ini") { 
        $Pcsx2Inis = Join-Path $BinDir "pcsx2\inis"
        if (-not (Test-Path $Pcsx2Inis)) { New-Item -ItemType Directory -Path $Pcsx2Inis -Force | Out-Null }
        Copy-Item "$TplDir\PCSX2.ini" "$Pcsx2Inis\PCSX2.ini" -Force 
    }
}

# 5. Verificação de Utilitários de Linha de Comando (tools/)
$ChdmanExe = Join-Path $ToolsDir "chdman.exe"
$ChdmanInPath = Get-Command "chdman" -ErrorAction SilentlyContinue
if (-not (Test-Path $ChdmanExe) -and -not $ChdmanInPath) {
    Write-Host "`n[AVISO] chdman.exe não detectado em tools\ nem no PATH." -ForegroundColor Yellow
    Write-Host "Para compactar mídias de CD/DVD via scripts\convert_chd.ps1, extraia o 'chdman.exe' (distribuído no pacote oficial MAME) para a pasta '$ToolsDir'." -ForegroundColor Gray
}

Write-Host "`n=== Provisionamento Concluído com Sucesso! ===" -ForegroundColor Green
