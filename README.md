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

## Estrutura Canônica de Diretórios

```text
retrogame-lab/
├── .agy/
│   └── skills/
│       └── emulator-pipeline/      # Orquestrador do agente no Windows
├── bin/                            # Emuladores Portáteis (Zero-Install)
├── data/                           # Segregação estrita do ciclo de vida dos dados
│   ├── bios/                       # Firmware centralizado (Sincronizado via Syncthing Send-Only)
│   ├── roms/                       # Imagens de jogos compactadas (.chd, .rvz, .cso)
│   ├── saves/                      # Saves in-game (.srm, .mcd, .ps2, .gci, .bin)
│   └── states/                     # Savestates locais (isolados no .stignore)
├── docs/                           # Documentação e especificações de engenharia
│   ├── specs-windows.md
│   └── specs-android.md
├── scripts/                        # Automação em PowerShell Core (pwsh)
│   ├── bootstrap.ps1               # Instalação automatizada do host Windows
│   ├── launch.ps1                  # Lançador dinâmico de emuladores e perfis
│   ├── convert_chd.ps1             # Conversor inteligente CD vs DVD
│   ├── setup_android_emulators.ps1 # Provisionamento de APKs e pastas via ADB
│   └── audit_library.ps1           # Auditoria de integridade e hashes
├── templates/                      # Mapeamentos pré-calibrados de controle e ES-DE
├── tools/                          # Utilitários portáteis (chdman, 7z, adb)
└── AGENTS.md                       # Diretrizes e governança para agentes de IA
```
