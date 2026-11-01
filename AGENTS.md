# Guia Operacional e Instruções para Agentes Autônomos (AGENTS.md)

Este documento define as diretrizes de engenharia, padrões de desenvolvimento, protocolos de automação e boas práticas da comunidade de retrogaming que **todo agente de IA deve seguir estritamente** ao atuar no repositório `retrogame-lab`.

---

## 1. Visão Geral e Filosofia do Projeto

O **RetroGame Lab** adapta a filosofia do projeto [akitaonrails/distrobox-gaming](https://github.com/akitaonrails/distrobox-gaming) para o ambiente **Windows 11** com interoperabilidade móvel contínua para **Android** (qualquer dispositivo ARM64):

1. **Arquitetura Estritamente Agnóstica de Hardware:** O sistema não assume uma CPU, GPU ou aparelho móvel fixo. A decisão de emulador, backend gráfico (Vulkan/D3D), escala de resolução e afinidade de threads é tomada dinamicamente no momento da seleção do jogo e análise de capacidades do host. Hardwares específicos (como PCs com Intel 12ª Gen + RTX 4050 ou smartphones Snapdragon) são meros **baselines empíricos de homologação**, e nunca requisitos estáticos.
2. **Portabilidade Estática por Diretório (*Zero-Install*):** Nenhuma configuração ou save deve depender de caminhos absolutos no `%APPDATA%`, `Program Files` ou registro do Windows para funcionar. Toda a suíte deve ser relocalizável.
3. **Automação Idempotente:** Toda tarefa de instalação, atualização, verificação ou conversão de mídias deve ser executável via scripts determinísticos em **PowerShell Core (`pwsh`)** ou utilitários em **Python 3.10+** (gerenciados via `uv`).
4. **Sincronização Híbrida Segura:** A sincronização Windows $\leftrightarrow$ Android via **Syncthing** é estritamente restrita a saves in-game (SRAM / Memory Card) e firmware/ROMs, blindada contra concorrência e conflitos de sobrescrita.

---

## 2. Stack Tecnológica e Ferramental Homologado

| Camada | Tecnologia / Ferramenta | Padrão Obrigatório de Uso |
| :--- | :--- | :--- |
| **Gerenciador de Pacotes (Host)** | **`winget` (Windows Package Manager)** | Exclusivo para instalar runtimes, ferramentas de linha de comando e aplicações do host. |
| **Shell & Scripting** | **PowerShell Core (`pwsh` v7+)** | Proibido o uso do `powershell.exe` (Windows PowerShell 5.1 legacy). Scripts com `[CmdletBinding()]` e `$ErrorActionPreference = "Stop"`. |
| **Linguagem & Ambientes Python** | **Python 3.10+ (Astral `uv` / `uvx`)** | `uv` para dependências do projeto (`uv run`, `uv add`). Uso obrigatório de `uvx` para executar ferramentas CLI externas isoladas. PEP 8, Google Docstrings e `pytest`. |
| **Mobile Bridge** | **ADB (Android Debug Bridge)** | Comunicação via USB/Wi-Fi Debugging para provisionamento de pastas e APKs no Android. |
| **Camada de Sincronização** | **Syncthing** | Sincronização local em LAN/Wi-Fi, portas `8384` (GUI) e `22000` (Sync). |
| **Mídia e Compressão** | **MAME `chdman`** e **7-Zip (`7z`)** | Compactação estruturada por blocos para imagens de disco. |

---

## 3. Protocolo de Instalação e Provisionamento com `winget`

Sempre que um agente precisar instalar ferramentas de suporte, runtimes ou utilitários no Windows 11, deve utilizar comandos `winget` padronizados com as flags `--exact`, `--source winget`, `--silent` e aceitação automática de termos:

```powershell
winget install --id <Package.ID> --exact --source winget --silent --accept-package-agreements --accept-source-agreements
```

### 3.1 Pacotes Canônicos Homologados para o Host

> [!NOTE]
> **Elevação de Privilégios (Administrador):**  
> A instalação de runtimes de sistema (`Microsoft.VCRedist.2015+.x64` e `Microsoft.DirectX`) requer execução em terminal com privilégios de Administrador. As demais ferramentas podem ser provisionadas em nível de usuário.

```powershell
# Runtimes de Sistema Essenciais (Obrigatórios para todos os emuladores - Requer Admin)
winget install --id Microsoft.VCRedist.2015+.x64 -e --source winget --silent --accept-package-agreements --accept-source-agreements
winget install --id Microsoft.DirectX -e --source winget --silent --accept-package-agreements --accept-source-agreements

# Ferramentas de Linha de Comando e Automação
winget install --id Microsoft.PowerShell -e --source winget --silent --accept-package-agreements --accept-source-agreements
winget install --id Git.Git -e --source winget --silent --accept-package-agreements --accept-source-agreements
winget install --id 7zip.7zip -e --source winget --silent --accept-package-agreements --accept-source-agreements
winget install --id Google.PlatformTools -e --source winget --silent --accept-package-agreements --accept-source-agreements
winget install --id Syncthing.Syncthing -e --source winget --silent --accept-package-agreements --accept-source-agreements
winget install --id Astral-sh.uv -e --source winget --silent --accept-package-agreements --accept-source-agreements
```

> [!IMPORTANT]
> **Diretriz de Portabilidade dos Emuladores:**  
> Ao instalar ou extrair emuladores para a pasta `bin/`, garanta que o modo portátil esteja ativo antes de qualquer execução:
> * **PCSX2:** Criar arquivo vazio `bin/pcsx2/portable.txt`.
> * **DuckStation:** Criar arquivo vazio `bin/duckstation/portable.txt`.
> * **Dolphin:** Criar arquivo vazio `bin/dolphin/portable.txt`.
> * **RetroArch:** Fornecer `bin/retroarch/retroarch.cfg` configurado com caminhos relativos (sem `portable.ini`).
> * **PPSSPP:** Garantir a pasta `bin/ppsspp/memstick/`.

---

## 4. Práticas Canônicas da Comunidade de Retrogaming

### 4.1 Formatos de Mídia e Conversão Determinística (`chdman` e `Dolphin`)
* **Mídias baseadas em CD-ROM (PS1, Saturn, Sega CD, Dreamcast):**
  * Formatos brutos de entrada: `.cue` + `.bin`, multi-track com áudio CDDA.
  * Comando obrigatório: `chdman createcd -i arquivo.cue -o arquivo.chd`.
  * Setor bruto preservado: 2352 bytes/setor.
* **Mídias baseadas em DVD-ROM (PS2):**
  * Formatos brutos de entrada: `.iso` de trilha de dados única de PS2.
  * Comando obrigatório: `chdman createdvd -i jogo.iso -o jogo.chd`.
  * Setor limpo preservado: 2048 bytes/setor.
  * **AVISO:** Nunca rodar `createcd` em ISOs de DVD, sob pena de gerar imagens corrompidas.
* **GameCube / Wii:**
  * **Proibição:** Nunca converter GameCube/Wii para `.chd` com `chdman`.
  * **Padrão Homologado:** Formato **`.rvz`** gerado nativamente pelo Dolphin (`Dolphin.exe -b -e input.iso --convert-to-rvz --rvz-block-size=131072 -o output.rvz`), utilizando compressão Zstandard e preservando scrubbing determinístico.
* **PSP:**
  * Utilizar **`.cso`** (nível 9) ou **`.chd`**.

---

### 4.2 Arquitetura Anti-Conflito de Saves (Windows $\leftrightarrow$ Android)

A perda de saves por colisão de sincronização é o problema mais crítico de ecossistemas híbridos. Todo agente deve impor as seguintes regras:

1. **Proibição Estrita de Sincronizar Savestates:**
   * Savestates (`.state`, `.s01`, `.nvram.bak`) são atrelados a registradores de CPU e builds binárias (x86_64 vs ARM64). Sincronizá-los provoca falhas graves.
   * Manter sempre o arquivo `.stignore` em `data/saves/.stignore` contendo `*.state*`, `*.tmp*`, `*.lock*`, `*.lck`, `*.wal`, `*.shm` e `(?d).syncthing.*`.
2. **Padrão de Cartão de Memória Individual por Jogo (*Title-specific Memory Card*):**
   * **Proibição:** É estritamente vedado configurar cartões de memória compartilhados globais (ex.: um único `shared_card_1.mcd` ou `Mcd001.ps2` para toda a biblioteca).
   * **Padrão Homologado:**
     * **PS1 (DuckStation):** Cartão individual por título (`data/saves/ps1/<Title>_<ID>.mcd`).
     * **PS2 (PCSX2 / NetherSX2):** Cartão individual por título (`data/saves/ps2/<Title>_<ID>.ps2`) ou *Folder Memory Card*.
     * **SNES:** Arquivo `.srm` com nome idêntico à ROM em `data/saves/snes/<NomeDaRom>.srm`.
     * **GameCube (Dolphin):** Modo GCI individual / Pastas de Região em `data/saves/gc/`.
     * **Dreamcast (Flycast):** VMU padrão (`data/saves/dc/vms0.bin`).
3. **Protocolo de Encerramento e Flush de Disco:**
   * Emuladores mantêm dados de save em buffer de RAM enquanto estão abertos. Instrua o usuário ou automações a **fechar o emulador** antes de alternar de dispositivo.
   * Aguardar o gatilho inotify/file-watcher do Syncthing (2 a 5 segundos na LAN) antes de iniciar a sessão no outro aparelho.

---

### 4.3 Padrão Canônico de Nomenclatura de Arquivos e Ingestão Segura de ROMs

1. **Proibição Estrita de Espaços e Caracteres Especiais:**
   * Nomes de arquivos de ROMs, firmwares de BIOS e saves **nunca devem conter espaços** nem caracteres especiais (`'"~^!?\:;*<>|#`).
   * Espaços devem ser sempre convertidos para sublinhado (`_`).
   * Caracteres especiais e pontuações perigosas para linhas de comando e filesystems móveis (FAT32/exFAT) devem ser eliminados.
   * As extensões devem permanecer sempre em letras minúsculas (ex.: `.chd`, `.rvz`, `.sfc`, `.mcd`).
2. **Dupla Camada de Blindagem (Dual-Layer Guard):**
   * **Camada de Ingestão (`uv run retrogame-lab import-rom`):** Toda inclusão de novos títulos deve ser processada através do pipeline em `src/retrogame_lab/ingestion.py`, garantindo validação de formatos autorizados para a plataforma e higienização automática do nome antes de gravar em `data/roms/<plataforma>/`.
   * **Camada Pré-Voo no Lançador (`scripts/launch.ps1`):** O script lançador atua como barreira secundária (*fail-safe*). Caso uma ROM tenha sido depositada manualmente na pasta contendo espaços ou caracteres proibidos, o lançador detecta a anomalia via regex e realiza a auto-higienização física no disco antes de invocar o emulador.
3. **Higienização em Massa da Biblioteca:**
   * Agentes e operadores dispõem do comando `uv run retrogame-lab sanitize [--apply]` para auditar e normalizar toda a árvore de arquivos de ROMs e saves de forma idempotente.

---

## 5. Diretrizes de Engenharia e Adaptação Dinâmica de Hardware (Windows 11)

Ao escrever scripts ou executar comandos de inicialização de emuladores no Windows 11, os agentes devem respeitar o princípio de agnoticismo de hardware:

### 5.1 Perfilamento Dinâmico de GPU (dGPU vs iGPU)
* Agentes **nunca devem assumir um modelo estático de GPU** (como RTX 4050).
* O script deve inspecionar dinamicamente se há uma GPU dedicada (NVIDIA, AMD Radeon ou Intel Arc) presente via `Win32_VideoController`.
* Caso identificada uma dGPU em sistema híbrido (notebook ou desktop com iGPU), registrar a preferência de alto desempenho:
  ```powershell
  $RegPath = "HKCU:\Software\Microsoft\DirectX\UserGpuPreferences"
  if (-not (Test-Path $RegPath)) { New-Item -Path $RegPath -Force | Out-Null }
  Set-ItemProperty -Path $RegPath -Name (Resolve-Path $EmulatorExe).Path -Value "GpuPreference=2;"
  ```
* Em sistemas operando exclusivamente com iGPU, o orquestrador deve calibrar resoluções e shaders para perfis leves (1x a 2x nativo).

### 5.2 Afinidade Dinâmica de CPU para Topologias Heterogêneas
* Para emuladores com demanda intensiva de IPC e temporização (PCSX2, Dolphin), o agente deve inspecionar se a CPU possui arquitetura heterogênea (ex.: Intel 12ª Gen+ P-Cores e E-Cores).
* Somente em CPUs híbridas deve-se vincular o processo aos **Performance-cores (P-cores 0 a 7)**. Em arquiteturas homogêneas (AMD Ryzen ou Intel clássico), o escalonamento deve permanecer livre:
  ```powershell
  $Process = Start-Process -FilePath $EmulatorExe -ArgumentList $ArgList -PassThru
  if ($IsHybridCpu) {
      $Process.ProcessorAffinity = [IntPtr]0x00FF
  }
  ```

### 5.3 Isolamento do Diretório de Trabalho (*Working Directory Isolation*)
* Sempre encapsular a chamada dos emuladores com `Push-Location (Split-Path $EmulatorExe)` e `Pop-Location`.
* Executar o executável a partir de outra pasta faz com que emuladores despejem arquivos temporários e logs no CWD ativo, quebrando o isolamento portátil.

---

## 6. Diretrizes de Engenharia para o Ecossistema Android (Qualquer ARM64)

Ao desenvolver scripts de pareamento via ADB ou automações para o dispositivo móvel:

### 6.1 Detecção Dinâmica de Arquitetura via ADB
* Validar dinamicamente o modelo e a ABI do dispositivo conectado via `adb shell "getprop ro.product.cpu.abi"` para assegurar compatibilidade ARM64 antes do download de APKs.

### 6.2 Tratamento do Scoped Storage (Android 11+)
* O comando `adb install -g` **não concede** a permissão especial de gerenciamento total de arquivos.
* O script ADB deve obrigatoriamente executar a concessão explícita para cada emulador instalado:
  ```powershell
  adb shell "appops set <PackageName> MANAGE_EXTERNAL_STORAGE allow"
  ```

### 6.3 Prevenção contra Doze Mode no Syncthing
* Para impedir que o sistema operacional Android finalize o Syncthing em segundo plano e bloqueie a sincronização de saves, adicionar o pacote à whitelist de economia de energia:
  ```powershell
  adb shell "dumpsys deviceidle whitelist +com.nutomic.syncthingcb"
  ```

### 6.4 Estrutura de Diretórios Canônica no Armazenamento Interno
* Todos os emuladores no Android devem apontar para:
  * `/storage/emulated/0/RetroGames/bios/`
  * `/storage/emulated/0/RetroGames/roms/<plataforma>/`
  * `/storage/emulated/0/RetroGames/saves/<plataforma>/`

---

## 7. Padrões de Código, Testes e Governança do Repositório

1. **Python e Ecossistema Astral (`uv` / `uvx`):**
   * **Versão:** Python 3.10+.
   * **Gerenciador:** Astral `uv` exclusivamente (`uv run`, `uv add`, `uv test`). Proibido sugerir `pip install` solto.
   * **Execução de Ferramentas CLI Externas via `uvx`:**
     * Sempre que o projeto necessitar de uma ferramenta executável em Python (que não seja uma biblioteca interna de suporte importada no código-fonte, mas sim uma ferramenta autônoma CLI para auditoria, scraping, conversão, linting ou geração de artefatos), **é obrigatório utilizar o `uvx`** (ex.: `uvx <ferramenta>==<versao>`).
     * O `uvx` garante que uma versão específica e isolada da ferramenta seja criada e executada sob demanda para o projeto, sem poluir o ambiente de dependências da aplicação nem o sistema host.
   * **Framework de Testes:** Exclusivamente `pytest` e `pytest-mock` (fixture `mocker`). Proibido o uso de `unittest` ou `unittest.TestCase`.
   * **Padrão de Estilo:** PEP 8 estrito e Google Style Docstrings em todos os módulos, classes e funções.
2. **Git e Versionamento:**
   * Commits atômicos e granulares (1 a 2 arquivos por commit).
   * Padrão semântico: *Conventional Commits* (`feat`, `fix`, `docs`, `chore`, `refactor`, `perf`).
   * Idioma: Português do Brasil (pt-BR), tom imperativo e conciso (ex.: `docs(agents): criar instrucoes para agentes autonomos`).
   * Higiene: Proibido versionar dados brutos/processados (`data/`), credenciais, binários (`bin/`, `tools/`) ou ambientes de teste (`scratch/`).
3. **Ambiente Volátil (*Scratch*):**
   * Scripts pontuais de debug, dumps temporários de ROMs e arquivos de teste descartáveis devem residir em `scratch/` (estritamente ignorado no `.gitignore`).
