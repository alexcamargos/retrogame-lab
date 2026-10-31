# Guia Operacional e Instruções para Agentes Autônomos (AGENTS.md)

Este documento define as diretrizes de engenharia, padrões de desenvolvimento, protocolos de automação e boas práticas da comunidade de retrogaming que **todo agente de IA deve seguir estritamente** ao atuar no repositório `retrogame-lab`.

---

## 1. Visão Geral e Filosofia do Projeto

O **RetroGame Lab** adapta a filosofia do projeto [akitaonrails/distrobox-gaming](https://github.com/akitaonrails/distrobox-gaming) para o ambiente **Windows 11** com interoperabilidade móvel contínua para **Android** (Motorola Signature / Snapdragon 8 Gen 5):

1. **Portabilidade Estática por Diretório (*Zero-Install*):** Nenhuma configuração ou save deve depender de caminhos absolutos no `%APPDATA%`, `Program Files` ou registro do Windows para funcionar. Toda a suíte deve ser relocalizável.
2. **Automação Idempotente:** Toda tarefa de instalação, atualização, verificação ou conversão de mídias deve ser executável via scripts determinísticos em **PowerShell Core (`pwsh`)** ou utilitários em **Python 3.10+** (gerenciados via `uv`).
3. **Sincronização Híbrida Segura:** A sincronização Windows $\leftrightarrow$ Android via **Syncthing** é estritamente restrita a saves in-game (SRAM / Memory Card) e firmware/ROMs, blindada contra concorrência e conflitos de sobrescrita.

---

## 2. Stack Tecnológica e Ferramental Homologado

| Camada | Tecnologia / Ferramenta | Padrão Obrigatório de Uso |
| :--- | :--- | :--- |
| **Gerenciador de Pacotes (Host)** | **`winget` (Windows Package Manager)** | Exclusivo para instalar runtimes, ferramentas de linha de comando e aplicações do host. |
| **Shell & Scripting** | **PowerShell Core (`pwsh` v7+)** | Proibido o uso do `powershell.exe` (Windows PowerShell 5.1 legacy). Scripts com `[CmdletBinding()]` e `$ErrorActionPreference = "Stop"`. |
| **Linguagem de Programação** | **Python 3.10+** | Utilizar exclusivamente **Astral `uv`** para resolução de dependências e ambientes virtuais. Seguir estritamente PEP 8, type hints, Google Style Docstrings e testes em `pytest`. |
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

```powershell
# Runtimes de Sistema Essenciais (Obrigatórios para todos os emuladores)
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

### 4.1 Formatos de Mídia e Conversão Determinística (`chdman`)
* **Mídias baseadas em CD-ROM (PS1, Saturn, Sega CD, Dreamcast):**
  * Formatos brutos de entrada: `.cue` + `.bin`, multi-track com áudio CDDA.
  * Comando obrigatório: `chdman createcd -i arquivo.cue -o arquivo.chd`.
  * Setor bruto preservado: 2352 bytes/setor.
* **Mídias baseadas em DVD-ROM (PS2, GameCube):**
  * Formatos brutos de entrada: `.iso` de trilha de dados única.
  * Comando obrigatório: `chdman createdvd -i jogo.iso -o jogo.chd`.
  * Setor limpo preservado: 2048 bytes/setor.
  * **AVISO:** Nunca rodar `createcd` em ISOs de PS2/GC, sob pena de gerar imagens corrompidas.
* **GameCube / Wii:**
  * Preferir formato **`.rvz`** gerado pelo Dolphin (compressão Zstandard, tamanho de bloco de 128KB, preservando scrubbing determinístico).
* **PSP:**
  * Utilizar **`.cso`** (nível 9) ou **`.chd`**.

---

### 4.2 Arquitetura Anti-Conflito de Saves (Windows $\leftrightarrow$ Android)

A perda de saves por colisão de sincronização é o problema mais crítico de ecossistemas híbridos. Todo agente deve impor as seguintes regras:

1. **Proibição Estrita de Sincronizar Savestates:**
   * Savestates (`.state`, `.s01`, `.nvram.bak`) são atrelados a registradores de CPU e builds binárias (x86_64 vs ARM64). Sincronizá-los provoca falhas graves.
   * Manter sempre o arquivo `.stignore` em `data/saves/.stignore` contendo `*.state*`, `*.tmp` e `(?d).syncthing.*`.
2. **Padrão de Cartão de Memória Individual por Jogo (*Title-specific Memory Card*):**
   * **Proibição:** É estritamente vedado configurar cartões de memória compartilhados globais (ex.: um único `shared_card_1.mcd` ou `Mcd001.ps2` para toda a biblioteca).
   * **Padrão Homologado:**
     * **PS1 (DuckStation):** Cartão individual por título (`data/saves/ps1/<Title>_<ID>.mcd`).
     * **PS2 (PCSX2 / NetherSX2):** Cartão individual por título (`data/saves/ps2/<Title>_<ID>.ps2`) ou *Folder Memory Card*.
     * **SNES:** Arquivo `.srm` com nome idêntico à ROM em `data/saves/snes/<NomeDaRom>.srm`.
     * **GameCube (Dolphin):** Modo GCI individual (`data/saves/gc/USA/Card A/<GameID>.gci`).
     * **Dreamcast (Flycast):** VMU dedicado (`data/saves/dc/vmu_save_A1.bin`).
3. **Protocolo de Encerramento e Flush de Disco:**
   * Emuladores mantêm dados de save em buffer de RAM enquanto estão abertos. Instrua o usuário ou automações a **fechar o emulador** antes de alternar de dispositivo.
   * Aguardar o gatilho inotify/file-watcher do Syncthing (2 a 5 segundos na LAN) antes de iniciar a sessão no outro aparelho.

---

## 5. Diretrizes de Engenharia para o Host Windows 11

Ao escrever scripts ou executar comandos de inicialização de emuladores no Windows 11:

### 5.1 Forçagem Determinística da GPU Dedicada (RTX 4050 Laptop)
* Variáveis de ambiente como `DXVK_FILTER_DEVICE_NAME` **não têm efeito** em backends Vulkan ou Direct3D 12 nativos.
* Os agentes devem forçar a preferência de alto desempenho gravando diretamente no registro do Windows:
  ```powershell
  $RegPath = "HKCU:\Software\Microsoft\DirectX\UserGpuPreferences"
  if (-not (Test-Path $RegPath)) { New-Item -Path $RegPath -Force | Out-Null }
  Set-ItemProperty -Path $RegPath -Name (Resolve-Path $EmulatorExe).Path -Value "GpuPreference=2;"
  ```

### 5.2 Afinidade de CPU para Arquiteturas Híbridas (Intel 12ª Gen P-Cores)
* Para emuladores com demanda intensiva de IPC e temporização (PCSX2, Dolphin), vincular o processo aos **Performance-cores (P-cores 0 a 7)** para evitar quedas de performance causadas pelo Thread Director nos E-cores:
  ```powershell
  $Process = Start-Process -FilePath $EmulatorExe -ArgumentList $ArgList -PassThru
  # Máscara binária para os primeiros 8 threads lógicos (P-Cores)
  $Process.ProcessorAffinity = [IntPtr]0x00FF
  ```

### 5.3 Isolamento do Diretório de Trabalho (*Working Directory Isolation*)
* Sempre encapsular a chamada dos emuladores com `Push-Location (Split-Path $EmulatorExe)` e `Pop-Location`.
* Executar o executável a partir de outra pasta faz com que emuladores despejem arquivos temporários e logs no CWD ativo, quebrando o isolamento portátil.

---

## 6. Diretrizes de Engenharia para o Ecossistema Android

Ao desenvolver scripts de pareamento via ADB ou automações para o dispositivo móvel:

### 6.1 Tratamento do Scoped Storage (Android 11+)
* O comando `adb install -g` **não concede** a permissão especial de gerenciamento total de arquivos.
* O script ADB deve obrigatoriamente executar a concessão explícita para cada emulador instalado:
  ```powershell
  adb shell "appops set <PackageName> MANAGE_EXTERNAL_STORAGE allow"
  ```

### 6.2 Prevenção contra Doze Mode no Syncthing
* Para impedir que o sistema operacional Android finalize o Syncthing em segundo plano e bloqueie a sincronização de saves, adicionar o pacote à whitelist de economia de energia:
  ```powershell
  adb shell "dumpsys deviceidle whitelist +com.nutomic.syncthingcb"
  ```

### 6.3 Estrutura de Diretórios Canônica no Armazenamento Interno
* Todos os emuladores no Android devem apontar para:
  * `/storage/emulated/0/RetroGames/bios/`
  * `/storage/emulated/0/RetroGames/roms/<plataforma>/`
  * `/storage/emulated/0/RetroGames/saves/<plataforma>/`

---

## 7. Padrões de Código, Testes e Governança do Repositório

1. **Python (se aplicável):**
   * Versão: Python 3.10+.
   * Gerenciador: Astral `uv` exclusivamente (`uv run`, `uv add`, `uv test`). Proibido sugerir `pip install` solto.
   * Framework de Testes: Exclusivamente `pytest` e `pytest-mock` (fixture `mocker`). Proibido o uso de `unittest` ou `unittest.TestCase`.
   * Padrão de Estilo: PEP 8 estrito e Google Style Docstrings em todos os módulos, classes e funções.
2. **Git e Versionamento:**
   * Commits atômicos e granulares (1 a 2 arquivos por commit).
   * Padrão semântico: *Conventional Commits* (`feat`, `fix`, `docs`, `chore`, `refactor`, `perf`).
   * Idioma: Português do Brasil (pt-BR), tom imperativo e conciso (ex.: `docs(agents): criar instrucoes para agentes autonomos`).
   * Higiene: Proibido versionar dados brutos/processados (`data/`), credenciais, binários (`bin/`, `tools/`) ou ambientes de teste (`scratch/`).
3. **Ambiente Volátil (*Scratch*):**
   * Scripts pontuais de debug, dumps temporários de ROMs e arquivos de teste descartáveis devem residir em `scratch/` (estritamente ignorado no `.gitignore`).
