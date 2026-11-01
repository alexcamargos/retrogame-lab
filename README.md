# RetroGame Lab

> Pipeline portátil e agnóstico de hardware para emulação e retro-gaming em **Windows 11** com sincronização e pareamento contínuo para dispositivos **Android ARM64** via **Syncthing** e automação via **PowerShell Core** e **ADB**.

Inspirado na arquitetura e filosofia de isolamento do projeto [akitaonrails/distrobox-gaming](https://github.com/akitaonrails/distrobox-gaming), adaptada para execução nativa de alto desempenho no ecossistema Windows 11 sem contêineres pesados e com interoperabilidade móvel.

---

## Princípios de Arquitetura

1. **Agnosticismo de Hardware com Perfilamento Dinâmico:** O ecossistema é projetado para operar em qualquer computador com Windows 11 (adaptando-se a CPUs Intel/AMD com ou sem topologia híbrida e a gráficos integrados ou GPUs dedicadas) e em qualquer dispositivo móvel Android (Smartphones, Tablets ou Consoles Portáteis ARM64). A seleção de backend, resoluções e alocação de núcleos é decidida dinamicamente no momento da execução do jogo.
2. **Baselines de Referência para Homologação:** Dispositivos específicos (como notebook com Intel 12ª Gen + RTX 4050 e smartphone com Snapdragon) foram utilizados estritamente como *benchmarks empíricos de homologação* para atestar limites de estresse térmico e estabilidade, e não como requisitos rígidos de sistema.
3. **Portabilidade Estática por Diretório (*Zero-Install*):** Toda a suíte de emulação opera com caminhos relativos em pastas isoladas, sem gravar no registro do sistema ou no `%APPDATA%`.

---

## Mapa da Documentação Técnica (Living Docs)

A documentação de arquitetura e decisões de engenharia está estruturada no diretório `docs/`:

* **[Guia Operacional para Agentes (AGENTS.md)](file:///c:/WorkspaceHub/retrogame-lab/AGENTS.md)**
  * Protocolos de automação, convenções de ferramentas e pacotes via `winget`.
  * Boas práticas de retrogaming, anti-conflito de saves e regras de perfilamento dinâmico de hardware.
* **[Especificação Técnica: Pipeline Windows 11](file:///c:/WorkspaceHub/retrogame-lab/docs/specs-windows.md)**
  * Arquitetura de portabilidade estática por diretório (*Zero-Install*).
  * Perfilamento dinâmico de CPU (P-cores) e GPU (dGPU vs iGPU).
  * Scripts de automação: `launch.ps1` (com perfilamento e isolamento de CWD), `convert_chd.ps1` e `bootstrap.ps1`.
  * Integração opcional com o frontend visual **ES-DE Portable**.
* **[Especificação Técnica: Sincronização e Pareamento Android](file:///c:/WorkspaceHub/retrogame-lab/docs/specs-android.md)**
  * Topologia Syncthing: saves bidirecionais com versionamento simples, BIOS e ROMs *send-only*.
  * Matriz de formatos unificados e estratégia anti-conflito de saves (*Per-Game Memory Cards*).
  * Script de provisionamento total via ADB: `setup_android_emulators.ps1` (Scoped Storage e detecção dinâmica de ABI).
  * Rotina de segurança para cross-save entre PC e dispositivo móvel.

---

## Guia Rápido de Comandos e Operação

### 1. Provisionamento Inicial do Host (Cold Start)

```powershell
# Cria a estrutura de pastas e marcadores de portabilidade (sem instalar ferramentas)
pwsh -NoProfile -File scripts\bootstrap.ps1 -SkipWinget

# Instalação completa de runtimes e utilitários via winget (requer terminal de Administrador)
pwsh -NoProfile -File scripts\bootstrap.ps1
```

### 2. Auditoria de Integridade de BIOS, ROMs e Saves

```powershell
# Auditoria interativa com relatório visual
pwsh -NoProfile -File scripts\audit_library.ps1

# Auditoria com saída estruturada em JSON para scripts e agentes
pwsh -NoProfile -File scripts\audit_library.ps1 -Json

# Execução direta via CLI Python
uv run retrogame-lab audit
```

### 3. Higienização e Padronização de Nomenclatura (Sem Espaços)

```powershell
# Simulação prévia das renomeações necessárias (Dry Run)
uv run retrogame-lab sanitize

# Aplicação real da padronização (converte espaços em '_' e remove aspas/especiais)
uv run retrogame-lab sanitize --apply
```

### 4. Ingestão Segura de ROMs (Validação e Roteamento)

```powershell
# Importação de arquivo único validando plataforma e higienizando nome (cópia)
uv run retrogame-lab import-rom "C:\Downloads\Super Mario World.sfc" -p snes

# Importação movendo o arquivo original para o diretório canônico data/roms/<platform>/
uv run retrogame-lab import-rom "C:\Downloads\Gran Turismo 2.chd" -p ps1 --move

# Ingestão em lote de uma pasta com múltiplas ROMs
uv run retrogame-lab import-rom "C:\Downloads\LotePS2\" -p ps2
```

### 5. Lançamento Dinâmico de Jogos

O script `launch.ps1` conta com uma **trava de segurança pré-voo (Pre-flight Gate)**: caso uma ROM adicionada manualmente contenha espaços ou caracteres especiais, ela é automaticamente higienizada no disco antes da inicialização do emulador.

```powershell
# Lançamento com detecção automática de GPU e afinidade de P-cores
pwsh -NoProfile -File scripts\launch.ps1 -Platform ps1 -RomPath data\roms\ps1\meu_jogo.chd

# Forçar uso exclusivo de GPU dedicada
pwsh -NoProfile -File scripts\launch.ps1 -Platform ps2 -RomPath data\roms\ps2\jogo.chd -GpuMode dgpu
```

### 6. Conversão Determinística de Mídias para CHD

```powershell
# Comprimir mídias de CD (PS1/DC) e DVD (PS2) preservando setores limpos
pwsh -NoProfile -File scripts\convert_chd.ps1 -SourceDirectory data\roms\ps1
```

### 7. Provisionamento do Dispositivo Android via ADB

```powershell
# Cria pastas remotas, concede permissão Scoped Storage e injeta .stignore
pwsh -NoProfile -File scripts\setup_android_emulators.ps1
```

### 8. Execução da Suíte de Testes e Qualidade de Código

```powershell
# Execução da bateria completa de testes com cobertura
uv run pytest tests/ -v --cov=retrogame_lab

# Verificação estática de tipos e formatação PEP 8 com Ruff
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
├── data/                           # Segregação estrita do ciclo de vida dos dados
│   ├── bios/                       # Firmware centralizado (Sincronizado via Syncthing Send-Only)
│   ├── roms/                       # Imagens de jogos compactadas (.chd, .rvz, .cso)
│   ├── saves/                      # Saves in-game (.srm, .mcd, .ps2, .gci, .bin)
│   └── states/                     # Savestates locais (isolados no .stignore)
├── docs/                           # Documentação e especificações de engenharia
│   ├── specs-windows.md            # Especificação do host Windows 11
│   └── specs-android.md            # Especificação da bridge Android e Syncthing
├── scripts/                        # Automação em PowerShell Core (pwsh)
│   ├── bootstrap.ps1               # Instalação automatizada do host Windows
│   ├── launch.ps1                  # Lançador dinâmico com trava pré-voo e perfilamento de GPU/CPU
│   ├── convert_chd.ps1             # Conversor inteligente CD vs DVD com higienização de saída
│   ├── setup_android_emulators.ps1 # Provisionamento de APKs e pastas via ADB
│   └── audit_library.ps1           # Auditoria de integridade e hashes
├── src/
│   └── retrogame_lab/              # Pacote Python canônico (CLI, Ingestão, Sanitizer, Auditor, Config)
├── templates/                      # Mapeamentos pré-calibrados de controle e ES-DE
│   ├── config/                     # Templates de retroarch.cfg, DuckStation e PCSX2
│   ├── controllers/                # Perfis XInput, DualSense e 8BitDo
│   └── es-de/                      # Configurações de rotas do ES-DE
├── tests/                          # Bateria de 43 testes unitários com pytest e pytest-mock
├── tools/                          # Utilitários portáteis (chdman, 7z, adb)
└── AGENTS.md                       # Diretrizes e governança para agentes de IA
```
