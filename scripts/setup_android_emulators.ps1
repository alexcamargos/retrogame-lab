[CmdletBinding()]
param (
    [string]$DeviceId = "",
    [string]$TargetDevicePath = "/storage/emulated/0/RetroGames",
    [switch]$SkipDownload = $false
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $BaseDir "tools"
$ApkCacheDir = Join-Path $BaseDir "tools\android_apks"

if (-not (Test-Path $ApkCacheDir)) {
    New-Item -ItemType Directory -Path $ApkCacheDir -Force | Out-Null
}

Write-Host ">>> Identificando conexões via ADB..." -ForegroundColor Cyan

# 1. Resolução Segura de Dispositivo (Suporte a Multi-Device)
try {
    $DeviceLines = @((adb devices | Out-String) -split "`r?`n" | Where-Object { $_ -match "\bdevice\b" -and $_ -notmatch "List of devices" })
} catch {
    Write-Error "O utilitário adb não foi encontrado no PATH. Execute scripts/bootstrap.ps1 para instalar o Google.PlatformTools."
}

if (-not $DeviceLines -or $DeviceLines.Count -eq 0) {
    Write-Error "Nenhum dispositivo Android autorizado foi detectado. Ative a Depuração USB e autorize o computador."
}

if (-not $DeviceId) {
    $DeviceId = ($DeviceLines[0].Trim() -split "\s+")[0]
    Write-Host ">>> Dispositivo selecionado automaticamente: $DeviceId" -ForegroundColor Yellow
}

$AdbArgs = @("-s", $DeviceId)

# Identificação Dinâmica da Arquitetura
& adb @AdbArgs start-server 2>$null | Out-Null
$DeviceModelRaw = (& adb @AdbArgs shell "getprop ro.product.model") | Out-String
$DeviceAbiRaw   = (& adb @AdbArgs shell "getprop ro.product.cpu.abi") | Out-String

$DeviceModel = ($DeviceModelRaw.Trim() -split "`r?`n")[-1].Trim()
$DeviceAbi   = ($DeviceAbiRaw.Trim() -split "`r?`n")[-1].Trim()
Write-Host ">>> Dispositivo Alvo: $DeviceModel (ABI: $DeviceAbi)" -ForegroundColor Green

if ($DeviceAbi -notmatch "arm64") {
    Write-Warning "O dispositivo conectado não reporta ABI arm64-v8a ($DeviceAbi). Alguns APKs podem falhar."
}

# 2. Estruturação Completa de Pastas no Android
Write-Host ">>> Criando estrutura hierárquica no armazenamento interno..." -ForegroundColor Cyan
$Directories = @(
    "$TargetDevicePath/bios/ps1",
    "$TargetDevicePath/bios/ps2",
    "$TargetDevicePath/bios/dc",
    "$TargetDevicePath/roms/snes",
    "$TargetDevicePath/roms/ps1",
    "$TargetDevicePath/roms/ps2",
    "$TargetDevicePath/roms/psp",
    "$TargetDevicePath/roms/gc",
    "$TargetDevicePath/roms/dc",
    "$TargetDevicePath/saves/snes",
    "$TargetDevicePath/saves/ps1",
    "$TargetDevicePath/saves/ps2",
    "$TargetDevicePath/saves/psp",
    "$TargetDevicePath/saves/gc",
    "$TargetDevicePath/saves/dc",
    "$TargetDevicePath/config",
    "$TargetDevicePath/states"
)

foreach ($Dir in $Directories) {
    & adb @AdbArgs shell "mkdir -p `"$Dir`""
}

# 3. Injeção de Regras .stignore no Android
$LocalStIgnore = Join-Path $BaseDir "data\saves\.stignore"
if (Test-Path $LocalStIgnore) {
    & adb @AdbArgs push $LocalStIgnore "$TargetDevicePath/saves/.stignore" | Out-Null
} else {
    $StIgnoreContent = @"
// .stignore para retrogames-saves
*.state*
*.s[0-9][0-9]
*.nvram.bak
*.tmp*
*.lock*
*.lck
*.wal
*.shm
(?d).DS_Store
(?d)thumbs.db
(?d)desktop.ini
(?d).syncthing.*
"@
    $TempStIgnore = [System.IO.Path]::GetTempFileName()
    Set-Content -Path $TempStIgnore -Value $StIgnoreContent -Encoding UTF8
    & adb @AdbArgs push $TempStIgnore "$TargetDevicePath/saves/.stignore" | Out-Null
    Remove-Item -Path $TempStIgnore -Force
}

# 4. Definição do Catálogo de Emuladores ARM64
$Emulators = @(
    @{
        Name    = "RetroArch (Universal)"
        Package = "com.retroarch.aarch64"
        Url     = "https://buildbot.libretro.com/nightly/android/RetroArch_aarch64.apk"
        File    = Join-Path $ApkCacheDir "RetroArch_aarch64.apk"
    },
    @{
        Name    = "DuckStation (PS1)"
        Package = "com.github.stenzek.duckstation"
        Url     = "" # DuckStation Android é mantido preferencialmente em cache local
        File    = Join-Path $ApkCacheDir "duckstation-android.apk"
    },
    @{
        Name    = "PPSSPP (PSP)"
        Package = "org.ppsspp.ppsspp"
        Url     = "https://www.ppsspp.org/files/1_18_1/ppsspp.apk"
        File    = Join-Path $ApkCacheDir "ppsspp.apk"
    },
    @{
        Name    = "Dolphin (GameCube/Wii)"
        Package = "org.dolphinemu.dolphinemu"
        Url     = "https://dolphin-emu.org/download/get/latest/dolphin-master.apk"
        File    = Join-Path $ApkCacheDir "dolphin-android.apk"
    },
    @{
        Name    = "Flycast (Dreamcast)"
        Package = "com.flyinghead.flycast"
        Url     = "https://github.com/flyinghead/flycast/releases/download/v2.7/flycast-2.7.apk"
        File    = Join-Path $ApkCacheDir "flycast-android.apk"
    }
)

# 5. Download e Instalação dos APKs
foreach ($Emu in $Emulators) {
    Write-Host "`n--- Processando: $($Emu.Name) ---" -ForegroundColor Yellow

    if (-not $SkipDownload -and $Emu.Url) {
        if (-not (Test-Path $Emu.File) -or (Get-Item $Emu.File).Length -lt 1024) {
            Write-Host "Baixando pacote atualizado ($($Emu.Url))..." -ForegroundColor Gray
            try {
                Invoke-WebRequest -Uri $Emu.Url -OutFile $Emu.File -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
            } catch {
                if (Test-Path $Emu.File) { Remove-Item $Emu.File -Force }
                Write-Warning "Falha no download online de $($Emu.Name). Verifique a URL ou forneça o APK em tools\android_apks\"
            }
        }
    }

    if ((Test-Path $Emu.File) -and (Get-Item $Emu.File).Length -ge 1024) {
        Write-Host "Instalando/Atualizando APK no dispositivo Android..." -ForegroundColor Green
        & adb @AdbArgs install -r -d -g $Emu.File

        # Concessão mandatória de MANAGE_EXTERNAL_STORAGE (Android 11+)
        Write-Host "Concedendo permissão MANAGE_EXTERNAL_STORAGE..." -ForegroundColor Gray
        & adb @AdbArgs shell "appops set $($Emu.Package) MANAGE_EXTERNAL_STORAGE allow" 2>$null
    } else {
        Write-Warning "APK válido para $($Emu.Name) não encontrado em $($Emu.File). Etapa ignorada."
    }
}

# 6. Tratamento Especial para o NetherSX2 (PS2)
$NetherApk = Join-Path $ApkCacheDir "NetherSX2.apk"
if (Test-Path $NetherApk) {
    Write-Host "`n--- Instalando NetherSX2 (PS2) do cache local ---" -ForegroundColor Yellow
    & adb @AdbArgs install -r -d -g $NetherApk
    & adb @AdbArgs shell "appops set xyz.aethersx2.android MANAGE_EXTERNAL_STORAGE allow" 2>$null
    & adb @AdbArgs shell "appops set xyz.nethersx2.android MANAGE_EXTERNAL_STORAGE allow" 2>$null
} else {
    Write-Host "`n[AVISO] NetherSX2.apk não encontrado em tools\android_apks\. Copie o APK patcheado para concluir a instalação do PS2." -ForegroundColor Magenta
}

# 7. Injeção de Arquivos de Configuração Específicos para Android
Write-Host "`n>>> Injetando configurações automáticas dos emuladores no Android..." -ForegroundColor Cyan
$AndroidTemplatesDir = Join-Path $BaseDir "templates\android"

if (Test-Path $AndroidTemplatesDir) {
    # 7.1 Espelhar templates para a pasta central de configurações no dispositivo
    Write-Host "Enviando perfis padronizados para $TargetDevicePath/config/..." -ForegroundColor Gray
    Get-ChildItem -Path $AndroidTemplatesDir -File | ForEach-Object {
        & adb @AdbArgs push $_.FullName "$TargetDevicePath/config/$($_.Name)" 2>$null | Out-Null
    }

    # 7.2 Injeção Direta - RetroArch (Universal)
    $RetroArchCfg = Join-Path $AndroidTemplatesDir "retroarch.cfg"
    if (Test-Path $RetroArchCfg) {
        Write-Host "Aplicando configuração: RetroArch..." -ForegroundColor Gray
        & adb @AdbArgs shell "mkdir -p /storage/emulated/0/RetroArch /storage/emulated/0/Android/data/com.retroarch.aarch64/files" 2>$null | Out-Null
        & adb @AdbArgs push $RetroArchCfg "/storage/emulated/0/RetroArch/retroarch.cfg" 2>$null | Out-Null
        & adb @AdbArgs push $RetroArchCfg "/storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg" 2>$null | Out-Null
    }

    # 7.3 Injeção Direta - PPSSPP (PSP)
    $PpssppIni = Join-Path $AndroidTemplatesDir "ppsspp.ini"
    if (Test-Path $PpssppIni) {
        Write-Host "Aplicando configuração: PPSSPP..." -ForegroundColor Gray
        & adb @AdbArgs shell "mkdir -p /storage/emulated/0/PSP/SYSTEM /storage/emulated/0/Android/data/org.ppsspp.ppsspp/files/PSP/SYSTEM" 2>$null | Out-Null
        & adb @AdbArgs push $PpssppIni "/storage/emulated/0/PSP/SYSTEM/ppsspp.ini" 2>$null | Out-Null
        & adb @AdbArgs push $PpssppIni "/storage/emulated/0/Android/data/org.ppsspp.ppsspp/files/PSP/SYSTEM/ppsspp.ini" 2>$null | Out-Null
    }

    # 7.4 Injeção Direta - Dolphin (GameCube/Wii)
    $DolphinIni = Join-Path $AndroidTemplatesDir "Dolphin.ini"
    if (Test-Path $DolphinIni) {
        Write-Host "Aplicando configuração: Dolphin..." -ForegroundColor Gray
        & adb @AdbArgs shell "mkdir -p /storage/emulated/0/dolphin-emu/Config /storage/emulated/0/Android/data/org.dolphinemu.dolphinemu/files/Config" 2>$null | Out-Null
        & adb @AdbArgs push $DolphinIni "/storage/emulated/0/dolphin-emu/Config/Dolphin.ini" 2>$null | Out-Null
        & adb @AdbArgs push $DolphinIni "/storage/emulated/0/Android/data/org.dolphinemu.dolphinemu/files/Config/Dolphin.ini" 2>$null | Out-Null
    }

    # 7.5 Injeção Direta - Flycast (Dreamcast)
    $FlycastCfg = Join-Path $AndroidTemplatesDir "emu.cfg"
    if (Test-Path $FlycastCfg) {
        Write-Host "Aplicando configuração: Flycast..." -ForegroundColor Gray
        & adb @AdbArgs shell "mkdir -p /storage/emulated/0/Flycast /storage/emulated/0/Android/data/com.flyinghead.flycast/files" 2>$null | Out-Null
        & adb @AdbArgs push $FlycastCfg "/storage/emulated/0/Flycast/emu.cfg" 2>$null | Out-Null
        & adb @AdbArgs push $FlycastCfg "/storage/emulated/0/Android/data/com.flyinghead.flycast/files/emu.cfg" 2>$null | Out-Null
    }

    # 7.6 DuckStation e NetherSX2 (Carga de perfis nos diretórios de staging do app)
    $DuckSettings = Join-Path $AndroidTemplatesDir "duckstation_settings.ini"
    if (Test-Path $DuckSettings) {
        & adb @AdbArgs shell "mkdir -p /storage/emulated/0/Android/data/com.github.stenzek.duckstation/files" 2>$null | Out-Null
        & adb @AdbArgs push $DuckSettings "/storage/emulated/0/Android/data/com.github.stenzek.duckstation/files/settings.ini" 2>$null | Out-Null
    }
    $NetherSettings = Join-Path $AndroidTemplatesDir "nethersx2_settings.ini"
    if (Test-Path $NetherSettings) {
        & adb @AdbArgs shell "mkdir -p /storage/emulated/0/Android/data/xyz.nethersx2.android/files /storage/emulated/0/Android/data/xyz.aethersx2.android/files" 2>$null | Out-Null
        & adb @AdbArgs push $NetherSettings "/storage/emulated/0/Android/data/xyz.nethersx2.android/files/PCSX2.ini" 2>$null | Out-Null
        & adb @AdbArgs push $NetherSettings "/storage/emulated/0/Android/data/xyz.aethersx2.android/files/PCSX2.ini" 2>$null | Out-Null
    }
    Write-Host "Injeção de configurações concluída." -ForegroundColor Green
}

# 8. Otimização do Syncthing contra Doze Mode (Economia de Bateria)
Write-Host "`n>>> Inserindo Syncthing na whitelist de economia de bateria..." -ForegroundColor Cyan
$SyncthingPackages = @(
    "com.nutomic.syncthingandroid",
    "com.github.catfriend1.syncthingandroid",
    "com.nutomic.syncthingcb"
)
foreach ($Pkg in $SyncthingPackages) {
    & adb @AdbArgs shell "dumpsys deviceidle whitelist +$Pkg" 2>$null
}

Write-Host "`n=== Provisionamento Android Concluído com Sucesso! ===" -ForegroundColor Green
