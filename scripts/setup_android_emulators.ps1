[CmdletBinding()]
param (
    [string]$DeviceId = "",
    [string]$TargetDevicePath = "/storage/emulated/0/RetroGames",
    [switch]$SkipDownload = $false,
    [switch]$ForceTemplates = $false
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
    "$TargetDevicePath/saves/.stfolder",
    "$TargetDevicePath/roms/.stfolder",
    "$TargetDevicePath/bios/.stfolder",
    "$TargetDevicePath/config",
    "$TargetDevicePath/states"
)

foreach ($Dir in $Directories) {
    & adb @AdbArgs shell "mkdir -p `"$Dir`""
}

# 3. Injeção de Regras .stignore no Android
$RemoteIgnoreExists = (& adb @AdbArgs shell "[ -f '$TargetDevicePath/saves/.stignore' ] && echo exists") | Out-String
if ($RemoteIgnoreExists -match 'exists') {
    Write-Warning "O .stignore Android existente foi preservado. Execute 'retrogame syncthing --apply --no-windows' para incorporar as regras obrigatórias."
} else {
    $StIgnoreContent = @"
// .stignore para retrogames-saves
*.state*
*.s[0-9][0-9]
*.nvram.bak
*.ppst*
*.p2s*
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

if (-not $NetherApk -and -not $SkipDownload) {
    Write-Host "Tentando baixar NetherSX2 Classic atualizado (Trixarian/NetherSX2-classic)..." -ForegroundColor Gray
    try {
        $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/Trixarian/NetherSX2-classic/releases/latest" -Headers @{ "User-Agent" = "RetroGameLab-Bootstrap/1.0" }
        $Asset = $Release.assets | Where-Object { $_.name -match "\.apk$" } | Select-Object -First 1
        if ($Asset) {
            $DefaultNetherFile = Join-Path $ApkCacheDir $Asset.name
            Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile $DefaultNetherFile -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
            if ((Test-Path $DefaultNetherFile) -and (Get-Item $DefaultNetherFile).Length -ge 1024) {
                $NetherApk = $DefaultNetherFile
            }
        }
    } catch {
        Write-Warning "Download online de NetherSX2 Classic indisponível: $($_.Exception.Message)"
    }
}

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
    Write-Host "Execute '.\retrogame download-emulators -Emulators nethersx2' ou copie o APK para tools\android_apks\" -ForegroundColor Gray
}

foreach ($Pkg in $NetherPackages) {
    if ($InstalledPackages -contains $Pkg) {
        Write-Host "Concedendo permissão MANAGE_EXTERNAL_STORAGE para $Pkg..." -ForegroundColor Gray
        & adb @AdbArgs shell "appops set $Pkg MANAGE_EXTERNAL_STORAGE allow" 2>$null
    }
}

# 7. Injeção de Arquivos de Configuração Específicos para Android
function Push-AndroidConfigIfNeeded {
    param (
        [string]$LocalPath,
        [string]$RemotePath,
        [switch]$ForceOverwrite
    )
    if (-not (Test-Path $LocalPath)) { return }
    if (-not $ForceOverwrite) {
        $ExistsOut = (& adb @AdbArgs shell "[ -f '$RemotePath' ] && echo 'exists' || echo 'missing'") | Out-String
        if ($ExistsOut -match "exists") { return }
    }
    $PushOut = (& adb @AdbArgs push $LocalPath $RemotePath 2>&1) | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Não foi possível gravar '$RemotePath' via ADB (restrição de Scoped Storage Android 13+/14+): $($PushOut.Trim()). Utilize o perfil salvo em '$TargetDevicePath/config/'."
    }
}

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
        Push-AndroidConfigIfNeeded $RetroArchCfg "/storage/emulated/0/RetroArch/retroarch.cfg" -ForceOverwrite:$ForceTemplates
        Push-AndroidConfigIfNeeded $RetroArchCfg "/storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg" -ForceOverwrite:$ForceTemplates

        # Geração e Injeção Automática de Playlists (SNES e Nintendo 64)
        $RetroArchPlaylists = @(
            @{
                Label      = "Super Nintendo"
                RomSubdir  = "snes"
                Extensions = @(".sfc", ".smc", ".chd", ".zip")
                CorePath   = "/data/user/0/com.retroarch.aarch64/cores/snes9x_libretro_android.so"
                CoreName   = "Nintendo - SNES / SFC (Snes9x)"
                DbName     = "Nintendo - Super Nintendo Entertainment System.lpl"
            },
            @{
                Label      = "Nintendo 64"
                RomSubdir  = "n64"
                Extensions = @(".z64", ".n64", ".v64", ".zip")
                CorePath   = "/data/user/0/com.retroarch.aarch64/cores/mupen64plus_next_gles3_libretro_android.so"
                CoreName   = "Nintendo - Nintendo 64 (Mupen64Plus-Next GLES3)"
                DbName     = "Nintendo - Nintendo 64.lpl"
            }
        )

        foreach ($Pl in $RetroArchPlaylists) {
            $LocalRomDir = Join-Path $BaseDir "data\roms\$($Pl.RomSubdir)"
            $LocalRoms = @()
            if (Test-Path $LocalRomDir) {
                $LocalRoms = @(Get-ChildItem -Path $LocalRomDir -File | Where-Object { $_.Extension -in $Pl.Extensions })
            }

            if ($LocalRoms.Count -gt 0) {
                Write-Host "Gerando playlist automática de $($Pl.Label) ($($LocalRoms.Count) títulos)..." -ForegroundColor Gray
                $PlaylistItems = @()

                foreach ($Rom in $LocalRoms) {
                    $CleanLabel = $Rom.BaseName -replace "_", " "
                    $PlaylistItems += @{
                        path      = "$TargetDevicePath/roms/$($Pl.RomSubdir)/$($Rom.Name)"
                        label     = $CleanLabel
                        core_path = $Pl.CorePath
                        core_name = $Pl.CoreName
                        crc32     = "DETECT"
                        db_name   = $Pl.DbName
                    }
                }

                $PlaylistObj = @{
                    version              = "1.5"
                    default_core_path    = $Pl.CorePath
                    default_core_name    = $Pl.CoreName
                    label_display_mode   = 0
                    right_thumbnail_mode = 0
                    left_thumbnail_mode  = 0
                    sort_mode            = 0
                    items                = $PlaylistItems
                }

                $TempPlaylist = Join-Path $CoreCacheDir $Pl.DbName
                $PlaylistObj | ConvertTo-Json -Depth 5 | Set-Content -Path $TempPlaylist -Encoding utf8
                & adb @AdbArgs push $TempPlaylist "/storage/emulated/0/RetroArch/playlists/$($Pl.DbName)" 2>$null | Out-Null
                & adb @AdbArgs push $TempPlaylist "/storage/emulated/0/Android/data/com.retroarch.aarch64/files/playlists/$($Pl.DbName)" 2>$null | Out-Null
            }
        }

        Write-Host ">>> [Aviso RetroArch] Segurança Android (Linker W^X sem Root):" -ForegroundColor Cyan
        Write-Host "    As playlists de SNES e N64 foram geradas e vinculadas aos respectivos núcleos." -ForegroundColor Gray
        Write-Host "    Por restrição do Android, os binários (.so) devem residir no namespace interno do app." -ForegroundColor Gray
        Write-Host "    Etapa única necessária no celular: Menu Principal -> Atualizador Online -> Baixar Núcleo -> Snes9x e Mupen64Plus-Next GLES3." -ForegroundColor Yellow
    }

    # 7.3 Injeção Direta - PPSSPP (PSP)
    $PpssppIni = Join-Path $AndroidTemplatesDir "ppsspp.ini"
    if (Test-Path $PpssppIni) {
        Write-Host "Aplicando configuração: PPSSPP..." -ForegroundColor Gray
        & adb @AdbArgs shell "mkdir -p /storage/emulated/0/PSP/SYSTEM /storage/emulated/0/Android/data/org.ppsspp.ppsspp/files/PSP/SYSTEM" 2>$null | Out-Null
        Push-AndroidConfigIfNeeded $PpssppIni "/storage/emulated/0/PSP/SYSTEM/ppsspp.ini" -ForceOverwrite:$ForceTemplates
        Push-AndroidConfigIfNeeded $PpssppIni "/storage/emulated/0/Android/data/org.ppsspp.ppsspp/files/PSP/SYSTEM/ppsspp.ini" -ForceOverwrite:$ForceTemplates
    }

    # Na primeira execução o próprio Dolphin deve criar sua configuração.
    # Preserva instalações existentes mesmo quando -ForceTemplates é solicitado.
    $DolphinIni = Join-Path $AndroidTemplatesDir "Dolphin.ini"
    $DolphinConfig = "/storage/emulated/0/Android/data/org.dolphinemu.dolphinemu/files/Config/Dolphin.ini"
    if ((Test-Path $DolphinIni) -and ($InstalledPackages -contains "org.dolphinemu.dolphinemu")) {
        $ConfigStatus = (& adb @AdbArgs shell "if [ -f '$DolphinConfig' ]; then echo present; else echo missing; fi") | Out-String
        if ($LASTEXITCODE -ne 0 -or $ConfigStatus.Trim() -notin @("present", "missing")) {
            Write-Warning "Não foi possível verificar a configuração do Dolphin; perfil inicial não aplicado."
        } elseif ($ConfigStatus.Trim() -eq "present") {
            Write-Host "Dolphin: configuração existente preservada." -ForegroundColor Gray
        } else {
            $Running = (& adb @AdbArgs shell "pidof org.dolphinemu.dolphinemu") | Out-String
            if ($Running.Trim()) {
                Write-Warning "Dolphin em execução sem configuração acessível; perfil inicial não aplicado."
            } else {
                & adb @AdbArgs shell "am start -n org.dolphinemu.dolphinemu/.ui.main.MainActivity" | Out-Null
                $Created = $false
                if ($LASTEXITCODE -eq 0) {
                    for ($Attempt = 0; $Attempt -lt 15; $Attempt++) {
                        Start-Sleep -Seconds 1
                        $Check = (& adb @AdbArgs shell "if [ -f '$DolphinConfig' ]; then echo present; fi") | Out-String
                        if ($LASTEXITCODE -eq 0 -and $Check.Trim() -eq "present") { $Created = $true; break }
                    }
                }
                if (-not $Created) {
                    Write-Warning "Dolphin não criou a configuração; conclua a inicialização no aparelho e configure o perfil manualmente."
                } else {
                    & adb @AdbArgs shell "am force-stop org.dolphinemu.dolphinemu" | Out-Null
                    if ($LASTEXITCODE -ne 0) {
                        Write-Warning "Não foi possível encerrar o Dolphin; perfil inicial não aplicado."
                    } else {
                        # Alterar o arquivo existente por redirecionamento conserva seu proprietário.
                        $Original = (& adb @AdbArgs shell "cat '$DolphinConfig'") | Out-String
                        if ($LASTEXITCODE -ne 0) {
                            Write-Warning "Não foi possível ler a configuração criada pelo Dolphin."
                        } else {
                            $LocalProfile = [System.IO.Path]::GetTempFileName()
                            $LocalBackup = [System.IO.Path]::GetTempFileName()
                            $RemoteProfile = "/data/local/tmp/retrogame-dolphin-$([guid]::NewGuid().ToString('N')).ini"
                            $RemoteBackup = "$RemoteProfile.bak"
                            $WriteAttempted = $false
                            try {
                                [System.IO.File]::WriteAllText($LocalBackup, $Original, [System.Text.UTF8Encoding]::new($false))
                                # Mesclar apenas chaves do perfil, preservando as demais preferências.
                                $Merged = [System.Collections.Generic.List[string]]::new()
                                $Merged.AddRange([string[]]($Original -split "`r?`n"))
                                $Section = ""
                                foreach ($Line in (Get-Content -LiteralPath $DolphinIni)) {
                                    if ($Line -match '^\s*\[([^]]+)\]\s*$') { $Section = $Matches[1]; continue }
                                    if (-not $Section -or $Line -notmatch '^\s*([^#;=]+?)\s*=') { continue }
                                    $Key = $Matches[1].Trim()
                                    $Start = -1
                                    for ($i = 0; $i -lt $Merged.Count; $i++) {
                                        if ($Merged[$i] -match ('^\s*\[' + [regex]::Escape($Section) + '\]\s*$')) { $Start = $i; break }
                                    }
                                    if ($Start -lt 0) {
                                        $Merged.Add("[$Section]")
                                        $Merged.Add($Line)
                                        continue
                                    }
                                    $End = $Start + 1
                                    $Found = $false
                                    while ($End -lt $Merged.Count -and $Merged[$End] -notmatch '^\s*\[') {
                                        if ($Merged[$End] -match ('^\s*' + [regex]::Escape($Key) + '\s*=')) {
                                            $Merged[$End] = $Line
                                            $Found = $true
                                            break
                                        }
                                        $End++
                                    }
                                    if (-not $Found) { $Merged.Insert($End, $Line) }
                                }
                                [System.IO.File]::WriteAllText($LocalProfile, ($Merged -join "`n"), [System.Text.UTF8Encoding]::new($false))
                                & adb @AdbArgs push $LocalBackup $RemoteBackup | Out-Null
                                if ($LASTEXITCODE -ne 0) { throw "falha ao enviar backup temporário" }
                                & adb @AdbArgs push $LocalProfile $RemoteProfile | Out-Null
                                if ($LASTEXITCODE -ne 0) { throw "falha ao enviar perfil temporário" }
                                $WriteAttempted = $true
                                & adb @AdbArgs shell "cat '$RemoteProfile' > '$DolphinConfig'" | Out-Null
                                if ($LASTEXITCODE -ne 0) { throw "falha ao aplicar perfil ao arquivo existente" }
                                $Applied = (& adb @AdbArgs shell "cat '$DolphinConfig'") | Out-String
                                if ($LASTEXITCODE -ne 0 -or $Applied -notmatch '(?m)^GFXBackend\s*=\s*Vulkan\s*$') {
                                    throw "não foi possível confirmar o perfil aplicado"
                                }
                                Write-Host "Dolphin: perfil inicial aplicado à configuração criada pelo aplicativo." -ForegroundColor Green
                            } catch {
                                if ($WriteAttempted) {
                                    & adb @AdbArgs shell "cat '$RemoteBackup' > '$DolphinConfig'" | Out-Null
                                    if ($LASTEXITCODE -ne 0) {
                                        Write-Warning "Não foi possível restaurar o arquivo original automaticamente."
                                    }
                                }
                                Write-Warning "Perfil inicial do Dolphin não confirmado: $($_.Exception.Message). Backup local: $LocalBackup"
                                $LocalBackup = $null
                            } finally {
                                & adb @AdbArgs shell "rm -f '$RemoteProfile'" | Out-Null
                                & adb @AdbArgs shell "rm -f '$RemoteBackup'" | Out-Null
                                Remove-Item -LiteralPath $LocalProfile -Force -ErrorAction SilentlyContinue
                                if ($LocalBackup) { Remove-Item -LiteralPath $LocalBackup -Force -ErrorAction SilentlyContinue }
                            }
                        }
                    }
                }
            }
        }
    }
    Write-Host "Dolphin: adicione as pastas de jogos pelo seletor do Android." -ForegroundColor Yellow

    # 7.5 Injeção Direta - Flycast (Dreamcast)
    $FlycastCfg = Join-Path $AndroidTemplatesDir "emu.cfg"
    if (Test-Path $FlycastCfg) {
        Write-Host "Aplicando configuração: Flycast..." -ForegroundColor Gray
        & adb @AdbArgs shell "mkdir -p /storage/emulated/0/Flycast" 2>$null | Out-Null
        Push-AndroidConfigIfNeeded $FlycastCfg "/storage/emulated/0/Flycast/emu.cfg" -ForceOverwrite:$ForceTemplates
        foreach ($Pkg in @("com.flycast.emulator", "com.flyinghead.flycast")) {
            & adb @AdbArgs shell "mkdir -p /storage/emulated/0/Android/data/$Pkg/files" 2>$null | Out-Null
            Push-AndroidConfigIfNeeded $FlycastCfg "/storage/emulated/0/Android/data/$Pkg/files/emu.cfg" -ForceOverwrite:$ForceTemplates
        }
    }

    # 7.6 DuckStation e NetherSX2 (Carga de perfis nos diretórios de staging do app)
    $DuckSettings = Join-Path $AndroidTemplatesDir "duckstation_settings.ini"
    if (Test-Path $DuckSettings) {
        Write-Host "Aplicando configuração: DuckStation..." -ForegroundColor Gray
        & adb @AdbArgs shell "mkdir -p /storage/emulated/0/Android/data/com.github.stenzek.duckstation/files" 2>$null | Out-Null
        Push-AndroidConfigIfNeeded $DuckSettings "/storage/emulated/0/Android/data/com.github.stenzek.duckstation/files/settings.ini" -ForceOverwrite:$ForceTemplates
    }
    $NetherSettings = Join-Path $AndroidTemplatesDir "nethersx2_settings.ini"
    if (Test-Path $NetherSettings) {
        Write-Host "Aplicando configuração: NetherSX2..." -ForegroundColor Gray
        foreach ($Pkg in @("com.theemulatorapp.nethersx2", "xyz.nethersx2.android", "xyz.aethersx2.android")) {
            & adb @AdbArgs shell "mkdir -p /storage/emulated/0/Android/data/$Pkg/files" 2>$null | Out-Null
            Push-AndroidConfigIfNeeded $NetherSettings "/storage/emulated/0/Android/data/$Pkg/files/PCSX2.ini" -ForceOverwrite:$ForceTemplates
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
