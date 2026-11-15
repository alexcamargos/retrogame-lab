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
  * O escalonador do sistema gerencia a afinidade; o lançador não presume a topologia a partir do nome da CPU.
* **Arquiteturas Simétricas (AMD Ryzen, Intel pré-12ª Gen):**
  * O escalonamento permanece padrão e irrestrito (usando todos os núcleos disponíveis sem aplicar máscara de afinidade).

### 2.2 Subsistema Gráfico (GPU & Rendering Backend)
* **Hosts com GPU Dedicada (NVIDIA, AMD Radeon, Intel Arc):**
  * O script injeta a preferência de alto desempenho no registro do Windows 11 (`HKCU:\Software\Microsoft\DirectX\UserGpuPreferences` -> `GpuPreference=2;`) para o binário acionado, garantindo que o sistema operacional direcione a renderização para a dGPU.
  * Backend prioritário: **Vulkan** com compilação assíncrona de shaders habilitada.
* **Hosts com Gráficos Integrados (Intel Iris Xe / AMD Radeon 600M/700M/800M):**
  * Os perfis iniciais usam resolução conservadora; o usuário pode ajustar as opções conforme a capacidade do host.
  * Backend alternativo: **Direct3D 12** ou **Direct3D 11** caso o suporte a Vulkan da iGPU apresente artefatos.

### 2.3 Memória e Armazenamento
* **RAM:** Alocação flexível. O footprint de emulação varia de 512MB (2D) até 4GB (PS2/Wii em resoluções altas).
* **Armazenamento:** Mídias armazenadas exclusivamente em formatos compactados por blocos com acesso aleatório direto (`.chd` para CD/DVD de PS1/PS2/DC e `.rvz` para GameCube/Wii), reduzindo o consumo de espaço em qualquer disco SSD/NVMe.

---

## 3. Topologia de Diretórios (Filesystem Estruturado)

A raiz do projeto é totalmente autocontida e portável entre diretórios ou volumes de disco:

```text
retrogame-lab/
├── .agents/
│   └── skills/
│       └── emulator-pipeline/      # Skill com orquestração do Agente Antigravity
├── bin/                            # Emuladores e Frontends Portáteis (Zero-Install)
│   ├── es-de/                      # Frontend EmulationStation Desktop Edition
│   │   ├── ES-DE.exe
│   │   └── es_systems.xml          # Configuração de sistemas apontando para data/
│   ├── retroarch/                  # SNES, Mega Drive, Arcade, GBA
│   │   ├── retroarch.exe
│   │   └── retroarch.cfg           # Configuração portátil local (sem portable.ini)
│   ├── duckstation/                # PS1
│   │   ├── duckstation-qt.exe
│   │   ├── portable.txt            # Gatilho de portabilidade oficial
│   │   └── settings.ini            # Title-specific Memory Card ativo
│   ├── pcsx2/                      # PS2 (v2.x Qt)
│   │   ├── pcsx2-qt.exe
│   │   ├── portable.txt            # Gatilho de portabilidade oficial (v2.0+)
│   │   └── inis/PCSX2.ini          # Title-specific Memory Card ativo
│   ├── ppsspp/                     # PSP
│   │   ├── PPSSPPWindows64.exe
│   │   └── memstick/               # Armazenamento local (SAVEDATA linkado via junção)
│   ├── dolphin/                    # GameCube / Wii
│   │   ├── Dolphin.exe
│   │   └── portable.txt            # Gatilho de portabilidade oficial
│   ├── flycast/                    # Dreamcast
│   │   ├── flycast.exe
│   │   └── emu.cfg                 # Configuração local
│   ├── rpcs3/                      # PS3 (Windows-only)
│   │   ├── rpcs3.exe
│   │   └── portable.txt            # Gatilho de portabilidade oficial
│   ├── xenia/                      # Xbox 360 (Windows-only)
│   │   ├── xenia.exe
│   │   └── portable.txt            # Gatilho de portabilidade oficial
│   └── ryujinx/                    # Switch (Windows-only)
│       ├── Ryujinx.exe
│       └── portable/               # Isolamento local oficial de perfil/saves
├── data/                           # Segregação estrita do ciclo de vida dos dados
│   ├── bios/                       # Firmware centralizado (Sincronizado via Syncthing Send-Only)
│   │   ├── ps1/
│   │   ├── ps2/
│   │   ├── dc/
│   │   ├── ps3/                    # PS3UPDAT.PUP (Firmware oficial)
│   │   └── switch/                 # prod.keys e firmware
│   ├── roms/                       # Imagens de jogos padronizadas sem espaços (Send-Only)
│   │   ├── snes/                   # Formato .sfc / .smc
│   │   ├── ps1/                    # Formato .chd (CD)
│   │   ├── ps2/                    # Formato .chd (DVD) / .iso
│   │   ├── psp/                    # Formato .cso / .iso
│   │   ├── gc/                     # Formato .rvz (Dolphin)
│   │   ├── dc/                     # Formato .chd (CD)
│   │   ├── wii/                    # Formato .rvz (Dolphin)
│   │   ├── n64/                    # Formato .z64
│   │   ├── ps3/                    # Formato .iso / .pkg (Windows-only)
│   │   ├── xbox360/                # Formato .iso / .xex (Windows-only)
│   │   └── switch/                 # Formato .nsp / .xci (Windows-only)
│   ├── saves/                      # Saves in-game (.srm, .mcd, .ps2, .gci, .bin) (Send-Receive)
│   │   ├── .stignore               # Filtro anti-savestate (*.state*), locks e isolamento Windows-only
│   │   ├── snes/                   # Arquivos .srm por jogo
│   │   ├── ps1/                    # Cartão por jogo (.mcd)
│   │   ├── ps2/                    # Cartão por jogo (.ps2)
│   │   ├── psp/SAVEDATA/           # Pastas SAVEDATA nativas
│   │   ├── gc/                     # Cartões GCI / Pastas por Região (USA, EUR, JAP)
│   │   ├── dc/                     # Arquivos VMU (.bin)
│   │   ├── wii/                    # Títulos e saves nativos do Dolphin
│   │   ├── n64/                    # Arquivos .sra / .fla / .eep / .mpk por jogo
│   │   ├── ps3/                    # Pastas dev_hdd0/home/.../savedata (Desktop-only)
│   │   ├── xbox360/                # Pastas Content/0000000000000000 (Desktop-only)
│   │   └── switch/                 # Pastas de perfil do emulador (Desktop-only)
│   └── states/                     # Savestates locais (NÃO sincronizados, isolados via .stignore)
├── docs/                           # Documentação técnica e de engenharia
│   ├── guia-inicio.md              # Guia de início e integração multiplataforma (Windows <-> Android)
│   ├── specs-windows.md            # Esta especificação
│   └── specs-android.md            # Especificação de sincronização com Android
├── scripts/
│   ├── bootstrap.ps1               # Download idempotente via winget, junção PPSSPP e setup de templates
│   ├── download_emulators.ps1      # Download e extração automatizada de emuladores portáteis para bin/
│   ├── launch.ps1                  # Lançador dinâmico com trava pré-voo, perfilamento de GPU/CPU e CWD isolado
│   ├── convert_chd.ps1             # Conversor inteligente CD vs DVD com higienização de nomes e fallback no PATH
│   ├── setup_android_emulators.ps1 # Provisionamento de pastas, permissões e APKs no Android via ADB
│   └── audit_library.ps1           # Wrapper PowerShell para auditoria da biblioteca
├── src/
│   └── retrogame_lab/              # Pacote Python modular (CLI, Auditor, Ingestão, Higienização)
│       ├── __init__.py
│       ├── config.py               # Resolução canônica de caminhos e metadados
│       ├── auditor.py              # Auditoria SHA-256, formatos de disco e regras de saves
│       ├── sanitizer.py            # Higienização de nomenclatura (sem espaços e caracteres especiais)
│       ├── ingestion.py            # Pipeline de ingestão segura de ROMs (validação e cópia/movimentação)
│       └── cli.py                  # CLI Typer com rich tables (info, audit, sanitize, import-rom)
├── templates/                      # Configurações pré-definidas injetadas no bootstrap
│   ├── config/                     # Templates de retroarch.cfg, duckstation_settings.ini, PCSX2.ini
│   ├── controllers/                # Mapeamentos XInput (Xbox), DualSense e 8BitDo
│   └── es-de/                      # Configurações de rotas do ES-DE
├── tests/                          # Bateria de 55 testes unitários com pytest e pytest-mock
├── tools/                          # Utilitários de linha de comando
│   ├── chdman.exe                  # MAME CHD Manager
│   └── 7z.exe                      # Descompactação determinística
├── AGENTS.md                       # Diretrizes e governança para agentes de IA
├── retrogame.cmd                   # Ponto de entrada rápido para cmd/terminal
└── retrogame.ps1                   # CLI unificada e orquestrador em PowerShell Core
```

---

## 4. Matriz de Perfis de Renderização e Calibração Dinâmica

A resolução interna e os aprimoramentos visuais são parametrizados com base na capacidade do hardware host e nas características do jogo:

| Plataforma | Emulador Homologado | Backend Recomendado | Perfil Básico (iGPU) | Perfil Avançado (dGPU / Baseline) | Estratégia de Saves | Escopo |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SNES** | RetroArch (`snes9x` / `bsnes`) | Vulkan / D3D11 | 1x Nativo (CRT shader leve) | 1x Nativo (CRT-Royale / Mega Bezel) | Arquivos `.srm` por jogo em `data/saves/snes/` | Windows + Android |
| **PS1** | DuckStation (Qt) | Vulkan | 2x a 3x (720p) | 5x (1080p) a 6x (1440p) + PGXP | **Title-specific Card** (`data/saves/ps1/<Title>_<ID>.mcd`) | Windows + Android |
| **PS2** | PCSX2 (Qt v2.0+) | Vulkan / D3D12 | 1x a 2x (Nativo/720p) | 3x (1080p) a 4x (1440p) + Aniso 16x | **Title-specific Card** (`data/saves/ps2/<Title>_<ID>.ps2`) | Windows + Android |
| **PSP** | PPSSPP Standalone | Vulkan | 2x a 3x (PSP HD) | 5x a 10x (1080p / 4K) | Pastas nativas `data/saves/psp/SAVEDATA/` | Windows + Android |
| **GameCube** | Dolphin | Vulkan | 1.5x a 2x (720p) | 3x (1080p) a 4x (1440p) + Ubershaders | Cartões GCI / Pastas de Região em `data/saves/gc/` | Windows + Android |
| **Dreamcast** | Flycast | Vulkan | 1x a 2x (VGA) | 3x (1440p) + Per-Pixel Transparency | Arquivo de VMU padrão em `data/saves/dc/vms0.bin` | Windows + Android |
| **Nintendo Wii** | Dolphin | Vulkan | 1.5x a 2x (720p) | 3x (1080p) a 4x (1440p) + Ubershaders | Títulos nativos Dolphin em `data/saves/wii/` | Windows + Android |
| **Nintendo 64** | RetroArch (`mupen64plus-next`) | Vulkan / D3D11 | 2x (720p) | 4x (1440p) + CRT Shaders | Saves `.sra`/`.fla`/`.eep`/`.mpk` em `data/saves/n64/` | Windows + Android |
| **PS3** | RPCS3 | Vulkan | 1x Nativo (720p) | 1080p a 1440p + ZCull Occlusion | Pastas nativas `dev_hdd0/home/.../savedata` | Windows 11 (Desktop) |
| **Xbox 360** | Xenia (ou Canary) | Direct3D 12 / Vulkan | 1x Nativo (720p) | 2x (1440p) + FSR | Pastas de perfil `Content/0000000000000000` | Windows 11 (Desktop) |
| **Nintendo Switch** | Ryujinx | Vulkan | 1x Nativo (Handheld/Dock) | 2x (1440p) + FSR Scaling | Pastas de perfil de save do usuário | Windows 11 (Desktop) |

---

## 5. Módulo de Automação: Scripts PowerShell Core (`pwsh`)

### 5.1 Script Lançador Agnóstico (`scripts/launch.ps1`)

O [lançador](../scripts/launch.ps1) detecta a GPU, preserva o diretório de trabalho do emulador e protege ROMs com saves associados. O escalonador do sistema controla a afinidade de CPU.

---

### 5.2 Script de Conversão Automática para CHD (`scripts/convert_chd.ps1`)

O [conversor](../scripts/convert_chd.ps1) aceita descritores de CD e imagens ISO. Para ISO, informe explicitamente `-MediaType cd` ou `-MediaType dvd`. A saída é verificada antes da publicação; colisões e arquivos de saída existentes são recusados.

---

### 5.3 Script de Instalação e Provisionamento (`scripts/bootstrap.ps1`)

O [bootstrap](../scripts/bootstrap.ps1) provisiona a estrutura portátil e verifica as junções de saves. Uma junção que ainda aponte para um destino antigo existente exige análise manual para preservar os dados.

---

### 5.4 Módulo Python de Ingestão, Higienização e Auditoria (`retrogame-lab` CLI)

O pacote canônico `src/retrogame_lab/` implementa a lógica central de governança de dados:

1. **Ingestão Segura (`retrogame_lab.ingestion`):**
   * Validação de extensões aceitas e proibidas por plataforma (ex.: proíbe `.chd` em GameCube, exigindo `.rvz`; proíbe `.gdi` solto em Dreamcast).
   * Higienização automática do nome do arquivo (remoção de caracteres especiais e conversão de espaços para `_`).
   * Roteamento determinístico para `data/roms/<plataforma>/`, suportando modo cópia ou movimentação (`--move`).
   * Comando CLI: `uv run retrogame-lab import-rom <arquivo|pasta> --platform <plataforma> [--move]`.

2. **Higienização de Nomenclatura (`retrogame_lab.sanitizer`):**
   * Normalização idempotente de arquivos e diretórios em massa.
   * Suporte a simulação (*Dry Run*) antes de aplicar alterações reais no disco.
   * Comando CLI: `uv run retrogame-lab sanitize [--apply] [--path <pasta>]`.

3. **Auditoria de Integridade da Biblioteca (`retrogame_lab.auditor`):**
   * Verificação de hashes SHA-256 de firmwares em `data/bios/`.
   * Detecção de arquivos soltos fora das pastas de plataforma.
   * Validação de formatos de disco recomendados e checagem anti-savestates (`*.state*`) em `data/saves/`.
   * Comando CLI: `uv run retrogame-lab audit [--json] [--full] [--path <raiz>]`.

---

### 5.5 Orquestrador e CLI Unificada (`retrogame`)

Para simplificar a operação do ecossistema, o projeto disponibiliza um ponto de entrada unificado que despacha de forma transparente para automações em PowerShell Core ou comandos da suíte analítica em Python:

* **PowerShell:** `.\retrogame <subcomando> [opções...]`
* **Prompt de Comando:** `retrogame.cmd <subcomando> [opções...]`
* **Astral uv:** `uv run retrogame <subcomando> [opções...]`

Principais subcomandos suportados:
* `bootstrap`: Provisiona pastas, marcadores portáteis e ferramentas via winget (`[-SkipWinget] [-DownloadEmulators]`).
* `download-emulators`: Baixa e extrai versões portáteis oficiais de 64 bits para `bin/` (`[-Force] [-Emulators <lista>]`).
* `check-updates`: Compara versões instaladas contra os repositórios remotos oficiais (`[-Emulators <lista>]`).
* `update-emulators`: Atualiza apenas emuladores com novas versões disponíveis em `bin/` (`[-Force] [-Emulators <lista>]`).
* `launch`: Inicializa jogos com detecção de GPU e trava pré-voo (`-Platform <plat> -RomPath <rom> [-Windowed] [-GpuMode auto|igpu|dgpu]`).
* `convert-chd`: Compacta imagens para CHD determinístico (`-SourceDirectory <pasta> [-MediaType auto|cd|dvd]`).
* `android`: Provisiona o dispositivo Android conectado via ADB (`[-SkipDownload]`).
* `audit`: Audita integridade de BIOS, ROMs e saves (`[--json] [--full]`).
* `sanitize`: Higieniza nomes de ROMs e saves (`[--apply]`).
* `import-rom`: Ingere e normaliza ROMs para a biblioteca canônica (`<arquivo> -p <plat> [--move]`).
* `info`: Exibe a matriz de plataformas homologadas e formatos aceitos.
* `version`: Exibe a versão do pacote instalada.

---

## 6. Integração com Frontend Unificado (ES-DE Portable)

O **ES-DE (EmulationStation Desktop Edition) Portable** opera como frontend de console agnóstico:
* Localizado em `bin/es-de/`.
* Mapeamento relativo em `es_systems.xml` conectando `data/roms/` aos executáveis em `bin/`.
* Independência de resolução do display, ajustando-se automaticamente da tela do notebook a TVs 4K externas.

> [!IMPORTANT]
> **Seleção da Pasta de ROMs no Assistente do ES-DE:**  
> Ao iniciar o ES-DE pela primeira vez (ou ao configurar *Settings -> ROM Directory*), selecione a **raiz do repositório (`retrogame-lab/`)** como diretório principal de ROMs, e não a subpasta `data/roms/`. Isso garante que as rotas relativas `%ROMPATH%/data/roms/<plataforma>` e o comando `%ROMPATH%\scripts\launch.ps1` definidos em `templates/es-de/es_systems.xml` sejam resolvidos sem erros.

---

## 7. Critérios de Homologação

1. **Portabilidade Integral:** A raiz do projeto pode ser movida de pasta ou de unidade sem perder saves, caminhos de BIOS ou configurações de emulador.
2. **Adaptação Dinâmica:** O lançador identifica automaticamente as capacidades gráficas e de CPU do computador host sem depender de configurações estáticas ou hardcoded.
3. **Consistência de Saves:** Toda escrita em memory card ocorre em `data/saves/<plataforma>/`, padronizada para sincronização via Syncthing.
