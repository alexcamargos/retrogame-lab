[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [ValidateSet("snes", "ps1", "ps2", "psp", "gc", "dc")]
    [string]$Platform,

    [Parameter(Mandatory = $true)]
    [string]$RomPath,

    [switch]$Fullscreen,
    [switch]$Windowed,

    [ValidateSet("auto", "igpu", "dgpu")]
    [string]$GpuMode = "auto"
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot
$BinDir  = Join-Path $BaseDir "bin"

# Resolução de modo de tela: fullscreen ativo por padrão a menos que -Windowed seja acionado
$IsFullscreen = $true
if ($Windowed) {
    $IsFullscreen = $false
} elseif ($PSBoundParameters.ContainsKey('Fullscreen')) {
    $IsFullscreen = [bool]$Fullscreen
}

if (-not (Test-Path $RomPath)) {
    Write-Error "Arquivo de ROM não encontrado: $RomPath"
}
$ResolvedRom = (Resolve-Path $RomPath).Path

# 0. Trava de Pré-Voo e Segurança Ativa: Normalização mandatória de nomenclatura
$RomItem = Get-Item $ResolvedRom
$RomLeaf = $RomItem.Name
if ($RomLeaf -match "[\s'""`~^!?\:;*<>|#]") {
    $Stem = [System.IO.Path]::GetFileNameWithoutExtension($RomLeaf)
    $Ext = [System.IO.Path]::GetExtension($RomLeaf)

    # Limpeza de caracteres especiais e conversão de espaços para sublinhado
    $CleanStem = $Stem -replace "['""`~^!?\:;*<>|#]", ""
    $CleanStem = $CleanStem -replace "\s+", "_"
    $CleanStem = $CleanStem -replace "_+", "_"
    $CleanStem = $CleanStem.Trim("_")

    $NewLeaf = "$CleanStem$Ext"
    $NewRomPath = Join-Path $RomItem.DirectoryName $NewLeaf

    Write-Host ">>> [SEGURANÇA ATIVA] Nome fora do padrão detectado ('$RomLeaf')." -ForegroundColor Yellow
    Write-Host ">>> Normalizando automaticamente para: '$NewLeaf'..." -ForegroundColor Cyan

    if (-not (Test-Path $NewRomPath)) {
        Rename-Item -Path $ResolvedRom -NewName $NewLeaf -Force
    }
    $ResolvedRom = (Resolve-Path $NewRomPath).Path
}

# 1. Resolução Dinâmica de Executáveis e Montagem de Argumentos
$ArgList = @()
switch ($Platform) {
    "snes" {
        $Emulator = Join-Path $BinDir "retroarch\retroarch.exe"
        $CoreDir = Join-Path $BinDir "retroarch\cores"
        $Core = Join-Path $CoreDir "snes9x_libretro.dll"
        if (-not (Test-Path $Core)) {
            Write-Host ">>> [AUTO-PROVISIONAMENTO] Core Libretro ausente ('$Core')." -ForegroundColor Yellow
            Write-Host ">>> Baixando 'snes9x_libretro.dll' automaticamente do Buildbot oficial..." -ForegroundColor Cyan
            if (-not (Test-Path $CoreDir)) { New-Item -ItemType Directory -Path $CoreDir -Force | Out-Null }
            $TempZip = Join-Path $env:TEMP "snes9x_libretro.dll.zip"
            try {
                Invoke-WebRequest -Uri "https://buildbot.libretro.com/nightly/windows/x86_64/latest/snes9x_libretro.dll.zip" -OutFile $TempZip -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
                Expand-Archive -Path $TempZip -DestinationPath $CoreDir -Force
                if (Test-Path $TempZip) { Remove-Item $TempZip -Force -ErrorAction SilentlyContinue }
                Write-Host ">>> Core snes9x instalado com sucesso em '$Core'!" -ForegroundColor Green
            } catch {
                Write-Error "Falha ao provisionar core Libretro snes9x automaticamente: $($_.Exception.Message)"
            }
        }
        $ArgList += @("-L", $Core, $ResolvedRom)
        if ($IsFullscreen) { $ArgList += "--fullscreen" }
    }
    "ps1" {
        $DuckBin = Get-ChildItem -Path (Join-Path $BinDir "duckstation") -Filter "duckstation*.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notmatch "updater|setup|unins" } |
            Select-Object -First 1
        if (-not $DuckBin) {
            $Emulator = Join-Path $BinDir "duckstation\duckstation-qt.exe"
        } else {
            $Emulator = $DuckBin.FullName
        }
        $ArgList += @("-batch", $ResolvedRom)
        if ($IsFullscreen) { $ArgList += "-fullscreen" }
    }
    "ps2" {
        # Localiza executável Qt moderno (pcsx2-qt.exe ou pcsx2-qtx64.exe), ignorando updaters
        $Pcsx2Bin = Get-ChildItem -Path (Join-Path $BinDir "pcsx2") -Filter "pcsx2*.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notmatch "updater|setup|unins" } |
            Select-Object -First 1
        if (-not $Pcsx2Bin) {
            $Emulator = Join-Path $BinDir "pcsx2\pcsx2-qt.exe"
        } else {
            $Emulator = $Pcsx2Bin.FullName
        }
        $ArgList += @("-batch")
        if ($IsFullscreen) { $ArgList += "-fullscreen" }
        $ArgList += @("--", $ResolvedRom)
    }
    "psp" {
        $PpssppBin = Get-ChildItem -Path (Join-Path $BinDir "ppsspp") -Filter "PPSSPP*.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notmatch "updater|setup|unins" } |
            Select-Object -First 1
        if (-not $PpssppBin) {
            $Emulator = Join-Path $BinDir "ppsspp\PPSSPPWindows64.exe"
        } else {
            $Emulator = $PpssppBin.FullName
        }
        $ArgList += $ResolvedRom
        if ($IsFullscreen) { $ArgList += "--fullscreen" }
    }
    "gc" {
        $DolphinBin = Get-ChildItem -Path (Join-Path $BinDir "dolphin") -Filter "Dolphin*.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notmatch "updater|setup|unins" } |
            Select-Object -First 1
        if (-not $DolphinBin) {
            $Emulator = Join-Path $BinDir "dolphin\Dolphin.exe"
        } else {
            $Emulator = $DolphinBin.FullName
        }
        # Dolphin inicia fullscreen via configuração em Dolphin.ini; flag CLI -b encerra ao sair
        $ArgList += @("-b", "-e", $ResolvedRom)
    }
    "dc" {
        $FlycastBin = Get-ChildItem -Path (Join-Path $BinDir "flycast") -Filter "flycast*.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notmatch "updater|setup|unins" } |
            Select-Object -First 1
        if (-not $FlycastBin) {
            $Emulator = Join-Path $BinDir "flycast\flycast.exe"
        } else {
            $Emulator = $FlycastBin.FullName
        }
        $ArgList += $ResolvedRom
        if ($IsFullscreen) { $ArgList += "--fullscreen" }
    }
}

# 2. Detecção Dinâmica de GPU (dGPU vs iGPU)
if (-not (Test-Path "HKCU:\Software\Microsoft\DirectX\UserGpuPreferences")) {
    New-Item -Path "HKCU:\Software\Microsoft\DirectX\UserGpuPreferences" -Force | Out-Null
}

$ApplyDgpu = $false
if ($GpuMode -eq "dgpu") {
    $ApplyDgpu = $true
} elseif ($GpuMode -eq "auto") {
    $Gpus = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue
    if ($Gpus | Where-Object { $_.Name -match "NVIDIA|Radeon RX|Intel Arc|GeForce" }) {
        $ApplyDgpu = $true
    }
}

if ($ApplyDgpu -and (Test-Path $Emulator)) {
    Set-ItemProperty -Path "HKCU:\Software\Microsoft\DirectX\UserGpuPreferences" -Name (Resolve-Path $Emulator).Path -Value "GpuPreference=2;" -ErrorAction SilentlyContinue
    Write-Host ">>> GPU de Alto Desempenho (dGPU) ativada para o processo." -ForegroundColor Gray
}

# 3. Execução com Isolamento de CWD e Afinidade Protegida de CPU
if (-not (Test-Path $Emulator)) {
    Write-Error "Executável do emulador não encontrado: $Emulator. Execute o provisionamento ou verifique a pasta bin/."
}

Push-Location (Split-Path $Emulator)
try {
    Write-Host ">>> Executando $Platform [$RomPath]..." -ForegroundColor Cyan

    # Encapsula argumentos que contêm espaços para evitar fragmentação no Start-Process
    $EscapedArgs = $ArgList | ForEach-Object {
        if ($_ -match '\s' -and $_ -notmatch '^".*"$') {
            "`"$_`""
        } else {
            $_
        }
    }

    $Process = Start-Process -FilePath $Emulator -ArgumentList $EscapedArgs -PassThru

    # Aplicação segura de afinidade de P-cores se CPU híbrida for identificada
    if ($Platform -in @("ps2", "gc")) {
        try {
            Start-Sleep -Milliseconds 150
            if (-not $Process.HasExited) {
                $Cpu = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue
                if ($Cpu.Name -match "12th|13th|14th|Core Ultra") {
                    $CoreCount = [Environment]::ProcessorCount
                    # Vincula aos P-cores (threads 0 a 7) se a topologia tiver threads suficientes
                    if ($CoreCount -ge 8) {
                        $Process.ProcessorAffinity = [IntPtr]0x00FF
                        Write-Host ">>> Afinidade vinculada aos P-cores." -ForegroundColor Gray
                    }
                }
            }
        } catch {
            # Não interrompe a execução caso o processo recuse ajuste de afinidade
        }
    }

    $Process.WaitForExit()
    if ($Process.ExitCode -ne 0) {
        exit $Process.ExitCode
    }
}
finally {
    Pop-Location
}
