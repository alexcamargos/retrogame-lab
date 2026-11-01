# RetroGame Lab

> Pipeline portátil e agnóstico de hardware para emulação e retro-gaming em **Windows 11** com sincronização e pareamento contínuo para dispositivos **Android ARM64** via **Syncthing** e automação via **PowerShell Core** e **ADB**.

Inspirado na arquitetura e filosofia de isolamento do projeto [akitaonrails/distrobox-gaming](https://github.com/akitaonrails/distrobox-gaming), adaptada para execução nativa de alto desempenho no ecossistema Windows 11 sem contêineres pesados e com interoperabilidade móvel contínua.

---

## Princípios de Arquitetura

1. **Agnosticismo de Hardware com Perfilamento Dinâmico:** O ecossistema opera em qualquer computador com Windows 11 (adaptando-se a CPUs Intel/AMD com ou sem topologia híbrida e a gráficos integrados ou GPUs dedicadas) e em qualquer dispositivo móvel Android (Smartphones, Tablets ou Consoles Portáteis ARM64). A seleção de backend gráfico, resoluções internas e afinidade de núcleos ocorre dinamicamente no momento da execução do jogo.
2. **Baselines de Referência para Homologação:** Dispositivos específicos (como notebook com Intel 12ª Gen + RTX 4050 e smartphone com Snapdragon) foram utilizados estritamente como *benchmarks empíricos de homologação* para atestar limites de estresse térmico e estabilidade, e não como requisitos rígidos de sistema.
3. **Portabilidade Estática por Diretório (*Zero-Install*):** Toda a suíte de emulação opera com caminhos relativos em pastas isoladas, sem gravar no registro global do sistema ou no `%APPDATA%`.
4. **Sincronização Híbrida Segura:** A sincronização Windows $\leftrightarrow$ Android via Syncthing é estritamente restrita a saves *in-game* (SRAM / Memory Card) e firmwares/ROMs, blindada contra conflitos de sobrescrita e incompatibilidades binárias de savestates (x86_64 vs ARM64).
5. **Orquestrador Unificado e Acesso CLI:** Ponto de entrada único via `retrogame` (disponível como script PowerShell `.\retrogame.ps1`, wrapper cmd `retrogame.cmd` e binário CLI registrado via Astral `uv`), despachando de forma transparente entre tarefas do sistema operacional e pipelines analíticos em Python.

---

## Mapa da Documentação Técnica (Living Docs)

A documentação detalhada de engenharia e decisões operacionais está estruturada no diretório `docs/` e na raiz do repositório:

* **[Guia de Início e Integração Multiplataforma](docs/guia-inicio.md)**
  * Passo a passo para novos usuários: do zero à sincronização perfeita Windows 11 $\leftrightarrow$ Android ARM64.
  * Configuração detalhada do Syncthing (pastas `retrogames-saves`, `retrogames-bios`, `retrogames-roms`).
  * Calibração de memory cards individuais (*Title-specific*) por emulador e rotina de cross-save sem erros.
* **[Guia Operacional para Agentes Autônomos](AGENTS.md)**
  * Diretrizes de engenharia, governança e protocolos de automação via `winget`.
  * Boas práticas de retrogaming, anti-conflito de saves e regras de perfilamento dinâmico de hardware.
* **[Especificação Técnica: Pipeline Windows 11](docs/specs-windows.md)**
  * Arquitetura de portabilidade estática por diretório (*Zero-Install*).
  * Perfilamento dinâmico de CPU (P-cores) e GPU (dGPU vs iGPU).
  * Automações: `launch.ps1`, `convert_chd.ps1`, `bootstrap.ps1` e integração opcional com o frontend visual **ES-DE Portable**.
* **[Especificação Técnica: Sincronização e Pareamento Android](docs/specs-android.md)**
  * Topologia Syncthing: saves bidirecionais com versionamento simples, BIOS e ROMs *send-only*.
  * Matriz de formatos unificados e estratégia anti-conflito de saves (*Per-Game Memory Cards*).
  * Provisionamento total via ADB: `setup_android_emulators.ps1` (Scoped Storage e detecção dinâmica de ABI).
* **[Skill do Agente: Emulator Pipeline](.agents/skills/emulator-pipeline/SKILL.md)**
  * Catálogo de automações e comandos para o agente autônomo Antigravity.

---

## Catálogo de Plataformas Homologadas

| Código | Plataforma | Formato Canônico | Extensões Aceitas | Estratégia de Saves | Emulador de Referência |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`snes`** | Super Nintendo | `.sfc` | `.sfc`, `.smc`, `.zip` | Arquivo `.srm` idêntico à ROM | RetroArch (`snes9x`) |
| **`ps1`** | Sony PlayStation 1 | `.chd` | `.chd` | Cartão individual por jogo (`.mcd`) | DuckStation (Qt) |
| **`ps2`** | Sony PlayStation 2 | `.chd` | `.chd`, `.iso` | Cartão individual por jogo (`.ps2`) | PCSX2 (Qt v2.0+) |
| **`psp`** | Sony PlayStation Portable | `.cso` | `.cso`, `.chd`, `.iso` | Pastas nativas `SAVEDATA` | PPSSPP Standalone |
| **`gc`** | Nintendo GameCube | `.rvz` | `.rvz` | Cartões GCI / Pastas de Região em `gc/` | Dolphin |
| **`dc`** | Sega Dreamcast | `.chd` | `.chd` | Arquivo de VMU padrão (`vms0.bin`) | Flycast |

---

## Guia Rápido de Comandos e Operação

O RetroGame Lab disponibiliza o utilitário unificado `retrogame`. Você pode utilizá-lo via **PowerShell Core (`.\retrogame`)**, **Prompt de Comando (`retrogame.cmd`)** ou através do gerenciador **Astral `uv` (`uv run retrogame` ou `uv run retrogame-lab`)**.

### 1. Provisionamento Inicial do Host (Cold Start)

Prepara a estrutura de pastas, marcadores de portabilidade e templates de configuração.

```powershell
# Cria a estrutura de pastas e marcadores de portabilidade (sem instalar ferramentas do host)
.\retrogame bootstrap -SkipWinget

# Instalação completa de runtimes (DirectX, VCRedist) e utilitários via winget (requer terminal Admin)
.\retrogame bootstrap
```

*Comandos alternativos diretos:*
* `pwsh -NoProfile -File scripts\bootstrap.ps1 [-SkipWinget]`
* `uv run retrogame-lab bootstrap [--skip-winget]`

### 2. Auditoria de Integridade de BIOS, ROMs e Saves

Valida a presença de firmwares de BIOS, integridade de hashes SHA-256, formatos de mídia e regras anti-conflito de salvamentos.

```powershell
# Auditoria interativa com relatório visual no terminal
.\retrogame audit

# Auditoria estruturada em JSON (ideal para agentes, CI e scripts)
.\retrogame audit --json
```

*Comandos alternativos diretos:*
* `pwsh -NoProfile -File scripts\audit_library.ps1 [-Json]`
* `uv run retrogame-lab audit [--json]`

### 3. Higienização e Padronização de Nomenclatura (Sem Espaços)

Audita e padroniza arquivos para que não contenham espaços (convertidos para `_`) nem caracteres especiais (`'"~^!?\:;*<>|#`), garantindo conformidade com Android Scoped Storage e sistemas de arquivos FAT32/exFAT.

```powershell
# Simulação prévia das alterações necessárias (Dry Run)
.\retrogame sanitize

# Aplicação real das renomeações no disco
.\retrogame sanitize --apply
```

*Comandos alternativos diretos:*
* `uv run retrogame-lab sanitize [--apply]`

### 4. Ingestão Segura de Jogos (ROMs)

Valida o formato aceito para a plataforma, bloqueia extensões proibidas (ex.: `.chd` para GameCube) e normaliza a nomenclatura antes de gravar em `data/roms/<plataforma>/`.

```powershell
# Importação de arquivo individual com validação e higienização automática (modo cópia)
.\retrogame import-rom "data\temp\Super Mario World.sfc" -p snes

# Importação movendo o arquivo de origem para o repositório canônico
.\retrogame import-rom "data\temp\Gran Turismo 2.chd" -p ps1 --move

# Ingestão em lote de um diretório contendo múltiplas imagens de jogos
.\retrogame import-rom "data\temp\LotePS2\" -p ps2
```

*Comandos alternativos diretos:*
* `uv run retrogame-lab import-rom <origem> -p <plataforma> [--move]`

### 4.1 Ingestão Interativa de ROMs Preservadas (No-Intro / Redump / Internet Archive)

Permite buscar, escolher e baixar títulos para todas as plataformas homologadas (SNES, PS1, PS2, PSP, GameCube, Dreamcast) diretamente de acervos de preservação digital oficiais, integrando o arquivo automaticamente na esteira de extração, sanitização de nomenclatura e ingestão física:

```powershell
# Busca e download interativo para qualquer plataforma
.\retrogame fetch-roms -p ps1 -q "crash"
.\retrogame fetch-roms -p ps2 -q "gran turismo"
.\retrogame fetch-roms -p psp -q "god of war"
.\retrogame fetch-roms -p gc  -q "metroid"
.\retrogame fetch-roms -p dc  -q "sonic"
.\retrogame fetch-roms -p snes -q "donkey kong"

# Atalhos por plataforma
.\retrogame fetch-snes -q "mario"
.\retrogame fetch-ps1 -q "silent hill"
```

*Comandos alternativos diretos:*
* `pwsh -NoProfile -File scripts\fetch_roms.ps1 -Platform <plat> [-Query <termo>] [-Identifier <id>]`
* `uv run retrogame-lab fetch-roms --platform <plat> [--query <termo>] [--identifier <id>]`

### 5. Lançamento Dinâmico de Jogos

Inicia o emulador da plataforma selecionada aplicando perfilamento dinâmico de GPU (dGPU vs iGPU), isolamento de diretório de trabalho (*CWD*) e afinidade protegida de CPU para P-cores em processadores híbridos. Conta ainda com **trava de pré-voo ativa**: caso uma ROM contenha espaços ou caracteres proibidos, realiza a auto-higienização física no disco antes de abrir o emulador.

```powershell
# Lançamento com detecção automática de GPU e afinidade de P-cores
.\retrogame launch -Platform ps1 -RomPath data\roms\ps1\meu_jogo.chd

# Lançamento em modo janela (-Windowed)
.\retrogame launch -Platform snes -RomPath data\roms\snes\jogo.sfc -Windowed

# Forçar uso de GPU dedicada em notebooks híbridos
.\retrogame launch -Platform ps2 -RomPath data\roms\ps2\jogo.chd -GpuMode dgpu
```

*Comandos alternativos diretos:*
* `pwsh -NoProfile -File scripts\launch.ps1 -Platform <plat> -RomPath <caminho> [-Windowed] [-GpuMode auto|igpu|dgpu]`
* `uv run retrogame-lab launch <plat> <caminho> [--windowed] [--gpu-mode auto|igpu|dgpu]`

### 6. Conversão Determinística de Mídias para CHD

Compacta imagens de disco (`.cue`/`.bin`, `.iso`) para o formato `.chd`, diferenciando automaticamente faixas de áudio CD-DA de CD-ROM (`createcd`, setor de 2352 bytes) e trilhas de dados de DVD (`createdvd`, setor de 2048 bytes), higienizando o nome do arquivo final e limpando arquivos parciais em caso de falha.

```powershell
# Comprimir mídias de CD (PS1/DC) e DVD (PS2) na pasta indicada
.\retrogame convert-chd -SourceDirectory data\roms\ps1
```

*Comandos alternativos diretos:*
* `pwsh -NoProfile -File scripts\convert_chd.ps1 -SourceDirectory <caminho> [-MediaType auto|cd|dvd]`
* `uv run retrogame-lab convert-chd <caminho> [--media-type auto|cd|dvd]`

### 7. Provisionamento do Dispositivo Android via ADB

Valida a conexão ADB, detecta a ABI do aparelho (assegurando compatibilidade ARM64), cria a árvore de diretórios `/storage/emulated/0/RetroGames/`, injeta as regras anti-conflito do `.stignore`, concede permissões de Scoped Storage (`MANAGE_EXTERNAL_STORAGE`) aos emuladores e adiciona o Syncthing à whitelist contra suspensão em segundo plano (Doze Mode).

```powershell
# Provisionamento completo do Android conectado via USB
.\retrogame android

# Provisionamento de pastas e permissões pulando o download de APKs
.\retrogame android -SkipDownload
```

*Comandos alternativos diretos:*
* `pwsh -NoProfile -File scripts\setup_android_emulators.ps1 [-DeviceId <id>] [-SkipDownload]`
* `uv run retrogame-lab setup-android [--device-id <id>] [--skip-download]`

### 8. Consulta de Metadados e Informações do Sistema

```powershell
# Exibe a tabela completa de plataformas, extensões homologadas e emuladores
.\retrogame info

# Exibe a versão instalada do pacote
.\retrogame version
```

### 9. Execução da Suíte de Testes e Qualidade de Código

O projeto adota padrões rigorosos de engenharia de software: **PEP 8 estrito**, **Google Style Docstrings**, suíte exclusiva com **`pytest`** (usando `pytest-mock` para mocks funcionais) e gerenciamento de dependências via **Astral `uv`**.

```powershell
# Execução da bateria completa de testes unitários com cobertura
uv run pytest tests/ -v --cov=retrogame_lab

# Verificação estática de tipos, formatação e boas práticas via Ruff
uv run ruff check .
uv run ruff format --check .
```

---

## Estrutura Canônica de Diretórios

```text
retrogame-lab/
├── .agents/
│   └── skills/
│       └── emulator-pipeline/      # Skill com orquestração do Agente Antigravity
├── bin/                            # Emuladores Portáteis (Zero-Install)
│   ├── dolphin/                    # GameCube / Wii (portable.txt ativo)
│   ├── duckstation/                # PS1 (portable.txt e settings.ini)
│   ├── pcsx2/                      # PS2 (portable.txt e inis/PCSX2.ini)
│   ├── ppsspp/                     # PSP (memstick/ linkado a data/saves/psp/SAVEDATA via junção)
│   ├── retroarch/                  # SNES / 2D (retroarch.cfg portátil)
│   └── flycast/                    # Dreamcast
├── data/                           # Segregação estrita do ciclo de vida dos dados
│   ├── bios/                       # Firmwares oficiais (Sincronizado via Syncthing Send-Only)
│   ├── roms/                       # Imagens de jogos compactadas (.chd, .rvz, .cso)
│   ├── saves/                      # Saves in-game (.srm, .mcd, .ps2, .gci, .bin)
│   │   └── .stignore               # Filtro anti-savestate (*.state*) e anti-locks
│   └── states/                     # Savestates locais (isolados no .stignore)
├── docs/                           # Documentação técnica e especificações de engenharia
│   ├── guia-inicio.md              # Guia de início e integração multiplataforma (Windows <-> Android)
│   ├── specs-windows.md            # Especificação técnica do host Windows 11
│   └── specs-android.md            # Especificação técnica de sincronização com Android
├── scripts/                        # Automações determinísticas em PowerShell Core (pwsh)
│   ├── bootstrap.ps1               # Provisionamento de pastas, templates e pacotes winget
│   ├── launch.ps1                  # Lançador dinâmico com trava pré-voo e perfilamento de GPU/CPU
│   ├── convert_chd.ps1             # Conversor inteligente CD vs DVD com higienização de saída
│   ├── setup_android_emulators.ps1 # Provisionamento de pastas, permissões e APKs via ADB
│   └── audit_library.ps1           # Wrapper de auditoria com saída em console ou JSON
├── src/
│   └── retrogame_lab/              # Pacote Python canônico
│       ├── __init__.py             # Metadados e versão da aplicação
│       ├── config.py               # Resolução canônica de caminhos e catálogo de plataformas
│       ├── auditor.py              # Auditoria de hashes SHA-256, extensões e regras de saves
│       ├── sanitizer.py            # Sanitização de nomenclatura (sem espaços e sem especiais)
│       ├── ingestion.py            # Pipeline de validação e importação segura de ROMs
│       └── cli.py                  # CLI Typer com rich tables e despacho para scripts
├── templates/                      # Templates pré-configurados injetados no bootstrap
│   ├── config/                     # Configurações de DuckStation, PCSX2 e RetroArch
│   ├── controllers/                # Perfis para 8BitDo Ultimate, DualSense e XInput
│   └── es-de/                      # Configurações de rotas portáteis para o ES-DE
├── tests/                          # Bateria de 55 testes unitários com pytest e pytest-mock
├── tools/                          # Utilitários portáteis e cache de instaladores
│   └── android_apks/               # Cache local de APKs para o Android (.gitkeep)
├── AGENTS.md                       # Diretrizes, padrões e governança para agentes de IA
├── pyproject.toml                  # Configuração única do projeto e dependências Astral uv
├── retrogame.cmd                   # Ponto de entrada rápido para cmd/terminal do Windows
└── retrogame.ps1                   # CLI unificada e orquestrador em PowerShell Core
```
