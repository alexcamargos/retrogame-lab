[CmdletBinding()]
param (
    [string[]]$Emulators = @("retroarch", "duckstation", "pcsx2", "ppsspp", "dolphin", "flycast"),
    [switch]$CheckOnly = $false,
    [switch]$Update = $false,
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot
$BinDir  = Join-Path $BaseDir "bin"
$DataDir = Join-Path $BaseDir "data"
$TempDir = Join-Path $BaseDir "tools\temp_downloads"
$VersionsFile = Join-Path $BinDir ".versions.json"

if (-not (Test-Path $TempDir)) {
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
}

# 1. Localização do 7-Zip para descompactação (.7z e .zip)
$7zExe = $null
$7zCmd = Get-Command "7z.exe" -ErrorAction SilentlyContinue
if (-not $7zCmd) { $7zCmd = Get-Command "7z" -ErrorAction SilentlyContinue }

if ($7zCmd) {
    $7zExe = $7zCmd.Source
} elseif (Test-Path "C:\Program Files\7-Zip\7z.exe") {
    $7zExe = "C:\Program Files\7-Zip\7z.exe"
} elseif (Test-Path "C:\Program Files (x86)\7-Zip\7z.exe") {
    $7zExe = "C:\Program Files (x86)\7-Zip\7z.exe"
}

function Expand-ArchivePortable {
    param (
        [string]$ArchiveFile,
        [string]$DestinationPath
    )

    if (-not (Test-Path $DestinationPath)) {
        New-Item -ItemType Directory -Path $DestinationPath -Force | Out-Null
    }

    if ($7zExe) {
        & $7zExe x -y "-o$DestinationPath" $ArchiveFile | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Erro ao descompactar '$ArchiveFile' com 7-Zip (código: $LASTEXITCODE)."
        }
    } else {
        if ($ArchiveFile.EndsWith(".zip", [System.StringComparison]::OrdinalIgnoreCase)) {
            Expand-Archive -Path $ArchiveFile -DestinationPath $DestinationPath -Force
        } else {
            throw "7-Zip não encontrado. Necessário para descompactar arquivos .7z. Execute 'winget install 7zip.7zip' ou '.\retrogame bootstrap'."
        }
    }
}

function Flatten-SingleDirectory {
    param (
        [string]$DirectoryPath
    )

    $Items = Get-ChildItem -Path $DirectoryPath -Force
    # Ignora arquivos de controle de portabilidade já criados pelo bootstrap
    $FilteredItems = $Items | Where-Object { $_.Name -notin @("portable.txt", "settings.ini", "PCSX2.ini", "inis", "memstick", "cores") }

    if ($FilteredItems.Count -eq 1 -and $FilteredItems[0].PSIsContainer) {
        $SubDir = $FilteredItems[0].FullName
        Get-ChildItem -Path $SubDir -Force | ForEach-Object {
            $TargetItem = Join-Path $DirectoryPath $_.Name
            if (Test-Path $TargetItem) {
                Remove-Item -Path $TargetItem -Recurse -Force -ErrorAction SilentlyContinue
            }
            Move-Item -Path $_.FullName -Destination $DirectoryPath -Force
        }
        Remove-Item -Path $SubDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Install-RetroArchCores {
    param (
        [string]$RetroArchFolder,
        [string[]]$CoreNames = @("snes9x"),
        [switch]$ForceDownload = $false
    )

    $CoreDir = Join-Path $RetroArchFolder "cores"
    if (-not (Test-Path $CoreDir)) {
        New-Item -ItemType Directory -Path $CoreDir -Force | Out-Null
    }

    foreach ($Core in $CoreNames) {
        $CoreDll = Join-Path $CoreDir "${Core}_libretro.dll"
        if ((Test-Path $CoreDll) -and -not $ForceDownload) {
            Write-Host "Core Libretro '${Core}' já presente em '$CoreDll'." -ForegroundColor Gray
            continue
        }

        Write-Host "Baixando e instalando Core Libretro oficial: ${Core}..." -ForegroundColor Yellow
        $CoreUrl = "https://buildbot.libretro.com/nightly/windows/x86_64/latest/${Core}_libretro.dll.zip"
        $ZipPath = Join-Path $TempDir "${Core}_libretro.dll.zip"

        try {
            Invoke-WebRequest -Uri $CoreUrl -OutFile $ZipPath -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
            Expand-ArchivePortable -ArchiveFile $ZipPath -DestinationPath $CoreDir
            if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue }
            Write-Host ">>> Core '${Core}' instalado com sucesso em '$CoreDir'!" -ForegroundColor Green
        } catch {
            Write-Warning "Falha ao baixar core '${Core}': $($_.Exception.Message)"
        }
    }
}

function Get-InstalledVersionsManifest {
    if (Test-Path $VersionsFile) {
        try {
            $Content = Get-Content $VersionsFile -Raw -ErrorAction SilentlyContinue
            if ($Content) {
                return ($Content | ConvertFrom-Json)
            }
        } catch {
            Write-Warning "Manifesto .versions.json corrompido. Será regerado."
        }
    }
    return [PSCustomObject]@{}
}

function Save-InstalledVersionEntry {
    param (
        [string]$EmuKey,
        [string]$VersionString
    )

    $Manifest = Get-InstalledVersionsManifest
    $Now = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssZ")

    if ($Manifest.PSObject.Properties[$EmuKey]) {
        $Manifest.$EmuKey.version = $VersionString
        $Manifest.$EmuKey.updated_at = $Now
    } else {
        $Manifest | Add-Member -MemberType NoteProperty -Name $EmuKey -Value ([PSCustomObject]@{
            version = $VersionString
            updated_at = $Now
        }) -Force
    }

    $Manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $VersionsFile -Force
}

$Headers = @{ "User-Agent" = "RetroGameLab-Bootstrap/1.0" }

# Normaliza lista de emuladores permitindo separação por vírgula ou array
$ParsedEmulators = @()
foreach ($Entry in $Emulators) {
    if ($Entry -match ",") {
        $ParsedEmulators += ($Entry -split ",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    } else {
        $ParsedEmulators += $Entry.Trim()
    }
}
$Emulators = $ParsedEmulators

# Carrega manifesto local
$LocalManifest = Get-InstalledVersionsManifest

Write-Host "=== RetroGame Lab: Gerenciador de Emuladores e Atualizações ===" -ForegroundColor Green

# 2. Resolução Dinâmica de Metadados Remotos
$RemoteCatalog = [ordered]@{}

Write-Host "`n>>> Consultando repositórios e buildbots oficiais..." -ForegroundColor Cyan

foreach ($Emu in $Emulators) {
    $EmuName = $Emu.ToLower().Trim()
    $TargetFolder = Join-Path $BinDir $EmuName

    $ExistingExe = Get-ChildItem -Path $TargetFolder -Filter "*.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch "updater|setup|unins|vcredist" } |
        Select-Object -First 1

    $InstalledVer = if ($LocalManifest.PSObject.Properties[$EmuName]) {
        $LocalManifest.$EmuName.version
    } elseif ($ExistingExe) {
        "instalado (versão não registrada)"
    } else {
        "não instalado"
    }

    try {
        switch ($EmuName) {
            "duckstation" {
                $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/stenzek/duckstation/releases/latest" -Headers $Headers
                $Asset = $Release.assets | Where-Object { $_.name -match "duckstation-windows-x64-release\.zip" } | Select-Object -First 1
                if (-not $Asset) {
                    $Asset = $Release.assets | Where-Object { $_.name -match "windows.*x64.*zip" } | Select-Object -First 1
                }
                $DateTag = if ($Asset.updated_at -is [System.DateTime]) { 
                    $Asset.updated_at.ToString("yyyy-MM-dd") 
                } elseif ($Asset.updated_at) { 
                    $Asset.updated_at.ToString().Substring(0, 10) 
                } else { 
                    "latest" 
                }
                $RemoteVer = "latest ($DateTag)"
                $RemoteCatalog[$EmuName] = [ordered]@{
                    Name = "DuckStation (PS1)"
                    RemoteVersion = $RemoteVer
                    InstalledVersion = $InstalledVer
                    Url = $Asset.browser_download_url
                    Archive = "duckstation.zip"
                    Type = "zip"
                    ExistingExe = $ExistingExe
                }
            }

            "pcsx2" {
                $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/PCSX2/pcsx2/releases/latest" -Headers $Headers
                $Asset = $Release.assets | Where-Object { $_.name -match "windows-x64-Qt\.7z" -and $_.name -notmatch "symbols" } | Select-Object -First 1
                if (-not $Asset) {
                    $Asset = $Release.assets | Where-Object { $_.name -match "windows.*Qt.*7z" -and $_.name -notmatch "symbols" } | Select-Object -First 1
                }
                $RemoteCatalog[$EmuName] = [ordered]@{
                    Name = "PCSX2 v2.x (PS2)"
                    RemoteVersion = $Release.tag_name
                    InstalledVersion = $InstalledVer
                    Url = $Asset.browser_download_url
                    Archive = "pcsx2.7z"
                    Type = "7z"
                    ExistingExe = $ExistingExe
                }
            }

            "ppsspp" {
                $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/hrydgard/ppsspp/releases/latest" -Headers $Headers
                $Asset = $Release.assets | Where-Object { $_.name -match "Windows-x64\.zip" } | Select-Object -First 1
                if (-not $Asset) {
                    $Asset = $Release.assets | Where-Object { $_.name -match "Windows.*zip" -and $_.name -notmatch "ARM64" } | Select-Object -First 1
                }
                $RemoteCatalog[$EmuName] = [ordered]@{
                    Name = "PPSSPP (PSP)"
                    RemoteVersion = $Release.tag_name
                    InstalledVersion = $InstalledVer
                    Url = $Asset.browser_download_url
                    Archive = "ppsspp.zip"
                    Type = "zip"
                    ExistingExe = $ExistingExe
                }
            }

            "dolphin" {
                $DolphinMeta = Invoke-RestMethod -Uri "https://dolphin-emu.org/update/latest/beta" -Headers $Headers
                $Asset = $DolphinMeta.artifacts | Where-Object { $_.system -eq "Windows x64" } | Select-Object -First 1
                $RemoteCatalog[$EmuName] = [ordered]@{
                    Name = "Dolphin (GameCube/Wii)"
                    RemoteVersion = $DolphinMeta.shortrev
                    InstalledVersion = $InstalledVer
                    Url = $Asset.url
                    Archive = "dolphin.7z"
                    Type = "7z"
                    ExistingExe = $ExistingExe
                }
            }

            "flycast" {
                $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/flyinghead/flycast/releases/latest" -Headers $Headers
                $Asset = $Release.assets | Where-Object { $_.name -match "win64.*\.zip" } | Select-Object -First 1
                $RemoteCatalog[$EmuName] = [ordered]@{
                    Name = "Flycast (Dreamcast)"
                    RemoteVersion = $Release.tag_name
                    InstalledVersion = $InstalledVer
                    Url = $Asset.browser_download_url
                    Archive = "flycast.zip"
                    Type = "zip"
                    ExistingExe = $ExistingExe
                }
            }

            "retroarch" {
                $RaRelease = Invoke-RestMethod -Uri "https://api.github.com/repos/libretro/RetroArch/releases/latest" -Headers $Headers
                $RemoteVer = if ($RaRelease.tag_name) { $RaRelease.tag_name } else { "stable" }
                $RemoteCatalog[$EmuName] = [ordered]@{
                    Name = "RetroArch (SNES/2D)"
                    RemoteVersion = $RemoteVer
                    InstalledVersion = $InstalledVer
                    Url = "https://buildbot.libretro.com/nightly/windows/x86_64/RetroArch.7z"
                    Archive = "retroarch.7z"
                    Type = "7z"
                    ExistingExe = $ExistingExe
                }
            }
        }
    } catch {
        Write-Warning "Falha ao obter metadados de '$EmuName': $($_.Exception.Message)"
    }
}

# 3. Exibição da Tabela de Auditoria de Versões
Write-Host "`nStatus Comparativo de Versões:" -ForegroundColor Cyan
$Report = @()
$UpdatesAvailable = 0

foreach ($Key in $RemoteCatalog.Keys) {
    $Info = $RemoteCatalog[$Key]
    $Status = "Atualizado"
    $NeedsWork = $false

    if (-not $Info.ExistingExe) {
        $Status = "Não Instalado"
        $NeedsWork = $true
    } elseif ($Info.InstalledVersion -eq "instalado (versão não registrada)") {
        # Registra a versão atual para manter o tracking ativo
        Save-InstalledVersionEntry -EmuKey $Key -VersionString $Info.RemoteVersion
        $Info.InstalledVersion = $Info.RemoteVersion
        $Status = "Atualizado"
    } elseif ($Info.InstalledVersion -ne $Info.RemoteVersion) {
        $Status = "Atualização Disponível"
        $NeedsWork = $true
        $UpdatesAvailable++
    }

    $Info["Status"] = $Status
    $Info["NeedsWork"] = $NeedsWork

    $Report += [PSCustomObject]@{
        "Emulador"         = $Info.Name
        "Versão Instalada" = $Info.InstalledVersion
        "Versão Remota"    = $Info.RemoteVersion
        "Status"           = $Status
    }
}

$Report | Format-Table -AutoSize | Out-String | Write-Host -ForegroundColor Gray

# Se foi solicitado apenas checagem, exibe orientações e encerra
if ($CheckOnly) {
    if ($UpdatesAvailable -gt 0) {
        Write-Host "Há $UpdatesAvailable emulador(es) com atualização disponível!" -ForegroundColor Yellow
        Write-Host "Para atualizar, execute: .\retrogame update-emulators`n" -ForegroundColor Cyan
    } else {
        Write-Host "Todos os emuladores instalados estão na versão mais recente homologada.`n" -ForegroundColor Green
    }
    exit 0
}

# 4. Execução de Download / Atualização
Write-Host "`n>>> Processando instalação/atualização de emuladores..." -ForegroundColor Cyan

foreach ($EmuName in $RemoteCatalog.Keys) {
    $Info = $RemoteCatalog[$EmuName]
    $TargetFolder = Join-Path $BinDir $EmuName

    $ShouldDownload = $false
    if ($Force) {
        $ShouldDownload = $true
    } elseif ($Update) {
        if ($Info.NeedsWork) { $ShouldDownload = $true }
    } else {
        # Modo padrão de download-emulators: instala se faltar, atualiza se versão não registrada ou desatualizada
        if ($Info.NeedsWork) { $ShouldDownload = $true }
    }

    if (-not $ShouldDownload) {
        Write-Host "`n--- ${EmuName}: Já está na versão mais recente ($($Info.InstalledVersion)) ---" -ForegroundColor Gray
        if ($EmuName -eq "retroarch") {
            Install-RetroArchCores -RetroArchFolder $TargetFolder
        }
        continue
    }

    Write-Host "`n--- Processando: $EmuName ($($Info.Status)) ---" -ForegroundColor Yellow
    $ArchiveFile = Join-Path $TempDir $Info.Archive

    try {
        Write-Host "Baixando $($Info.Name) ($($Info.RemoteVersion))..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $Info.Url -OutFile $ArchiveFile -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
        Expand-ArchivePortable -ArchiveFile $ArchiveFile -DestinationPath $TargetFolder
        Flatten-SingleDirectory -DirectoryPath $TargetFolder

        # Marcadores de portabilidade e ações específicas
        if ($EmuName -in @("duckstation", "pcsx2", "dolphin")) {
            New-Item -ItemType File -Path (Join-Path $TargetFolder "portable.txt") -Force | Out-Null
        } elseif ($EmuName -eq "ppsspp") {
            $PpssppMemstick = Join-Path $TargetFolder "memstick"
            New-Item -ItemType Directory -Path $PpssppMemstick -Force | Out-Null
        } elseif ($EmuName -eq "retroarch") {
            Install-RetroArchCores -RetroArchFolder $TargetFolder -ForceDownload:$Force
        }

        # Registra a versão instalada no manifesto local
        Save-InstalledVersionEntry -EmuKey $EmuName -VersionString $Info.RemoteVersion
        Write-Host ">>> $($Info.Name) atualizado para $($Info.RemoteVersion) com sucesso!" -ForegroundColor Green

    } catch {
        Write-Error "Falha ao processar o emulador '$EmuName': $($_.Exception.Message)"
    }
}

# 5. Limpeza de arquivos temporários de download
if (Test-Path $TempDir) {
    Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "`n=== Verificação Final dos Executáveis em bin/ ===" -ForegroundColor Green
$UpdatedManifest = Get-InstalledVersionsManifest
foreach ($Emu in @("retroarch", "duckstation", "pcsx2", "ppsspp", "dolphin", "flycast")) {
    $Folder = Join-Path $BinDir $Emu
    $Exe = Get-ChildItem -Path $Folder -Filter "*.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch "updater|setup|unins|vcredist" } |
        Select-Object -First 1

    $Ver = if ($UpdatedManifest.PSObject.Properties[$Emu]) { $UpdatedManifest.$Emu.version } else { "presente" }

    if ($Exe) {
        if ($Emu -eq "retroarch") {
            $Core = Join-Path $Folder "cores\snes9x_libretro.dll"
            if (Test-Path $Core) {
                Write-Host "  [OK] $Emu ($Ver) -> $($Exe.Name) (Core snes9x: OK)" -ForegroundColor Green
            } else {
                Write-Host "  [AVISO] $Emu ($Ver) -> $($Exe.Name) (Core snes9x ausente em cores/)" -ForegroundColor Yellow
            }
        } else {
            Write-Host "  [OK] $Emu ($Ver) -> $($Exe.Name)" -ForegroundColor Green
        }
    } else {
        Write-Host "  [PENDENTE] $Emu -> Nenhum executável encontrado em '$Folder'" -ForegroundColor Yellow
    }
}
