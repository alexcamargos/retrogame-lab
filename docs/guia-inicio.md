# Guia de Inicio e Integracao Multiplataforma (Windows 11 <---> Android)

Este guia orienta passo a passo a configuracao do ecossistema **RetroGame Lab**, desde o provisionamento inicial no **Windows 11** ate a integracao sem erros com dispositivos **Android ARM64** (Smartphones, Tablets ou consoles dedicados como Ayn Odin, Retroid Pocket e Anbernic) utilizando **Syncthing** e automacao via **PowerShell Core (`pwsh`)** e **ADB**.

---

## 1. Visao Geral da Arquitetura e Fluxo de Dados

O ecossistema opera sob o principio de **Portabilidade Estatica (Zero-Install)** no computador e espelhamento higienizado no dispositivo movel:

* **Saves de Jogo (Bidirecional / Send-Receive):** Seus dados de progresso (*in-game saves*, memory cards e arquivos `.srm`) sao sincronizados entre o PC e o Android. Alteracoes feitas em um aparelho sao refletidas no outro.
* **Firmwares de BIOS (Unidirecional / Send-Only do PC):** Mantidos de forma centralizada e auditada no Windows e transmitidos apenas para leitura no Android.
* **ROMs e Imagens de Disco (Unidirecional / Send-Only do PC):** Ingeridas, compactadas (`.chd`, `.rvz`, `.cso`) e higienizadas no Windows antes do envio para o Android.
* **Savestates (Isolamento Estrito):** Estados congelados de emulador (`*.state*`) **nunca sao sincronizados** entre arquiteturas distintas (x86_64 vs ARM64) devido a diferencas de registradores e compilacao, evitando falhas e travamentos.

---

## 2. Etapa 1: Provisionamento e Configuracao no Windows 11

### 2.1 Pre-requisitos do Sistema Host
* **Sistema Operacional:** Windows 11 (qualquer CPU x86_64, com iGPU integrada ou dGPU dedicada).
* **Terminal:** PowerShell Core 7+ (`pwsh`).
* **Gerenciador de Dependencias:** Astral `uv` para executar o CLI Python.
* **Permissoes:** Acesso de Administrador no terminal apenas para a instalacao inicial de runtimes de sistema (DirectX e Visual C++).

### 2.2 Execucao do Bootstrap Automatizado
Abra o **PowerShell 7 (`pwsh`)** como Administrador na raiz do repositorio e execute o orquestrador unificado (ou o script direto):

```powershell
# Provisionamento completo de runtimes (winget), pastas, templates e marcadores portateis
.\retrogame bootstrap

# Ou diretamente via script PowerShell:
pwsh -NoProfile -File scripts\bootstrap.ps1
```

O script executara de forma idempotente:
1. Instalacao dos pacotes necessarios via `winget` (`Microsoft.VCRedist.2015+.x64`, `Microsoft.DirectX`, `Google.PlatformTools`, `Syncthing.Syncthing`, `7zip.7zip`, `Astral-sh.uv`, `Git.Git`).
2. Criacao da estrutura de diretorios em `data/` (`bios`, `roms`, `saves`, `states`) e `bin/`.
3. Criacao dos marcadores de portabilidade (`portable.txt`) para PCSX2, DuckStation e Dolphin.
4. Vinculacao da pasta `bin/ppsspp/memstick/PSP/SAVEDATA` a `data/saves/psp/SAVEDATA/` via juncao NTFS.
5. Injecao dos templates pre-configurados de `templates/config/` (direcionando saves e BIOS para caminhos relativos de `data/`).

### 2.3 Download e Instalacao dos Emuladores Portateis no Windows 11

O RetroGame Lab adota a filosofia de **Portabilidade Estatica (Zero-Install)**: os emuladores nao sao instalados no sistema operacional via instaladores `.exe`/`.msi` nem gravam no registro do Windows ou `%APPDATA%`. Eles operam de forma autocontida a partir de subpastas em `bin/`.

Voce pode provisionar os emuladores de forma automatizada (recomendado) ou manual:

#### Opcao A: Download Automatizado (Recomendado)
Execute o comando unificado para baixar e descompactar as builds portateis oficiais de 64 bits para cada plataforma:

```powershell
# Baixa e configura todos os emuladores homologados em bin/
.\retrogame download-emulators

# Ou durante o bootstrap inicial:
.\retrogame bootstrap -DownloadEmulators

# Para baixar apenas emuladores especificos:
.\retrogame download-emulators -Emulators pcsx2,duckstation
```

O script automatiza:
* Consulta as releases mais recentes via GitHub API e buildbots oficiais.
* Baixa os arquivos compactados (`.zip` e `.7z`) e extrai diretamente em `bin/<emulador>/`.
* Garante a criacao dos arquivos de portabilidade (`portable.txt`) e preserva os templates injetados.
* Baixa e instala automaticamente o core Libretro `snes9x_libretro.dll` em `bin/retroarch/cores/` (sem necessidade de navegacao em menus).
* Caso um jogo de SNES seja iniciado pelo lancador sem o core presente, o proprio `launch.ps1` realiza o auto-provisionamento em tempo de execucao.

#### Checagem e Atualizacao de Emuladores
O gerenciador mantem um manifesto local em `bin/.versions.json` rastreando a versao exata de cada emulador:

```powershell
# Compara as versoes instaladas contra as releases oficiais disponiveis (sem baixar nada)
.\retrogame check-updates

# Atualiza apenas os emuladores que possuem versoes mais novas disponiveis
.\retrogame update-emulators

# Forca a reinstalacao/re-download de emuladores especificos
.\retrogame download-emulators -Force -Emulators pcsx2,duckstation
```

#### Opcao B: Download e Extracao Manual
Caso prefira baixar manualmente, faca o download das versoes portateis oficiais (Windows x64) e extraia o conteudo de cada pacote diretamente dentro da subpasta indicada em `bin/`:

| Plataforma / Sistema | Pasta de Destino | Executavel Esperado | Pacote Portatil Oficial Homologado |
| :--- | :--- | :--- | :--- |
| **SNES / 2D** (RetroArch) | `bin/retroarch/` | `retroarch.exe` | [RetroArch Windows x86_64 (.7z)](https://www.retroarch.com/?page=platforms)<br>*(O core Snes9x e baixado automaticamente ao executar `.\retrogame download-emulators` ou ao iniciar um jogo)* |
| **PlayStation 1** (DuckStation) | `bin/duckstation/` | `duckstation-qt.exe` | [DuckStation Releases](https://github.com/stenzek/duckstation/releases) (`duckstation-windows-x64-release.zip`) |
| **PlayStation 2** (PCSX2) | `bin/pcsx2/` | `pcsx2-qt.exe` | [PCSX2 Releases](https://pcsx2.net/downloads) (`pcsx2-v...-windows-x64-Qt.7z`) |
| **PSP** (PPSSPP) | `bin/ppsspp/` | `PPSSPPWindows64.exe` | [PPSSPP Download](https://www.ppsspp.org/download/) (`PPSSPP Windows zip` portatil) |
| **GameCube / Wii** (Dolphin) | `bin/dolphin/` | `Dolphin.exe` | [Dolphin Emulator](https://dolphin-emu.org/download/) (`Windows x64 7z` portatil) |
| **Dreamcast** (Flycast) | `bin/flycast/` | `flycast.exe` | [Flycast Releases](https://github.com/flyinghead/flycast/releases) (`flycast-win64.zip`) |
| **Frontend** (ES-DE Opcional) | `bin/es-de/` | `ES-DE.exe` | [ES-DE Frontend](https://es-de.org/) (`Portable Release .zip`) |

> [!IMPORTANT]
> **Marcador de Portabilidade:**  
> Apos extrair manualmente, certifique-se de que o arquivo vazio `portable.txt` continue presente dentro de `bin/duckstation/`, `bin/pcsx2/` e `bin/dolphin/` para forcar o armazenamento local de configuracoes.

### 2.4 Ativacao do Ambiente Python do Repositorio
No mesmo terminal (ou em sessao comum sem elevacao):

```powershell
# Instala dependencias locais e ferramentas de auditoria via Astral uv
uv sync

# Valida a instalacao da CLI e visualiza as plataformas suportadas
.\retrogame info

# Ou diretamente via CLI Python:
uv run retrogame-lab info
```

---

## 3. Etapa 2: Organizacao de BIOS, ROMs e Higienizacao

### 3.1 Adicao de Firmwares de BIOS
Deposite os firmwares oficiais nas pastas correspondentes em `data/bios/`:
* **PS1:** `data/bios/ps1/scph1001.bin` ou `scph5501.bin`.
* **PS2:** `data/bios/ps2/scph39001.bin`.
* **Dreamcast:** `data/bios/dc/boot.bin`.

### 3.2 Ingestao Segura de Jogos (ROMs)
> [!IMPORTANT]
> **Proibicao de Espacos e Caracteres Especiais:**  
> Sistemas de arquivos moveis (FAT32/exFAT) e emuladores baseados em Android frequentemente falham ou criam saves duplicados ao lidar com espacos (` `) ou caracteres como `'`, `"`, `~`, `!`, `#`.

Utilize sempre o comando oficial de ingestao para adicionar jogos:

```powershell
# Importa uma ROM individual sanitizando o nome e validando a extensao (modo copia)
.\retrogame import-rom "data\temp\Super Mario World.sfc" -p snes

# Importa movendo o arquivo original para data/roms/<plataforma>/
.\retrogame import-rom "data\temp\Gran Turismo 2.chd" -p ps1 --move

# Importa em lote uma pasta inteira de jogos
.\retrogame import-rom "data\temp\LotePS2\" -p ps2
```

Caso voce tenha depositado arquivos manualmente:
```powershell
# Simula a correcao dos nomes (Dry Run)
.\retrogame sanitize

# Aplica a correcao no disco (substitui espacos por '_' e remove caracteres especiais)
.\retrogame sanitize --apply
```

### 3.3 Ingestao Direta de Jogos Preservados (No-Intro / Redump / Internet Archive)
Para usuarios que possuem as midias fisicas originais mas nao dispoem de leitor optico ou gravador USB no momento, o RetroGame Lab disponibiliza uma interface integrada de busca e download conectada aos acervos oficiais de preservacao digital (*No-Intro* para cartuchos e *Redump* para midias opticas):

```powershell
# Busca e download interativo para qualquer plataforma homologada
.\retrogame fetch-roms -p ps1 -q "crash"
.\retrogame fetch-roms -p ps2 -q "gran turismo"
.\retrogame fetch-roms -p psp -q "patapon"
.\retrogame fetch-roms -p gc  -q "metroid"
.\retrogame fetch-roms -p dc  -q "sonic"
.\retrogame fetch-roms -p snes -q "mario"

# Ou utilizando os atalhos diretos por plataforma:
.\retrogame fetch-ps1 -q "resident evil"
.\retrogame fetch-snes -q "donkey kong"

# Especificando uma colecao/identificador alternativo no Internet Archive:
.\retrogame fetch-roms -p ps1 -i "minha-colecao-customizada"
```

O fluxo:
1. Consulta e armazena em cache local (`scratch/cache_<identificador>_files.json`) a lista de titulos catalogados.
2. Apresenta uma tabela interativa com numeracao, titulos e tamanho estimado.
3. Permite selecionar um ou varios jogos simultaneamente (ex: `1` ou `1, 3, 5`), pesquisar novos termos (`/busca <termo>`) ou alternar colecoes (`/colecao <id>`).
4. Baixa o arquivo para a area contabilmente isolada em `scratch/downloads/`.
5. Extrai a imagem no formato homologado (ex.: `.chd` para PS1/DC, `.rvz` para GC, `.sfc` para SNES, `.cso` ou `.iso` para PSP).
6. Aciona automaticamente a esteira de `import_rom` com sanitizacao de nome (substituindo espacos por `_`), validacao estrutural e destino canonico em `data/roms/<plataforma>/`.

### 3.4 Compressao de Discos (CD/DVD)
Para converter pastas contendo `.cue`/`.bin` ou `.iso` de PS1, PS2 e Dreamcast em arquivos compactados `.chd`:

```powershell
.\retrogame convert-chd -SourceDirectory data\roms\ps1
```

> [!NOTE]
> Mídias de GameCube e Wii nao devem ser convertidas para `.chd`. O formato canonico homologado e **`.rvz`**, gerado nativamente pelo proprio Dolphin (`Dolphin.exe -b -e input.iso --convert-to-rvz`).

---

## 4. Etapa 3: Preparacao e Provisionamento do Android via ADB

### 4.1 Habilitacao da Depuracao USB no Android
1. No dispositivo Android, acesse **Configuracoes** $\rightarrow$ **Sobre o telefone**.
2. Toque no item **Numero da versao** (ou *Build Number*) **7 vezes** consecutivas para liberar as **Opcoes do desenvolvedor**.
3. Va em **Sistema / Configuracoes Adicionais** $\rightarrow$ **Opcoes do desenvolvedor**.
4. Ative a chave **Depuracao USB** (*USB Debugging*).
5. Conecte o aparelho ao PC via cabo USB.
6. Na tela do Android, confirme a caixa de dialogo **Permitir a depuracao USB?** e marque **Sempre permitir a partir deste computador**.

### 4.2 Execucao do Provisionamento Automatizado
No PC com PowerShell Core, execute:

```powershell
# Provisiona diretorios, permissoes Scoped Storage e emuladores no Android via ADB
.\retrogame android

# Ou diretamente pelo script:
pwsh -NoProfile -File scripts\setup_android_emulators.ps1
```

O script realiza automaticamente todas as configuracoes criticas de sistema:
1. **Identificacao da ABI:** Confirma que o processador e `arm64-v8a`.
2. **Estrutura de Pastas:** Cria `/storage/emulated/0/RetroGames/` com subpastas `bios/`, `roms/` e `saves/` particionadas por plataforma.
3. **Injecao de Seguranca:** Grava o arquivo `/storage/emulated/0/RetroGames/saves/.stignore` para impedir o envio de savestates e arquivos de trava.
4. **Bypass de Scoped Storage:** Concede a permissao especial `MANAGE_EXTERNAL_STORAGE` para os pacotes dos emuladores via `appops`, permitindo leitura e gravacao direta em `/storage/emulated/0/RetroGames/`.
5. **Whitelist de Bateria (Doze Mode):** Adiciona os pacotes do Syncthing a lista de isencao de economia de energia (`dumpsys deviceidle whitelist`), garantindo sincronizacao em segundo plano com a tela apagada.
6. **Instalacao de Emuladores:** Baixa e instala as versoes oficiais ARM64 de RetroArch, PPSSPP, Dolphin e Flycast (e instala DuckStation e NetherSX2 caso os APKs estejam presentes na pasta `tools/android_apks/`).

---

## 5. Etapa 4: Configuracao do Syncthing (Windows 11 <---> Android)

O **Syncthing** garante a troca de saves e o envio de jogos na rede local Wi-Fi sem intermediarios em nuvem e sem risco de vazamento de dados.

### 5.1 Inicializacao dos Servicos
* **No Windows:** Abra o menu Iniciar, inicie o aplicativo **Syncthing** (ou abra no navegador o endereco `http://127.0.0.1:8384`).
* **No Android:** Abra o aplicativo **Syncthing** (ou *Syncthing-Fork*). Conceda todas as permissoes de armazenamento solicitadas.

### 5.2 Pareamento dos Dois Aparelhos
1. No painel web do Windows (`http://127.0.0.1:8384`), clique em **Acoes** $\rightarrow$ **Mostrar ID**.
2. No app do Android, va na aba **Dispositivos**, toque em **+** e escaneie o QR Code exibido na tela do PC (ou digite o ID manualmente).
3. No PC, surgira uma notificacao solicitando autorizacao do novo dispositivo. Clique em **Adicionar Dispositivo**.
4. Nas configuracoes avancadas do dispositivo pareado em ambas as pontas, garanta que a opcao **Descoberta Local (LAN)** esteja ativada.

### 5.3 Configuracao das 3 Pastas Compartilhadas

Configure exatamente as tres pastas abaixo para manter o isolamento e evitar perda de dados:

#### Pasta 1: `retrogames-saves` (A mais importante - Bidirecional)
* **Rotulo / ID da Pasta:** `retrogames-saves`
* **Caminho no Windows:** `<pasta_do_projeto>\data\saves` (ex.: `C:\retrogame-lab\data\saves`)
* **Caminho no Android:** `/storage/emulated/0/RetroGames/saves`
* **Tipo de Pasta no Windows:** **Envio e Recebimento (Send & Receive)**
* **Tipo de Pasta no Android:** **Envio e Recebimento (Send & Receive)**
* **Versionamento de Arquivo (Windows e Android):**
  * Selecione **Versionamento Simples de Arquivo (Simple File Versioning)**.
  * Mantenha **5 versoes**. (Garante que se algum save corromper, voce podera restaurar versoes anteriores na pasta `.stversions`).
* **Verificacao de Ignore:** Certifique-se de que a aba *Padroes de Exclusao* aponte para o arquivo `.stignore` contendo `*.state*`.

#### Pasta 2: `retrogames-bios` (Unidirecional PC -> Android)
* **Rotulo / ID da Pasta:** `retrogames-bios`
* **Caminho no Windows:** `<pasta_do_projeto>\data\bios` (ex.: `C:\retrogame-lab\data\bios`)
* **Caminho no Android:** `/storage/emulated/0/RetroGames/bios`
* **Tipo de Pasta no Windows:** **Apenas Envio (Send Only)**
* **Tipo de Pasta no Android:** **Apenas Recebimento (Receive Only)**
* **Versionamento:** Desativado.

#### Pasta 3: `retrogames-roms` (Unidirecional PC -> Android)
* **Rotulo / ID da Pasta:** `retrogames-roms`
* **Caminho no Windows:** `<pasta_do_projeto>\data\roms` (ex.: `C:\retrogame-lab\data\roms`)
* **Caminho no Android:** `/storage/emulated/0/RetroGames/roms`
* **Tipo de Pasta no Windows:** **Apenas Envio (Send Only)**
* **Tipo de Pasta no Android:** **Apenas Recebimento (Receive Only)**
* **Versionamento:** Desativado.

---

## 6. Etapa 5: Calibracao dos Emuladores no Android

Para que os emuladores leiam os mesmos arquivos sincronizados pelo Syncthing, configure os seguintes caminhos no dispositivo Android:

### 6.1 DuckStation (PlayStation 1)
1. Abra o DuckStation no Android.
2. Em **Configuracoes de Diretorio**:
   * Diretorio de BIOS: aponte para `/storage/emulated/0/RetroGames/bios/ps1/`.
   * Diretorio de Jogos: aponte para `/storage/emulated/0/RetroGames/roms/ps1/`.
3. Em **Cartoes de Memoria (Memory Cards)**:
   * Diretorio de Salvamento: `/storage/emulated/0/RetroGames/saves/ps1/`.
   * Tipo do Slot 1: **Cartao separado por titulo (Separate card per title)**. *(Obrigatorio para compatibilidade com o template do PC)*.

### 6.2 NetherSX2 / AetherSX2 (PlayStation 2)
1. Abra o NetherSX2.
2. Na inicializacao ou nas configuracoes:
   * BIOS: aponte para `/storage/emulated/0/RetroGames/bios/ps2/scph39001.bin`.
   * Diretorio de Jogos: adicione a pasta `/storage/emulated/0/RetroGames/roms/ps2/`.
3. Em **Memory Cards**:
   * Mapeie o diretorio para `/storage/emulated/0/RetroGames/saves/ps2/`.
   * Utilize **Cartao individual por jogo** ou **Memory Card em pasta**.

### 6.3 RetroArch (SNES / 2D)
1. Abra o RetroArch no Android.
2. Va em **Configuracoes** $\rightarrow$ **Diretorio**:
   * Gravacao / Salvar (*Savefile*): aponte para `/storage/emulated/0/RetroGames/saves/snes/`.
   * Estados Salvos (*Savestate*): mantenha na pasta padrao interna do RetroArch (nunca aponte para `saves/` compartilhada).
   * Sistema / BIOS: aponte para `/storage/emulated/0/RetroGames/bios/`.

### 6.4 PPSSPP (PlayStation Portable)
1. Abra o PPSSPP no Android.
2. Va em **Configuracoes** $\rightarrow$ **Sistema** $\rightarrow$ **Diretorio do Memory Stick**.
3. Selecione a pasta `/storage/emulated/0/RetroGames/saves/psp/`.
4. Os dados serao lidos e gravados automaticamente na subpasta `SAVEDATA/`.

### 6.5 Dolphin (GameCube / Wii)
1. Abra o Dolphin.
2. Adicione a pasta de jogos `/storage/emulated/0/RetroGames/roms/gc/`.
3. Em **Configuracoes** $\rightarrow$ **GameCube**, defina o diretorio do Slot A para `/storage/emulated/0/RetroGames/saves/gc/` (utilizando cartoes GCI ou pasta de regiao).

### 6.6 Flycast (Dreamcast)
1. Abra o Flycast.
2. Adicione a pasta de ROMs `/storage/emulated/0/RetroGames/roms/dc/`.
3. Configure o diretorio de dados e BIOS para apontar para `/storage/emulated/0/RetroGames/bios/dc/` e os saves de VMU para `/storage/emulated/0/RetroGames/saves/dc/`.

---

## 7. Etapa 6: Rotina de Operacao Cross-Save (Sem Perdas e Sem Conflitos)

Para alternar entre jogar no computador e no dispositivo movel de forma segura e transparente, siga sempre este protocolo:

1. **Salve sempre pelo menu do jogo:** Utilize os *save points* e opcoes nativas de gravacao de jogo ou cartao de memoria. **Nunca use savestates** para trocar de aparelho.
2. **Encerre o emulador no aparelho de origem:** Emuladores mantem arquivos abertos em buffers de memoria RAM enquanto estao em execucao. Apenas ao fechar a aplicacao os dados sao descarregados fisicamente para o arquivo de disco.
3. **Aguarde a sincronizacao na rede local:** Com ambos os aparelhos conectados ao mesmo Wi-Fi, o Syncthing detecta a alteracao no arquivo em aproximadamente 2 a 5 segundos.
4. **Abra o emulador no aparelho de destino:** Ao iniciar a sessao no outro aparelho, seu progresso estara perfeitamente atualizado.

---

## 8. Verificacao de Integridade e Resolucao de Problemas

### 8.1 Como Auditar o Estado do Ecossistema
A qualquer momento, voce pode rodar a auditoria integrada para checar se ha arquivos corrompidos, savestates indevidos ou nomes com espacos:

```powershell
# Execucao visual via orquestrador unificado
.\retrogame audit

# Ou diretamente pelo script ou CLI Python
pwsh -NoProfile -File scripts\audit_library.ps1
uv run retrogame-lab audit
```

Se todos os modulos apresentarem `[OK]`, o seu ambiente esta em conformidade total.

### 8.2 Guia de Solucao de Problemas Comuns

| Sintoma | Causa Provavel | Solucao Recomendada |
| :--- | :--- | :--- |
| **Arquivos `.sync-conflict` gerados na pasta de saves** | O jogo foi salvo em ambos os aparelhos quase simultaneamente ou o emulador permaneceu aberto em duas pontas. | Feche o emulador em ambos os aparelhos. Inspecione os dois arquivos gerados, mantenha o com a data/hora mais recente e apague o `.sync-conflict`. Sempre feche o emulador antes de trocar de dispositivo. |
| **O save nao atualiza no Android** | O Syncthing foi suspenso pelo sistema operacional Android (Doze Mode). | Reexecute `.\retrogame android` para reinserir o pacote na whitelist de bateria, ou acesse no Android: *Configuracoes -> Bateria -> Otimizacao de Bateria -> Syncthing -> Nao Otimizar*. |
| **Emulador no Android nao consegue gravar saves** | Falta da permissao `MANAGE_EXTERNAL_STORAGE` (Android 11+). | Reexecute o script de provisionamento ou conceda manualmente via ADB: `adb shell "appops set <pacote> MANAGE_EXTERNAL_STORAGE allow"`. |
| **O auditor reporta erro de savestate em `data/saves/`** | Savestates foram salvos na pasta de saves em vez de `data/states/`. | Mova os arquivos `*.state*` para `data/states/` e confirme que o arquivo `data/saves/.stignore` existe. |
| **Nomes de ROMs nao aparecem ou causam erro no launcher** | Nome do arquivo contem espacos ou aspas/caracteres especiais. | Execute `.\retrogame sanitize --apply` para renomear automaticamente. |
