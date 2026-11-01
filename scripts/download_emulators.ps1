[CmdletBinding()]
param (
    [string[]]$Emulators = @("retroarch", "duckstation", "pcsx2", "ppsspp", "dolphin", "flycast"),
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot
$BinDir  = Join-Path $BaseDir "bin"
$DataDir = Join-Path $BaseDir "data"
$TempDir = Join-Path $BaseDir "tools\temp_downloads"

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
        [string[]]$CoreNames = @("snes9x")
    )

    $CoreDir = Join-Path $RetroArchFolder "cores"
    if (-not (Test-Path $CoreDir)) {
        New-Item -ItemType Directory -Path $CoreDir -Force | Out-Null
    }

    foreach ($Core in $CoreNames) {
        $CoreDll = Join-Path $CoreDir "${Core}_libretro.dll"
        if ((Test-Path $CoreDll) -and -not $Force) {
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

Write-Host "=== Download e Provisionamento de Emuladores Portáteis no Windows 11 ===" -ForegroundColor Green

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

foreach ($Emu in $Emulators) {
    $EmuName = $Emu.ToLower().Trim()
    $TargetFolder = Join-Path $BinDir $EmuName

    if (-not (Test-Path $TargetFolder)) {
        New-Item -ItemType Directory -Path $TargetFolder -Force | Out-Null
    }

    Write-Host "`n--- Processando: $EmuName ---" -ForegroundColor Cyan

    # Verificação de existência prévia
    $ExistingExe = Get-ChildItem -Path $TargetFolder -Filter "*.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch "updater|setup|unins|vcredist" } |
        Select-Object -First 1

    if ($ExistingExe -and -not $Force) {
        Write-Host "Emulador já presente em '$($ExistingExe.FullName)' (Use -Force para reinstalar)." -ForegroundColor Gray
        if ($EmuName -eq "retroarch") {
            # Garante que os cores Libretro homologados estejam presentes mesmo se o RetroArch já existir
            Install-RetroArchCores -RetroArchFolder $TargetFolder
        }
        continue
    }

    try {
        switch ($EmuName) {
            "duckstation" {
                Write-Host "Consultando release oficial do DuckStation via GitHub API..." -ForegroundColor Gray
                $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/stenzek/duckstation/releases/latest" -Headers $Headers
                $Asset = $Release.assets | Where-Object { $_.name -match "duckstation-windows-x64-release\.zip" } | Select-Object -First 1
                if (-not $Asset) {
                    $Asset = $Release.assets | Where-Object { $_.name -match "windows.*x64.*zip" } | Select-Object -First 1
                }
                $Url = $Asset.browser_download_url
                $ArchiveFile = Join-Path $TempDir "duckstation.zip"

                Write-Host "Baixando DuckStation ($($Asset.name))..." -ForegroundColor Yellow
                Invoke-WebRequest -Uri $Url -OutFile $ArchiveFile -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
                Expand-ArchivePortable -ArchiveFile $ArchiveFile -DestinationPath $TargetFolder
                Flatten-SingleDirectory -DirectoryPath $TargetFolder
                New-Item -ItemType File -Path (Join-Path $TargetFolder "portable.txt") -Force | Out-Null
            }

            "pcsx2" {
                Write-Host "Consultando release oficial do PCSX2 v2.x via GitHub API..." -ForegroundColor Gray
                $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/PCSX2/pcsx2/releases/latest" -Headers $Headers
                $Asset = $Release.assets | Where-Object { $_.name -match "windows-x64-Qt\.7z" -and $_.name -notmatch "symbols" } | Select-Object -First 1
                if (-not $Asset) {
                    $Asset = $Release.assets | Where-Object { $_.name -match "windows.*Qt.*7z" -and $_.name -notmatch "symbols" } | Select-Object -First 1
                }
                $Url = $Asset.browser_download_url
                $ArchiveFile = Join-Path $TempDir "pcsx2.7z"

                Write-Host "Baixando PCSX2 ($($Asset.name))..." -ForegroundColor Yellow
                Invoke-WebRequest -Uri $Url -OutFile $ArchiveFile -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
                Expand-ArchivePortable -ArchiveFile $ArchiveFile -DestinationPath $TargetFolder
                Flatten-SingleDirectory -DirectoryPath $TargetFolder
                New-Item -ItemType File -Path (Join-Path $TargetFolder "portable.txt") -Force | Out-Null
            }

            "ppsspp" {
                Write-Host "Consultando release oficial do PPSSPP via GitHub API..." -ForegroundColor Gray
                $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/hrydgard/ppsspp/releases/latest" -Headers $Headers
                $Asset = $Release.assets | Where-Object { $_.name -match "Windows-x64\.zip" } | Select-Object -First 1
                if (-not $Asset) {
                    $Asset = $Release.assets | Where-Object { $_.name -match "Windows.*zip" -and $_.name -notmatch "ARM64" } | Select-Object -First 1
                }
                $Url = $Asset.browser_download_url
                $ArchiveFile = Join-Path $TempDir "ppsspp.zip"

                Write-Host "Baixando PPSSPP ($($Asset.name))..." -ForegroundColor Yellow
                Invoke-WebRequest -Uri $Url -OutFile $ArchiveFile -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
                Expand-ArchivePortable -ArchiveFile $ArchiveFile -DestinationPath $TargetFolder
                Flatten-SingleDirectory -DirectoryPath $TargetFolder
                
                # Garantir estrutura do memstick
                $PpssppMemstick = Join-Path $TargetFolder "memstick"
                New-Item -ItemType Directory -Path $PpssppMemstick -Force | Out-Null
            }

            "dolphin" {
                Write-Host "Consultando versão oficial do Dolphin..." -ForegroundColor Gray
                $DolphinMeta = Invoke-RestMethod -Uri "https://dolphin-emu.org/update/latest/beta" -Headers $Headers
                $Asset = $DolphinMeta.artifacts | Where-Object { $_.system -eq "Windows x64" } | Select-Object -First 1
                $Url = $Asset.url
                $ArchiveFile = Join-Path $TempDir "dolphin.7z"

                Write-Host "Baixando Dolphin ($($DolphinMeta.shortrev))..." -ForegroundColor Yellow
                Invoke-WebRequest -Uri $Url -OutFile $ArchiveFile -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
                Expand-ArchivePortable -ArchiveFile $ArchiveFile -DestinationPath $TargetFolder
                Flatten-SingleDirectory -DirectoryPath $TargetFolder
                New-Item -ItemType File -Path (Join-Path $TargetFolder "portable.txt") -Force | Out-Null
            }

            "flycast" {
                Write-Host "Consultando release oficial do Flycast via GitHub API..." -ForegroundColor Gray
                $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/flyinghead/flycast/releases/latest" -Headers $Headers
                $Asset = $Release.assets | Where-Object { $_.name -match "win64.*\.zip" } | Select-Object -First 1
                $Url = $Asset.browser_download_url
                $ArchiveFile = Join-Path $TempDir "flycast.zip"

                Write-Host "Baixando Flycast ($($Asset.name))..." -ForegroundColor Yellow
                Invoke-WebRequest -Uri $Url -OutFile $ArchiveFile -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
                Expand-ArchivePortable -ArchiveFile $ArchiveFile -DestinationPath $TargetFolder
                Flatten-SingleDirectory -DirectoryPath $TargetFolder
            }

            "retroarch" {
                Write-Host "Consultando pacote portátil do RetroArch..." -ForegroundColor Gray
                $Url = "https://buildbot.libretro.com/nightly/windows/x86_64/RetroArch.7z"
                $ArchiveFile = Join-Path $TempDir "retroarch.7z"

                Write-Host "Baixando RetroArch 64-bit..." -ForegroundColor Yellow
                Invoke-WebRequest -Uri $Url -OutFile $ArchiveFile -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
                Expand-ArchivePortable -ArchiveFile $ArchiveFile -DestinationPath $TargetFolder
                Flatten-SingleDirectory -DirectoryPath $TargetFolder

                # Download automatizado de Cores Libretro homologados (SNES, etc.)
                Install-RetroArchCores -RetroArchFolder $TargetFolder
            }

            default {
                Write-Warning "Emulador desconhecido: '$EmuName'. Emuladores suportados: retroarch, duckstation, pcsx2, ppsspp, dolphin, flycast"
            }
        }
        Write-Host ">>> $EmuName provisionado com sucesso em '$TargetFolder'!" -ForegroundColor Green
    } catch {
        Write-Error "Falha ao processar o emulador '$EmuName': $($_.Exception.Message)"
    }
}

# 3. Limpeza de arquivos temporários de download
if (Test-Path $TempDir) {
    Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "`n=== Verificação Final dos Executáveis em bin/ ===" -ForegroundColor Green
foreach ($Emu in @("retroarch", "duckstation", "pcsx2", "ppsspp", "dolphin", "flycast")) {
    $Folder = Join-Path $BinDir $Emu
    $Exe = Get-ChildItem -Path $Folder -Filter "*.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch "updater|setup|unins|vcredist" } |
        Select-Object -First 1

    if ($Exe) {
        if ($Emu -eq "retroarch") {
            $Core = Join-Path $Folder "cores\snes9x_libretro.dll"
            if (Test-Path $Core) {
                Write-Host "  [OK] $Emu -> $($Exe.Name) (Core snes9x: OK)" -ForegroundColor Green
            } else {
                Write-Host "  [AVISO] $Emu -> $($Exe.Name) (Core snes9x ausente em cores/)" -ForegroundColor Yellow
            }
        } else {
            Write-Host "  [OK] $Emu -> $($Exe.Name)" -ForegroundColor Green
        }
    } else {
        Write-Host "  [PENDENTE] $Emu -> Nenhum executável encontrado em '$Folder'" -ForegroundColor Yellow
    }
}
