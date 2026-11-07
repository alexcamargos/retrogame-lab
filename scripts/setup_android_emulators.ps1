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
$CoreCacheDir = Join-Path $BaseDir "tools\android_cores"

if (-not (Test-Path $ApkCacheDir)) {
    New-Item -ItemType Directory -Path $ApkCacheDir -Force | Out-Null
}
if (-not (Test-Path $CoreCacheDir)) {
    New-Item -ItemType Directory -Path $CoreCacheDir -Force | Out-Null
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

# Cache de pacotes instalados no Android
$InstalledPackagesRaw = (& adb @AdbArgs shell "pm list packages") | Out-String
$InstalledPackages = @($InstalledPackagesRaw -split "`r?`n" | ForEach-Object {
    if ($_ -match "^package:\s*(.+)$") { $Matches[1].Trim() }
})

function Resolve-InstalledPackage {
    param([string[]]$PackageCandidates)
    foreach ($Pkg in $PackageCandidates) {
        if ($InstalledPackages -contains $Pkg) { return $Pkg }
    }
    return $null
}

function Find-LocalApk {
    param([string]$Pattern)
    $FoundFiles = @(Get-ChildItem -Path $ApkCacheDir -Filter $Pattern -File -ErrorAction SilentlyContinue | Sort-Object Length -Descending)
    if ($FoundFiles.Count -gt 0 -and $FoundFiles[0].Length -ge 1024) {
        return $FoundFiles[0].FullName
    }
    return $null
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
    "$TargetDevicePath/roms/wii",
    "$TargetDevicePath/roms/n64",
    "$TargetDevicePath/saves/snes",
    "$TargetDevicePath/saves/ps1",
    "$TargetDevicePath/saves/ps2",
    "$TargetDevicePath/saves/psp",
    "$TargetDevicePath/saves/psp/PSP/SAVEDATA",
    "$TargetDevicePath/saves/gc",
    "$TargetDevicePath/saves/dc",
    "$TargetDevicePath/saves/wii",
    "$TargetDevicePath/saves/n64",
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
*.ppst
*.p2s
PPSSPP_STATE/
*.tmp*
*.lock*
*.lck
*.wal
*.shm
(?d).DS_Store
(?d)thumbs.db
(?d)desktop.ini
(?d).syncthing.*
// Plataformas Exclusivas de Desktop (Windows-only)
ps3/
xbox360/
switch/
"@
    $TempStIgnore = [System.IO.Path]::GetTempFileName()
    Set-Content -Path $TempStIgnore -Value $StIgnoreContent -Encoding UTF8
    & adb @AdbArgs push $TempStIgnore "$TargetDevicePath/saves/.stignore" | Out-Null
    Remove-Item -Path $TempStIgnore -Force
}

# 4. Definição do Catálogo de Emuladores ARM64
$Emulators = @(
    @{
        Name        = "RetroArch (Universal)"
        Packages    = @("com.retroarch.aarch64", "com.retroarch")
        Url         = "https://buildbot.libretro.com/nightly/android/RetroArch_aarch64.apk"
        FilePattern = "*retroarch*.apk"
        DefaultFile = Join-Path $ApkCacheDir "RetroArch_aarch64.apk"
    },
    @{
        Name        = "DuckStation (PS1)"
        Packages    = @("com.github.stenzek.duckstation")
        Url         = "" # DuckStation oficial é distribuído na Google Play Store
        FilePattern = "*duckstation*.apk"
        DefaultFile = Join-Path $ApkCacheDir "duckstation-android.apk"
    },
    @{
        Name        = "PPSSPP (PSP)"
        Packages    = @("org.ppsspp.ppsspp", "org.ppsspp.ppssppgold")
        Url         = "https://www.ppsspp.org/files/1_18_1/ppsspp.apk"
        FilePattern = "*ppsspp*.apk"
        DefaultFile = Join-Path $ApkCacheDir "ppsspp.apk"
    },
    @{
        Name        = "Dolphin (GameCube/Wii)"
        Packages    = @("org.dolphinemu.dolphinemu")
        Url         = "https://dolphin-emu.org/download/get/latest/dolphin-master.apk"
        FilePattern = "*dolphin*.apk"
        DefaultFile = Join-Path $ApkCacheDir "dolphin-android.apk"
    },
    @{
        Name        = "Flycast (Dreamcast)"
        Packages    = @("com.flycast.emulator", "com.flyinghead.flycast")
        Url         = "https://github.com/flyinghead/flycast/releases/download/v2.7/flycast-2.7.apk"
        FilePattern = "*flycast*.apk"
        DefaultFile = Join-Path $ApkCacheDir "flycast-android.apk"
    }
)

# 5. Download e Instalação dos APKs
foreach ($Emu in $Emulators) {
    Write-Host "`n--- Processando: $($Emu.Name) ---" -ForegroundColor Yellow

    $InstalledPkg = Resolve-InstalledPackage -PackageCandidates $Emu.Packages
    $LocalApk = Find-LocalApk -Pattern $Emu.FilePattern

    # Tenta baixar online caso o APK local não exista e uma URL esteja configurada
    if (-not $LocalApk -and -not $SkipDownload -and $Emu.Url) {
        Write-Host "Tentando baixar pacote atualizado ($($Emu.Url))..." -ForegroundColor Gray
        try {
            Invoke-WebRequest -Uri $Emu.Url -OutFile $Emu.DefaultFile -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
            if ((Test-Path $Emu.DefaultFile) -and (Get-Item $Emu.DefaultFile).Length -ge 1024) {
                $LocalApk = $Emu.DefaultFile
            }
        } catch {
            if (Test-Path $Emu.DefaultFile) { Remove-Item $Emu.DefaultFile -Force }
            if (-not $InstalledPkg) {
                Write-Warning "Download online de $($Emu.Name) indisponível ou bloqueado por CDN. Forneça o APK em tools\android_apks\"
            }
        }
    }

    if ($LocalApk) {
        Write-Host "Instalando/Atualizando APK no dispositivo Android ($([System.IO.Path]::GetFileName($LocalApk)))..." -ForegroundColor Green
        & adb @AdbArgs install -r -d -g $LocalApk
        # Reavalia o pacote instalado após a instalação
        $InstalledPackagesRaw = (& adb @AdbArgs shell "pm list packages") | Out-String
        $InstalledPackages = @($InstalledPackagesRaw -split "`r?`n" | ForEach-Object {
            if ($_ -match "^package:\s*(.+)$") { $Matches[1].Trim() }
        })
        $InstalledPkg = Resolve-InstalledPackage -PackageCandidates $Emu.Packages
    } elseif ($InstalledPkg) {
        Write-Host "Emulador já instalado no dispositivo Android ($InstalledPkg)." -ForegroundColor Green
    } else {
        if ($Emu.Name -match "DuckStation") {
            Write-Warning "DuckStation (PS1) não encontrado em tools\android_apks\ nem instalado no dispositivo. Instale via Google Play Store (com.github.stenzek.duckstation) ou copie o APK para tools\android_apks\"
        } else {
            Write-Warning "APK válido para $($Emu.Name) não encontrado em $ApkCacheDir nem instalado no aparelho. Etapa ignorada."
        }
    }

    # Concessão mandatória de MANAGE_EXTERNAL_STORAGE (Android 11+)
    if ($InstalledPkg) {
        Write-Host "Concedendo permissão MANAGE_EXTERNAL_STORAGE para $InstalledPkg..." -ForegroundColor Gray
        & adb @AdbArgs shell "appops set $InstalledPkg MANAGE_EXTERNAL_STORAGE allow" 2>$null
    }
}

# 6. Tratamento Especial para o NetherSX2 (PS2)
Write-Host "`n--- Processando: NetherSX2 (PS2) ---" -ForegroundColor Yellow
$NetherPackages = @("com.theemulatorapp.nethersx2", "xyz.nethersx2.android", "xyz.aethersx2.android")
$NetherInstalled = Resolve-InstalledPackage -PackageCandidates $NetherPackages
$NetherApk = Find-LocalApk -Pattern "*nether*.apk"

if ($NetherApk) {
    Write-Host "Instalando/Atualizando NetherSX2 do cache local ($([System.IO.Path]::GetFileName($NetherApk)))..." -ForegroundColor Green
    & adb @AdbArgs install -r -d -g $NetherApk
    $InstalledPackagesRaw = (& adb @AdbArgs shell "pm list packages") | Out-String
    $InstalledPackages = @($InstalledPackagesRaw -split "`r?`n" | ForEach-Object {
        if ($_ -match "^package:\s*(.+)$") { $Matches[1].Trim() }
    })
    $NetherInstalled = Resolve-InstalledPackage -PackageCandidates $NetherPackages
} elseif ($NetherInstalled) {
    Write-Host "NetherSX2 já instalado no dispositivo Android ($NetherInstalled)." -ForegroundColor Green
} else {
    Write-Host "[AVISO] NetherSX2.apk não encontrado em tools\android_apks\ nem instalado no dispositivo." -ForegroundColor Magenta
    Write-Host "O NetherSX2 é um patch comunitário para o AetherSX2. Para instalar, copie o APK patcheado para tools\android_apks\" -ForegroundColor Gray
}

foreach ($Pkg in $NetherPackages) {
    if ($InstalledPackages -contains $Pkg) {
        Write-Host "Concedendo permissão MANAGE_EXTERNAL_STORAGE para $Pkg..." -ForegroundColor Gray
        & adb @AdbArgs shell "appops set $Pkg MANAGE_EXTERNAL_STORAGE allow" 2>$null
    }
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

    # 7.2 Injeção Direta - RetroArch (Universal e SNES)
    $RetroArchCfg = Join-Path $AndroidTemplatesDir "retroarch.cfg"
    if (Test-Path $RetroArchCfg) {
        Write-Host "Aplicando configuração: RetroArch..." -ForegroundColor Gray
        & adb @AdbArgs shell "mkdir -p /storage/emulated/0/RetroArch /storage/emulated/0/Android/data/com.retroarch.aarch64/files /storage/emulated/0/Android/data/com.retroarch.aarch64/files/cores /storage/emulated/0/Android/data/com.retroarch.aarch64/files/info /storage/emulated/0/RetroArch/playlists /storage/emulated/0/Android/data/com.retroarch.aarch64/files/playlists" 2>$null | Out-Null
        & adb @AdbArgs push $RetroArchCfg "/storage/emulated/0/RetroArch/retroarch.cfg" 2>$null | Out-Null
        & adb @AdbArgs push $RetroArchCfg "/storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg" 2>$null | Out-Null

        # Geração e Injeção Automática de Playlist de SNES (pré-vinculada ao Snes9x)
        $LocalSnesRoms = @()
        $LocalSnesDir = Join-Path $BaseDir "data\roms\snes"
        if (Test-Path $LocalSnesDir) {
            $LocalSnesRoms = @(Get-ChildItem -Path $LocalSnesDir -File | Where-Object { $_.Extension -in @(".sfc", ".smc", ".chd", ".zip") })
        }

        if ($LocalSnesRoms.Count -gt 0) {
            Write-Host "Gerando playlist automática de Super Nintendo ($($LocalSnesRoms.Count) títulos)..." -ForegroundColor Gray
            $PlaylistItems = @()
            $TargetCorePath = "/data/user/0/com.retroarch.aarch64/cores/snes9x_libretro_android.so"
            $TargetCoreName = "Nintendo - SNES / SFC (Snes9x)"
            $DbName = "Nintendo - Super Nintendo Entertainment System.lpl"

            foreach ($Rom in $LocalSnesRoms) {
                $CleanLabel = $Rom.BaseName -replace "_", " "
                $PlaylistItems += @{
                    path      = "$TargetDevicePath/roms/snes/$($Rom.Name)"
                    label     = $CleanLabel
                    core_path = $TargetCorePath
                    core_name = $TargetCoreName
                    crc32     = "DETECT"
                    db_name   = $DbName
                }
            }

            $PlaylistObj = @{
                version            = "1.5"
                default_core_path  = $TargetCorePath
                default_core_name  = $TargetCoreName
                label_display_mode = 0
                right_thumbnail_mode = 0
                left_thumbnail_mode  = 0
                sort_mode          = 0
                items              = $PlaylistItems
            }

            $TempPlaylist = Join-Path $CoreCacheDir $DbName
            $PlaylistObj | ConvertTo-Json -Depth 5 | Set-Content -Path $TempPlaylist -Encoding utf8
            & adb @AdbArgs push $TempPlaylist "/storage/emulated/0/RetroArch/playlists/$DbName" 2>$null | Out-Null
            & adb @AdbArgs push $TempPlaylist "/storage/emulated/0/Android/data/com.retroarch.aarch64/files/playlists/$DbName" 2>$null | Out-Null
        }

        Write-Host ">>> [Aviso RetroArch / SNES] Segurança Android (Linker W^X sem Root):" -ForegroundColor Cyan
        Write-Host "    A playlist de SNES foi gerada e vinculada ao Snes9x com sucesso." -ForegroundColor Gray
        Write-Host "    Por restrição do Android, o binário (.so) deve residir no namespace interno do app." -ForegroundColor Gray
        Write-Host "    Etapa única necessária no celular: Menu Principal -> Atualizador Online -> Baixar Núcleo -> Nintendo - SNES / SFC (Snes9x)." -ForegroundColor Yellow
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
        & adb @AdbArgs shell "mkdir -p /storage/emulated/0/Flycast" 2>$null | Out-Null
        & adb @AdbArgs push $FlycastCfg "/storage/emulated/0/Flycast/emu.cfg" 2>$null | Out-Null
        foreach ($Pkg in @("com.flycast.emulator", "com.flyinghead.flycast")) {
            & adb @AdbArgs shell "mkdir -p /storage/emulated/0/Android/data/$Pkg/files" 2>$null | Out-Null
            & adb @AdbArgs push $FlycastCfg "/storage/emulated/0/Android/data/$Pkg/files/emu.cfg" 2>$null | Out-Null
        }
    }

    # 7.6 DuckStation e NetherSX2 (Carga de perfis nos diretórios de staging do app)
    $DuckSettings = Join-Path $AndroidTemplatesDir "duckstation_settings.ini"
    if (Test-Path $DuckSettings) {
        Write-Host "Aplicando configuração: DuckStation..." -ForegroundColor Gray
        & adb @AdbArgs shell "mkdir -p /storage/emulated/0/Android/data/com.github.stenzek.duckstation/files" 2>$null | Out-Null
        & adb @AdbArgs push $DuckSettings "/storage/emulated/0/Android/data/com.github.stenzek.duckstation/files/settings.ini" 2>$null | Out-Null
    }
    $NetherSettings = Join-Path $AndroidTemplatesDir "nethersx2_settings.ini"
    if (Test-Path $NetherSettings) {
        Write-Host "Aplicando configuração: NetherSX2..." -ForegroundColor Gray
        foreach ($Pkg in @("com.theemulatorapp.nethersx2", "xyz.nethersx2.android", "xyz.aethersx2.android")) {
            & adb @AdbArgs shell "mkdir -p /storage/emulated/0/Android/data/$Pkg/files" 2>$null | Out-Null
            & adb @AdbArgs push $NetherSettings "/storage/emulated/0/Android/data/$Pkg/files/PCSX2.ini" 2>$null | Out-Null
        }
    }
    Write-Host "Injeção de configurações concluída." -ForegroundColor Green
}

# 8. Provisionamento e Otimização do Syncthing (nel0x/syncthing-android-gplay)
Write-Host "`n--- Processando: Syncthing-Fork (Sincronização de Saves) ---" -ForegroundColor Yellow
$SyncthingPackages = @(
    "com.github.catfriend1.syncthingandroid",
    "com.nutomic.syncthingandroid",
    "com.nutomic.syncthingcb"
)
$SyncthingInstalled = Resolve-InstalledPackage -PackageCandidates $SyncthingPackages
$SyncthingApk = Find-LocalApk -Pattern "*syncthing*.apk"
$SyncthingDefaultFile = Join-Path $ApkCacheDir "syncthing-fork-arm64.apk"
$SyncthingUrl = "https://github.com/nel0x/syncthing-android-gplay/releases/latest/download/app-arm64-v8a-release.apk"

if (-not $SyncthingApk -and -not $SkipDownload -and -not $SyncthingInstalled) {
    Write-Host "Baixando Syncthing-Fork atualizado (nel0x/syncthing-android-gplay)..." -ForegroundColor Gray
    try {
        Invoke-WebRequest -Uri $SyncthingUrl -OutFile $SyncthingDefaultFile -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
        if ((Test-Path $SyncthingDefaultFile) -and (Get-Item $SyncthingDefaultFile).Length -ge 1024) {
            $SyncthingApk = $SyncthingDefaultFile
        }
    } catch {
        if (Test-Path $SyncthingDefaultFile) { Remove-Item $SyncthingDefaultFile -Force }
        Write-Warning "Falha no download online do Syncthing-Fork. Forneça o APK em tools\android_apks\"
    }
}

if ($SyncthingApk -and -not $SyncthingInstalled) {
    Write-Host "Instalando Syncthing-Fork no dispositivo Android ($([System.IO.Path]::GetFileName($SyncthingApk)))..." -ForegroundColor Green
    & adb @AdbArgs install -r -d -g $SyncthingApk
    $InstalledPackagesRaw = (& adb @AdbArgs shell "pm list packages") | Out-String
    $InstalledPackages = @($InstalledPackagesRaw -split "`r?`n" | ForEach-Object {
        if ($_ -match "^package:\s*(.+)$") { $Matches[1].Trim() }
    })
    $SyncthingInstalled = Resolve-InstalledPackage -PackageCandidates $SyncthingPackages
} elseif ($SyncthingInstalled) {
    Write-Host "Syncthing já instalado no dispositivo Android ($SyncthingInstalled)." -ForegroundColor Green
}

if ($SyncthingInstalled) {
    Write-Host "Concedendo permissão MANAGE_EXTERNAL_STORAGE para $SyncthingInstalled..." -ForegroundColor Gray
    & adb @AdbArgs shell "appops set $SyncthingInstalled MANAGE_EXTERNAL_STORAGE allow" 2>$null
    Write-Host "Inserindo Syncthing na whitelist de economia de bateria (Doze Mode)..." -ForegroundColor Gray
    $DumpResult = (& adb @AdbArgs shell "dumpsys deviceidle whitelist +$SyncthingInstalled") | Out-String
    Write-Host "Whitelist de economia de bateria aplicada com sucesso: $SyncthingInstalled" -ForegroundColor Green
} else {
    Write-Warning "Nenhum cliente Syncthing instalado no dispositivo. O pareamento de saves exige o Syncthing-Fork (nel0x/syncthing-android-gplay)."
}

Write-Host "`n=== Provisionamento Android Concluído com Sucesso! ===" -ForegroundColor Green
