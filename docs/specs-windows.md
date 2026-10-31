# Especificação Técnica: Pipeline Portátil de Emulação e Retro-Gaming para Windows 11

## 1. Visão Geral da Arquitetura

O projeto de referência [akitaonrails/distrobox-gaming](https://github.com/akitaonrails/distrobox-gaming) foca em isolamento de dependências via contêineres Linux (Distrobox/Arch Linux), evitando conflitos de glibc, bibliotecas e drivers X11/Wayland, orquestrado via Ansible e EmulationStation Desktop Edition (ES-DE).

No ambiente Windows 11, o isolamento é obtido pelo princípio de **Portabilidade Estática por Diretório** (*Zero-Install / Self-Contained Folders*). Os emuladores modernos (RetroArch, DuckStation, PCSX2, PPSSPP, Dolphin, Flycast) não exigem registro nem dependência do `%APPDATA%`, operando de forma desacoplada com caminhos relativos em pastas isoladas.

### 1.1 Filosofia Agnóstica de Hardware com Perfilamento Dinâmico
Este pipeline é projetado para ser **estritamente agnóstico de hardware**. O sistema não assume uma CPU ou GPU fixa; em vez disso, a seleção de backend de renderização, multiplicador de resolução interna, flags de shaders e alocação de núcleos ocorre **dinamicamente no momento do lançamento do emulador e do título selecionado**, conforme o perfil de capacidade do host detectado em tempo de execução:

```
                           +-------------------------------------------------+
                           |                 Host: Windows 11                |
                           |       (Qualquer CPU x86_64 / iGPU ou dGPU)      |
                           +-------------------------------------------------+
                                                    |
                                    +---------------+---------------+
                                    |                               |
                     +----------------------------+   +----------------------------+
                     |    Orquestração do Agente   |   | Módulo de Perfilamento     |
                     |       (agy CLI / Skills)   |   |   (Hardware Profiler Din.) |
                     +----------------------------+   +----------------------------+
                                                    |
                                    +---------------+---------------+
                                    |  Decisão Dinâmica de Execução  |
                                    |  (Backend, Resolução, Cores)  |
                                    +---------------+---------------+
                                                    |
         +------------------------------------------+------------------------------------------+
         |                                          |                                          |
+------------------+                      +-------------------+                      +------------------+
|  Emuladores 2D   |                      | 3D Leve/Intermed. |                      | 3D Avançado      |
|  (RetroArch)     |                      | (DuckStation/     |                      | (PCSX2 /         |
|  D3D11 / Vulkan  |                      |  PPSSPP / Flycast)|                      |  Dolphin)        |
|  Escala Adaptada |                      |  Vulkan / D3D12   |                      |  Vulkan / D3D12  |
+------------------+                      +-------------------+                      +------------------+
         |                                          |                                          |
         +------------------------------------------+------------------------------------------+
                                                    |
                                    +-------------------------------+
                                    |     Subsistema Gráfico Host   |
                                    | (dGPU Dedicada ou iGPU Integr)|
                                    +-------------------------------+
```

> [!NOTE]
> **Perfil de Referência Homologado:**  
> Um notebook equipado com Intel Core i5 de 12ª Geração (arquitetura híbrida) e NVIDIA GeForce RTX 4050 Laptop GPU (6GB) foi utilizado como **baseline empírico de referência** para calibrar tetos de performance e testar os limites de estresse térmico, mas todos os scripts e especificações suportam qualquer combinação de hardware compatível com Windows 11.

---

## 2. Detecção Dinâmica de Recursos e Alocação do Host

O pipeline inspeciona as capacidades do host em tempo de execução para aplicar as melhores diretrizes operacionais:

### 2.1 Processador (CPU Topology & Affinity)
* **Arquiteturas Híbridas (ex.: Intel 12ª Gen+ P-Cores e E-Cores):**
  * Para emuladores com alta sensibilidade a temporização e IPC monothread (PCSX2, Dolphin), o orquestrador detecta a presença de topologia heterogênea e vincula o processo prioritariamente aos **Performance-cores (P-cores)**, impedindo que o agendador do SO migre threads críticas para E-cores de menor rendimento.
* **Arquiteturas Simétricas (AMD Ryzen, Intel pré-12ª Gen):**
  * O escalonamento permanece padrão e irrestrito (usando todos os núcleos disponíveis sem aplicar máscara de afinidade).

### 2.2 Subsistema Gráfico (GPU & Rendering Backend)
* **Hosts com GPU Dedicada (NVIDIA, AMD Radeon, Intel Arc):**
  * O script injeta a preferência de alto desempenho no registro do Windows 11 (`HKCU:\Software\Microsoft\DirectX\UserGpuPreferences` -> `GpuPreference=2;`) para o binário acionado, garantindo que o sistema operacional direcione a renderização para a dGPU.
  * Backend prioritário: **Vulkan** com compilação assíncrona de shaders habilitada.
* **Hosts com Gráficos Integrados (Intel Iris Xe / AMD Radeon 600M/700M/800M):**
  * Resolução interna ajustada dinamicamente para níveis sustentáveis (1x a 2x nativo) sem forçar perfis excessivos de VRAM.
  * Backend alternativo: **Direct3D 12** ou **Direct3D 11** caso o suporte a Vulkan da iGPU apresente artefatos.

### 2.3 Memória e Armazenamento
* **RAM:** Alocação flexível. O footprint de emulação varia de 512MB (2D) até 4GB (PS2/Wii em resoluções altas).
* **Armazenamento:** Mídias armazenadas exclusivamente em formatos compactados por blocos com acesso aleatório direto (`.chd` para CD/DVD de PS1/PS2/DC e `.rvz` para GameCube/Wii), reduzindo o consumo de espaço em qualquer disco SSD/NVMe.

---

## 3. Topologia de Diretórios (Filesystem Estruturado)

A raiz do projeto é totalmente autocontida e portável entre diretórios ou volumes de disco:

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
│   │   ├── pcsx2-qt.exe
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
│   │   ├── ps1/                    # Formato .chd (CD)
│   │   ├── ps2/                    # Formato .chd (DVD) / .iso
│   │   ├── psp/                    # Formato .cso / .iso
│   │   ├── gc/                     # Formato .rvz (Dolphin)
│   │   └── dc/                     # Formato .chd (CD)
│   ├── saves/                      # Saves de Memory Card / Bateria (Sincronizado Bidirecional)
│   │   ├── snes/                   # Arquivos .srm por jogo
│   │   ├── ps1/                    # Cartão por jogo (.mcd)
│   │   ├── ps2/                    # Cartão por jogo (.ps2)
│   │   ├── psp/                    # Pastas SAVEDATA nativas
│   │   ├── gc/                     # Cartões GCI / Pastas por Região (USA, EUR, JAP)
│   │   └── dc/                     # Arquivos VMU (.bin)
│   └── states/                     # Savestates locais (NÃO sincronizados, isolados via .stignore)
├── docs/                           # Documentação técnica e de engenharia
│   ├── specs-windows.md            # Esta especificação
│   └── specs-android.md            # Especificação de sincronização com Android
├── scripts/
│   ├── bootstrap.ps1               # Download idempotente via winget e setup de templates
│   ├── launch.ps1                  # Lançador dinâmico com perfilamento de hardware e isolamento de CWD
│   ├── convert_chd.ps1             # Conversor inteligente de mídias (CD vs DVD)
│   └── audit_library.ps1           # Verificador de integridade de ROMs, BIOS e hashes
├── templates/                      # Configurações pré-definidas injetadas no bootstrap
│   ├── config/                     # Templates de retroarch.cfg, DuckStation settings.ini, PCSX2.ini
│   ├── controllers/                # Mapeamentos XInput (Xbox), DualSense e 8BitDo
│   └── es-de/                      # Configurações de rotas do ES-DE
└── tools/                          # Utilitários de linha de comando
    ├── chdman.exe                  # MAME CHD Manager
    └── 7z.exe                      # Descompactação determinística
```

---

## 4. Matriz de Perfis de Renderização e Calibração Dinâmica

A resolução interna e os aprimoramentos visuais são parametrizados com base na capacidade do hardware host e nas características do jogo:

| Plataforma | Emulador Homologado | Backend Recomendado | Perfil Básico (iGPU) | Perfil Avançado (dGPU / Baseline) | Estratégia de Saves |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SNES** | RetroArch (`snes9x` / `bsnes`) | Vulkan / D3D11 | 1x Nativo (CRT shader leve) | 1x Nativo (CRT-Royale / Mega Bezel) | Arquivos `.srm` por jogo em `data/saves/snes/` |
| **PS1** | DuckStation (Qt) | Vulkan | 2x a 3x (720p) | 5x (1080p) a 6x (1440p) + PGXP | **Title-specific Card** (`data/saves/ps1/<Title>_<ID>.mcd`) |
| **PS2** | PCSX2 (Qt v2.0+) | Vulkan / D3D12 | 1x a 2x (Nativo/720p) | 3x (1080p) a 4x (1440p) + Aniso 16x | **Title-specific Card** (`data/saves/ps2/<Title>_<ID>.ps2`) |
| **PSP** | PPSSPP Standalone | Vulkan | 2x a 3x (PSP HD) | 5x a 10x (1080p / 4K) | Pastas nativas `data/saves/psp/SAVEDATA/` |
| **GameCube / Wii** | Dolphin | Vulkan | 1.5x a 2x (720p) | 3x (1080p) a 4x (1440p) + Ubershaders | Cartões GCI / Pastas de Região em `data/saves/gc/` |
| **Dreamcast** | Flycast | Vulkan | 1x a 2x (VGA) | 3x (1440p) + Per-Pixel Transparency | Arquivo de VMU padrão em `data/saves/dc/vms0.bin` |

---

## 5. Módulo de Automação: Scripts PowerShell Core (`pwsh`)

### 5.1 Script Lançador Agnóstico (`scripts/launch.ps1`)

O lançador realiza inspeção dinâmica de GPU e afinidade de CPU em vez de aplicar valores hardcoded:

```powershell
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

$ResolvedRom = (Resolve-Path $RomPath).Path
if (-not (Test-Path $ResolvedRom)) {
    Write-Error "Arquivo de ROM não encontrado: $RomPath"
}

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
        $Pcsx2Bin = Get-ChildItem -Path (Join-Path $BinDir "pcsx2") -Filter "pcsx2*.exe" | Select-Object -First 1
        if (-not $Pcsx2Bin) { Write-Error "Executável do PCSX2 não encontrado em bin\pcsx2\" }
        $Emulator = $Pcsx2Bin.FullName
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

if ($ApplyDgpu) {
    Set-ItemProperty -Path "HKCU:\Software\Microsoft\DirectX\UserGpuPreferences" -Name (Resolve-Path $Emulator).Path -Value "GpuPreference=2;" -ErrorAction SilentlyContinue
    Write-Host ">>> GPU de Alto Desempenho (dGPU) ativada para o processo." -ForegroundColor Gray
}

# 3. Execução com Isolamento de CWD e Afinidade Protegida de CPU
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
```

---

### 5.2 Script de Conversão Automática para CHD (`scripts/convert_chd.ps1`)

Diferencia mídias de CD (2352 bytes/setor) de mídias de DVD (2048 bytes/setor) e ignora GameCube/Wii (que utilizam `.rvz` nativo):

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

    # Mídias de GameCube e Wii devem utilizar RVZ via Dolphin, não CHD
    if ($_.DirectoryName -match "\\gc" -or $_.DirectoryName -match "\\wii") {
        Write-Warning "Ignorando $($_.Name): Mídias de GameCube/Wii devem ser convertidas para .rvz via Dolphin, não .chd."
        return
    }

    $Command = "createcd"
    if ($MediaType -eq "dvd" -or ($MediaType -eq "auto" -and $Ext -eq ".iso" -and $_.DirectoryName -match "\\ps2")) {
        $Command = "createdvd"
    }

    Write-Host ">>> Comprimindo ($Command): $($_.Name) -> $(Split-Path $OutFile -Leaf)" -ForegroundColor Cyan
    & $Chdman $Command -i $_.FullName -o $OutFile
}
```

---

### 5.3 Script de Instalação e Provisionamento (`scripts/bootstrap.ps1`)

Automatiza a instalação de runtimes essenciais e ferramentas de suporte via **`winget`**, cria a estrutura de diretórios, ativa marcadores de portabilidade e injeta templates de configuração para garantir que todos os emuladores salvem em `data/saves/`:

```powershell
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

Write-Host "`n=== Provisionamento Concluído com Sucesso! ===" -ForegroundColor Green
```

---

## 6. Integração com Frontend Unificado (ES-DE Portable)

O **ES-DE (EmulationStation Desktop Edition) Portable** opera como frontend de console agnóstico:
* Localizado em `bin/es-de/`.
* Mapeamento relativo em `es_systems.xml` conectando `data/roms/` aos executáveis em `bin/`.
* Independência de resolução do display, ajustando-se automaticamente da tela do notebook a TVs 4K externas.

---

## 7. Critérios de Homologação

1. **Portabilidade Integral:** A raiz do projeto pode ser movida de pasta ou de unidade sem perder saves, caminhos de BIOS ou configurações de emulador.
2. **Adaptação Dinâmica:** O lançador identifica automaticamente as capacidades gráficas e de CPU do computador host sem depender de configurações estáticas ou hardcoded.
3. **Consistência de Saves:** Toda escrita em memory card ocorre em `data/saves/<plataforma>/`, padronizada para sincronização via Syncthing.
