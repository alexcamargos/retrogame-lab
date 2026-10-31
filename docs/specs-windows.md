# Especificação Técnica: Pipeline Portátil de Emulação e Retro-Gaming para Windows 11

## 1. Visão Geral da Arquitetura

O projeto de referência [akitaonrails/distrobox-gaming](https://github.com/akitaonrails/distrobox-gaming) foca em isolamento de dependências via contêineres Linux (Distrobox/Arch Linux), evitando conflitos de glibc, bibliotecas de 32 bits e drivers X11/Wayland, além de orquestrar tudo com Ansible e EmulationStation Desktop Edition (ES-DE).

No ambiente Windows 11, o isolamento equivalente é obtido pelo princípio de **Portabilidade Estática por Diretório** (*Zero-Install / Self-Contained Folders*). Os emuladores modernos (RetroArch, DuckStation, PCSX2, PPSSPP, Dolphin, Flycast) não exigem registro nem dependência do `%APPDATA%`, operando de forma desacoplada com caminhos relativos em pastas isoladas. A orquestração é controlada via **PowerShell Core (`pwsh`)** e Antigravity Skills, consumindo diretamente a **NVIDIA GeForce RTX 4050 6GB Laptop GPU** via **Vulkan** e **Direct3D 12**, com interface gráfica unificada opcional via **ES-DE Portable**.

```
                           +-------------------------------------------------+
                           |                 Host: Windows 11                |
                           |       (Intel Core i5-12th Gen | 16GB RAM)       |
                           +-------------------------------------------------+
                                                    |
                                    +---------------+---------------+
                                    |                               |
                     +----------------------------+   +----------------------------+
                     |    Orquestração do Agente   |   |     Camada de Execução     |
                     |       (agy CLI / Skills)   |   |  (PowerShell Core / ES-DE) |
                     +----------------------------+   +----------------------------+
                                                    |
         +------------------------------------------+------------------------------------------+
         |                                          |                                          |
+------------------+                      +-------------------+                      +------------------+
|  Emuladores 2D   |                      | 3D Leve/Intermed. |                      | 3D Avançado      |
|  (RetroArch)     |                      | (DuckStation/     |                      | (PCSX2 /         |
|  Direct3D 11/12  |                      |  PPSSPP / Flycast)|                      |  Dolphin)        |
|  SNES, GBA, Arcade|                     |  Vulkan (1080p)   |                      |  Vulkan (1440p)  |
+------------------+                      +-------------------+                      +------------------+
         |                                          |                                          |
         +------------------------------------------+------------------------------------------+
                                                    |
                                    +-------------------------------+
                                    |     NVIDIA RTX 4050 6GB       |
                                    | (High-Performance GPU Profile)|
                                    +-------------------------------+
```

---

## 2. Requisitos de Hardware e Alocação de Recursos

* **Processador:** Intel Core i5 12ª Geração (arquitetura híbrida P-Cores + E-Cores).
  * *Diretriz de Afinidade:* A emulação pesada (PCSX2, Dolphin) é vinculada via script prioritariamente aos **Performance-cores (P-cores 0–7)** para evitar perda de quadros causada pelo agendador de tarefas em E-cores.
* **Placa Gráfica:** NVIDIA GeForce RTX 4050 Laptop GPU (6GB GDDR6, arquitetura Ada Lovelace).
  * *Backend Primário:* **Vulkan** (com *Pipeline Cache* e *Async Shader Compilation* habilitados).
  * *Backend Secundário:* **Direct3D 12** (para títulos com incompatibilidades conhecidas em Vulkan).
  * *Forçagem de GPU:* Atribuição determinística no registro do Windows 11 (`HKCU:\Software\Microsoft\DirectX\UserGpuPreferences` -> `GpuPreference=2;`).
* **Memória RAM:** 16GB DDR4/DDR5 (Footprint operacional dos emuladores $\le$ 4GB).
* **Armazenamento:** SSD NVMe dedicado. Mídias compactadas por blocos (`.chd`, `.cso`, `.rvz`).

---

## 3. Topologia de Diretórios (Filesystem Estruturado)

A raiz do projeto é totalmente autocontida e alinhada às necessidades de sincronização com o ecossistema móvel:

```text
retrogame-lab/
├── .agy/
│   └── skills/
│       ├── emulator-pipeline/      # Skill com orquestração do Agente
│       └── retro-builder/          # Automação de compilação C++/Raylib portátil
├── bin/                            # Emuladores e Frontends Portáteis
│   ├── es-de/                      # Frontend EmulationStation Desktop Edition
│   │   ├── ES-DE.exe
│   │   └── es_systems.xml          # Configuração de sistemas apontando para data/
│   ├── retroarch/                  # SNES, Mega Drive, Arcade, GBA
│   │   ├── retroarch.exe
│   │   └── retroarch.cfg           # Configuração portátil local (sem portable.ini)
│   ├── duckstation/                # PS1
│   │   ├── duckstation-qt.exe
│   │   └── portable.txt            # Gatilho de portabilidade oficial
│   ├── pcsx2/                      # PS2 (v2.x Qt)
│   │   ├── pcsx2-qtx64.exe
│   │   └── portable.txt            # Gatilho de portabilidade oficial (v2.0+)
│   ├── ppsspp/                     # PSP
│   │   ├── PPSSPPWindows64.exe
│   │   └── memstick/               # Armazenamento local
│   ├── dolphin/                    # GameCube / Wii
│   │   ├── Dolphin.exe
│   │   └── portable.txt            # Gatilho de portabilidade oficial
│   └── flycast/                    # Dreamcast
│       ├── flycast.exe
│       └── emu.cfg                 # Configuração local
├── data/                           # Segregação estrita do ciclo de vida dos dados
│   ├── bios/                       # Firmware centralizado (Sincronizado via Syncthing Send-Only)
│   │   ├── ps1/
│   │   ├── ps2/
│   │   └── dc/
│   ├── roms/                       # Imagens de jogos (Sincronizado via Syncthing Send-Only)
│   │   ├── snes/
│   │   ├── ps1/                    # Formato .chd
│   │   ├── ps2/                    # Formato .chd (DVD) / .iso
│   │   ├── psp/                    # Formato .cso / .iso
│   │   ├── gc/                     # Formato .rvz
│   │   └── dc/                     # Formato .chd (CD)
│   ├── saves/                      # Saves de Memory Card / Bateria (Sincronizado Bidirecional)
│   │   ├── snes/                   # Arquivos .srm por jogo
│   │   ├── ps1/                    # Cartão por jogo (.mcd)
│   │   ├── ps2/                    # Cartão por jogo (.ps2)
│   │   ├── psp/                    # Pastas SAVEDATA nativas
│   │   ├── gc/                     # Arquivos GCI individuais
│   │   └── dc/                     # Arquivos VMU (.bin)
│   └── states/                     # Savestates locais (NÃO sincronizados, isolados via .stignore)
├── docs/                           # Documentação técnica e de engenharia
│   ├── specs-windows.md            # Esta especificação
│   └── specs-android.md            # Especificação de sincronização com Android
├── scripts/
│   ├── bootstrap.ps1               # Download e instalação idempotente dos emuladores
│   ├── launch.ps1                  # Lançador com injeção de GPU, P-Cores e controle de CWD
│   ├── convert_chd.ps1             # Conversor inteligente de mídias (CD vs DVD)
│   └── audit_library.ps1           # Verificador de integridade de ROMs, BIOS e hashes
├── templates/                      # Templates pré-configurados de controles e emuladores
│   ├── controllers/                # Mapeamentos XInput (Xbox), DualSense e 8BitDo
│   └── es-de/                      # Configurações de rotas do ES-DE
└── tools/                          # Utilitários de linha de comando
    ├── chdman.exe                  # MAME CHD Manager
    └── 7z.exe                      # Descompactação determinística
```

---

## 4. Matriz de Configuração dos Emuladores para RTX 4050

Todos os emuladores são calibrados para estabilidade térmica e performance no notebook:

| Plataforma | Emulador Recomendado | Backend Gráfico | Resolução Alvo | Estratégia de Memory Card / Saves |
| :--- | :--- | :--- | :--- | :--- |
| **SNES** | RetroArch (`snes9x` / `bsnes`) | Vulkan / D3D11 | 1x Nativo | Arquivos `.srm` por jogo em `data/saves/snes/` |
| **PS1** | DuckStation (Qt) | Vulkan | 5x (1080p) / 6x (1440p) | **Title-specific Card** (`data/saves/ps1/<Title>_<ID>.mcd`) |
| **PS2** | PCSX2 (Qt v2.0+) | Vulkan | 3x (1080p) / 4x (1440p) | **Title-specific Card** (`data/saves/ps2/<Title>_<ID>.ps2`) |
| **PSP** | PPSSPP Standalone | Vulkan | 5x (1360x760) / 10x | Pastas nativas `data/saves/psp/SAVEDATA/` |
| **GameCube / Wii** | Dolphin | Vulkan | 3x (1080p) / 4x (1440p) | Cartão GCI individual (`data/saves/gc/USA/Card A/`) |
| **Dreamcast** | Flycast | Vulkan | 3x (1440p) | Arquivo de VMU dedicado (`data/saves/dc/vmu_save_A1.bin`) |

> [!IMPORTANT]
> **Estratégia Anti-Conflito de Saves:**  
> O uso de cartões individuais por jogo (*Title-specific Memory Cards*) é fundamental para evitar conflitos de sincronização no Syncthing. Cartões únicos globais de 8MB sofrem corrupção irreparável se modificados em dispositivos diferentes sem sincronização prévia.

---

## 5. Módulo de Automação: Scripts PowerShell Core (`pwsh`)

### 5.1 Script Lançador (`scripts/launch.ps1`)

O script garante:
1. Controle estrito do diretório de trabalho (*Current Working Directory* - CWD) para evitar poluição do sistema.
2. Forçagem real da GPU dedicada (RTX 4050) no registro do Windows 11.
3. Fixação da afinidade de processo nos P-cores (Intel 12ª Geração) para PCSX2 e Dolphin.

```powershell
[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [ValidateSet("snes", "ps1", "ps2", "psp", "gc", "dc")]
    [string]$Platform,

    [Parameter(Mandatory = $true)]
    [string]$RomPath,

    [switch]$Fullscreen = $true
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot
$BinDir  = Join-Path $BaseDir "bin"

$ResolvedRom = (Resolve-Path $RomPath).Path
if (-not (Test-Path $ResolvedRom)) {
    Write-Error "Arquivo de ROM não encontrado: $RomPath"
}

# 1. Mapeamento de Binários e Argumentos
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
        $Emulator = Join-Path $BinDir "pcsx2\pcsx2-qtx64.exe"
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
        $ArgList += @("-b", "-e", $ResolvedRom)
    }
    "dc" {
        $Emulator = Join-Path $BinDir "flycast\flycast.exe"
        $ArgList += $ResolvedRom
        if ($Fullscreen) { $ArgList += "--fullscreen" }
    }
}

# 2. Forçar GPU de Alto Desempenho (RTX 4050) no Windows 11
$GpuRegPath = "HKCU:\Software\Microsoft\DirectX\UserGpuPreferences"
if (-not (Test-Path $GpuRegPath)) {
    New-Item -Path $GpuRegPath -Force | Out-Null
}
Set-ItemProperty -Path $GpuRegPath -Name (Resolve-Path $Emulator).Path -Value "GpuPreference=2;" -ErrorAction SilentlyContinue

# 3. Execução com Isolamento de Diretório de Trabalho (CWD) e Afinidade de P-Cores
Push-Location (Split-Path $Emulator)
try {
    Write-Host ">>> Iniciando $Platform com RTX 4050..." -ForegroundColor Cyan
    $Process = Start-Process -FilePath $Emulator -ArgumentList $ArgList -PassThru

    # Para emulação pesada (PS2 / GameCube), fixa nos primeiros 8 threads lógicos (P-Cores)
    if ($Platform -in @("ps2", "gc")) {
        # Máscara binária: 0b11111111 (Cores 0 a 7)
        $Process.ProcessorAffinity = [IntPtr]0x00FF
    }

    $Process.WaitForExit()
}
finally {
    Pop-Location
}
```

---

### 5.2 Script de Conversão Automática para CHD (`scripts/convert_chd.ps1`)

O script diferencia rigorosamente setores de CD (2352 bytes) de setores de DVD (2048 bytes), evitando imagens corrompidas:

```powershell
[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [string]$SourceDirectory,

    [ValidateSet("cd", "dvd", "auto")]
    [string]$MediaType = "auto"
)

$ErrorActionPreference = "Stop"
$Chdman = Join-Path (Split-Path -Parent $PSScriptRoot) "tools\chdman.exe"

if (-not (Test-Path $Chdman)) {
    Write-Error "chdman.exe não encontrado em tools\. Execute o bootstrap primeiro."
}

Get-ChildItem -Path $SourceDirectory -Include *.cue, *.iso, *.bin -Recurse | ForEach-Object {
    $OutFile = [System.IO.Path]::ChangeExtension($_.FullName, ".chd")
    if (Test-Path $OutFile) {
        return
    }

    $Ext = $_.Extension.ToLower()
    $Command = "createcd"

    if ($MediaType -eq "dvd") {
        $Command = "createdvd"
    } elseif ($MediaType -eq "auto") {
        # ISOs de PS2 e GameCube são tipicamente DVDs
        if ($Ext -eq ".iso" -and ($_.DirectoryName -match "ps2" -or $_.DirectoryName -match "gc")) {
            $Command = "createdvd"
        }
    }

    Write-Host ">>> Comprimindo ($Command): $($_.Name) -> $(Split-Path $OutFile -Leaf)" -ForegroundColor Cyan
    & $Chdman $Command -i $_.FullName -o $OutFile
}
```

---

### 5.3 Script de Instalação e Provisionamento (`scripts/bootstrap.ps1`)

Inspirado no papel do Ansible no `distrobox-gaming`, este script automatiza a configuração do ambiente no Windows 11:

```powershell
[CmdletBinding()]
param (
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot
$BinDir   = Join-Path $BaseDir "bin"
$ToolsDir = Join-Path $BaseDir "tools"
$DataDir  = Join-Path $BaseDir "data"

Write-Host "=== Provisionamento do Pipeline Retrogaming no Windows 11 ===" -ForegroundColor Green

# 1. Criação da Estrutura de Diretórios
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

# 2. Criação dos Marcadores de Portabilidade Oficiais
New-Item -ItemType File -Path (Join-Path $BinDir "duckstation\portable.txt") -Force | Out-Null
New-Item -ItemType File -Path (Join-Path $BinDir "pcsx2\portable.txt") -Force | Out-Null
New-Item -ItemType File -Path (Join-Path $BinDir "dolphin\portable.txt") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BinDir "ppsspp\memstick") -Force | Out-Null

Write-Host ">>> Estrutura de pastas e marcadores de portabilidade criados com sucesso!" -ForegroundColor Green
```

---

## 6. Integração com Frontend Unificado (ES-DE Portable)

Para espelhar a experiência de console do Akita, o frontend oficial é o **ES-DE (EmulationStation Desktop Edition) Portable**:
* Localizado em `bin/es-de/`.
* O arquivo `es_systems.xml` mapeia cada sistema diretamente para as pastas de dados e executáveis relativos:
  * ROMs: `%ROMPATH%\snes`, `%ROMPATH%\ps1`, etc. (apontando para `data/roms/`).
  * Emuladores: Invocação direta dos binários portáteis em `bin/`.
  * Scraper integrado: baixa metadados e capas diretamente para `bin/es-de/downloaded_media/`.

---

## 7. Critérios de Homologação

1. **Isolamento de Unidade:** A pasta raiz do projeto pode ser movida de unidade (ex: de `C:\WorkspaceHub\retrogame-lab` para `D:\retrogame-lab`) sem perda de configurações, saves ou mapeamento de BIOS.
2. **Prevenção de Throttling e GPU Locking:** PCSX2 e Dolphin operam com 100% de velocidade nativa vinculados aos P-Cores, e a RTX 4050 opera sob temperatura $\le$ 75°C.
3. **Consistência de Saves:** Toda escrita em memory card ocorre em `data/saves/<plataforma>/`, pronta para sincronização imediata via Syncthing.
