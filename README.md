# RetroGame Lab

> Pipeline portátil de emulação e retro-gaming para **Windows 11** (Intel 12ª Gen + NVIDIA RTX 4050) com sincronização e pareamento contínuo para **Android** (Snapdragon 8 Gen 5 / Motorola Signature) via **Syncthing** e automação via **ADB / PowerShell Core**.

Inspirado na arquitetura e filosofia de isolamento do projeto [akitaonrails/distrobox-gaming](https://github.com/akitaonrails/distrobox-gaming), adaptada para execução nativa de alto desempenho no ecossistema Windows 11 sem contêineres pesados e com interoperabilidade móvel.

---

## 🗺️ Mapa da Documentação Técnica (Living Docs)

A documentação de arquitetura e decisões de engenharia está estruturada no diretório `docs/`:

* 🖥️ **[Especificação Técnica: Pipeline Windows 11](file:///c:/WorkspaceHub/retrogame-lab/docs/specs-windows.md)**
  * Arquitetura de portabilidade estática por diretório (*Zero-Install*).
  * Matriz de calibração para NVIDIA GeForce RTX 4050 Laptop e Intel 12th Gen P-Cores.
  * Scripts de automação: `launch.ps1` (com injeção de GPU e afinidade de CPU), `convert_chd.ps1` e `bootstrap.ps1`.
  * Integração opcional com o frontend visual **ES-DE Portable**.
* 📱 **[Especificação Técnica: Sincronização e Pareamento Android](file:///c:/WorkspaceHub/retrogame-lab/docs/specs-android.md)**
  * Topologia Syncthing: saves bidirecionais com versionamento simples, BIOS e ROMs *send-only*.
  * Matriz de formatos unificados e estratégia anti-conflito de saves (*Per-Game Memory Cards*).
  * Script de provisionamento total via ADB: `setup_android_emulators.ps1` (Scoped Storage e whitelist de bateria).
  * Rotina de segurança para cross-save entre PC e smartphone.

---

## 📂 Estrutura Canônica de Diretórios

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
│   ├── launch.ps1                  # Lançador com forçagem de GPU e P-Cores
│   ├── convert_chd.ps1             # Conversor inteligente CD vs DVD
│   ├── setup_android_emulators.ps1 # Provisionamento de APKs e pastas via ADB
│   └── audit_library.ps1           # Auditoria de integridade e hashes
├── templates/                      # Mapeamentos pré-calibrados de controle e ES-DE
└── tools/                          # Utilitários portáteis (chdman, 7z, adb)
```
