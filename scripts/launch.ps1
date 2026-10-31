[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [ValidateSet("snes", "ps1", "ps2", "psp", "gc", "dc")]
    [string]$Platform,

    [Parameter(Mandatory = $true)]
    [string]$RomPath,

    [switch]$Fullscreen = $true,

    [ValidateSet("auto", "igpu", "dgpu")]
    [string]$GpuMode = "auto"
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot
$BinDir  = Join-Path $BaseDir "bin"

if (-not (Test-Path $RomPath)) {
    Write-Error "Arquivo de ROM não encontrado: $RomPath"
}
$ResolvedRom = (Resolve-Path $RomPath).Path

# 1. Resolução Dinâmica de Executáveis e Montagem de Argumentos
$ArgList = @()
switch ($Platform) {
    "snes" {
        $Emulator = Join-Path $BinDir "retroarch\retroarch.exe"
        $Core = Join-Path $BinDir "retroarch\cores\snes9x_libretro.dll"
        $ArgList += @("-L", $Core, $ResolvedRom)
        if ($Fullscreen) { $ArgList += "--fullscreen" }
    }
    "ps1" {
        $Emulator = Join-Path $BinDir "duckstation\duckstation-qt.exe"
        $ArgList += @("-batch", $ResolvedRom)
        if ($Fullscreen) { $ArgList += "-fullscreen" }
    }
    "ps2" {
        # Localiza executável Qt moderno (pcsx2-qt.exe ou pcsx2-qtx64.exe)
        $Pcsx2Bin = Get-ChildItem -Path (Join-Path $BinDir "pcsx2") -Filter "pcsx2*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $Pcsx2Bin) {
            $Emulator = Join-Path $BinDir "pcsx2\pcsx2-qt.exe"
        } else {
            $Emulator = $Pcsx2Bin.FullName
        }
        $ArgList += @("-batch")
        if ($Fullscreen) { $ArgList += "-fullscreen" }
        $ArgList += @("--", $ResolvedRom)
    }
    "psp" {
        $Emulator = Join-Path $BinDir "ppsspp\PPSSPPWindows64.exe"
        $ArgList += $ResolvedRom
        if ($Fullscreen) { $ArgList += "--fullscreen" }
    }
    "gc" {
        $Emulator = Join-Path $BinDir "dolphin\Dolphin.exe"
        # Dolphin inicia fullscreen via configuração em Dolphin.ini; flag CLI -b encerra ao sair
        $ArgList += @("-b", "-e", $ResolvedRom)
    }
    "dc" {
        $Emulator = Join-Path $BinDir "flycast\flycast.exe"
        $ArgList += $ResolvedRom
        if ($Fullscreen) { $ArgList += "--fullscreen" }
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
    $Process = Start-Process -FilePath $Emulator -ArgumentList $ArgList -PassThru

    # Aplicação segura de afinidade de P-cores se CPU híbrida for identificada
    if ($Platform -in @("ps2", "gc")) {
        try {
            Start-Sleep -Milliseconds 150
            if (-not $Process.HasExited) {
                $Cpu = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue
                if ($Cpu.Name -match "12th|13th|14th|Core Ultra") {
                    $Process.ProcessorAffinity = [IntPtr]0x00FF
                    Write-Host ">>> Afinidade vinculada aos P-cores." -ForegroundColor Gray
                }
            }
        } catch {
            # Não interrompe a execução caso o processo recuse ajuste de afinidade
        }
    }

    $Process.WaitForExit()
}
finally {
    Pop-Location
}
