# Especificação Técnica: Sincronização e Pareamento Multiplataforma (Windows 11 $\leftrightarrow$ Android) via Syncthing e ADB

Esta especificação define o pipeline contínuo de sincronização de dados (saves, BIOS, ROMs) e o provisionamento de emuladores compatíveis entre uma estação de trabalho **Windows 11** e qualquer dispositivo **Android ARM64** (Smartphones, Tablets ou Consoles Portáteis dedicados como Ayn Odin, Retroid Pocket, Anbernic, etc.).

> [!NOTE]
> **Perfil de Referência Homologado:**  
> Um smartphone com chipset Qualcomm Snapdragon 8 Gen 5 (arquitetura ARM64) foi utilizado como **baseline empírico de validação móvel**, confirmando a execução com folga de emuladores de 6ª geração (PS2/GameCube) e a compatibilidade do Android Scoped Storage. A arquitetura aqui descrita é, no entanto, agnóstica e compatível com qualquer dispositivo Android 10+ ARM64.

---

## 1. Topologia de Sincronização no Syncthing

Para evitar conflitos de gravação, perda de progresso e preservar a banda de rede local, o ecossistema divide as pastas compartilhadas em três categorias operacionais de acordo com a mutabilidade dos dados:

```
+---------------------------------------------------------------------------------------------------------+
|                                           TOPOLOGIA SYNCTHING                                           |
|                                                                                                         |
|   Windows 11 (Host Portátil)                                  Dispositivo Android (Qualquer ARM64)      |
|                                                                                                         |
|   [data\saves\]   <============== (Bidirecional / Send-Receive) =============> [/RetroGames/saves/]    |
|   - Saves por jogo (.srm, .mcd, .ps2, .gci, .bin)                                                       |
|                                                                                                         |
|   [data\bios\]    ---------------- (Unidirecional / Send-Only) --------------> [/RetroGames/bios/]     |
|   - Imagens de firmware oficiais                                                                        |
|                                                                                                         |
|   [data\roms\]    ---------------- (Unidirecional / Send-Only) --------------> [/RetroGames/roms/]     |
|   - Imagens comprimidas (.chd, .cso, .rvz)                                                              |
+---------------------------------------------------------------------------------------------------------+
```

### 1.1 Políticas das Pastas Compartilhadas

| Pasta ID | Caminho Windows | Caminho Android | Tipo de Sincronia | Política de Versionamento |
| :--- | :--- | :--- | :--- | :--- |
| `retrogames-saves` | `data\saves\` | `/storage/emulated/0/RetroGames/saves/` | **Send & Receive (Bidirecional)** | **Simple File Versioning** (Manter 5 versões para mitigar corrupção de save) |
| `retrogames-bios` | `data\bios\` | `/storage/emulated/0/RetroGames/bios/` | **Send Only** (PC) $\rightarrow$ **Receive Only** (Android) | Sem versionamento (estático) |
| `retrogames-roms` | `data\roms\` | `/storage/emulated/0/RetroGames/roms/` | **Send Only** (PC) $\rightarrow$ **Receive Only** (Android) | Sem versionamento (estático) |

---

## 2. Regras de Exclusão de Arquivos (`.stignore`)

> [!WARNING]
> **Savestates vs. Saves de Bateria / Memory Card:**  
> Savestates (`.state`, `.s01`, etc.) dependem do estado interno de registradores e versão exata do compilador na arquitetura (x86_64 vs. ARM64). Sincronizá-los entre PC e Android causa travamentos e falhas de memória. Apenas saves in-game (SRAM / Memory Card) devem ser sincronizados.

O arquivo de ignore deve ser posicionado em `data\saves\.stignore` no Windows e espelhado no Android:

```text
// .stignore para retrogames-saves

// 1. Proibir Savestates (Incompatibilidade binária x86_64 vs ARM64)
*.state*
*.s[0-9][0-9]
*.nvram.bak

// 2. Proibir Arquivos de Lock e Temporários Ativos
*.tmp*
*.lock*
*.lck
*.wal
*.shm

// 3. Metadados do Sistema Operacional e do Syncthing
(?d).DS_Store
(?d)thumbs.db
(?d)desktop.ini
(?d).syncthing.*
```

---

## 3. Matriz de Compatibilidade e Formatos de Cartão de Memória

Para evitar perdas por concorrência (quando dois aparelhos alteram o mesmo arquivo simultaneamente gerando `.sync-conflict`), adota-se o padrão **Cartão por Título / Jogo Individual**:

| Plataforma | App Windows | App Android | Formato Unificado do Save | Diretório de Destino (Relativo a `saves/`) |
| :--- | :--- | :--- | :--- | :--- |
| **SNES** | RetroArch (`snes9x`) | RetroArch (`snes9x`) | `.srm` individual por ROM | `snes/` |
| **PS1** | DuckStation (Qt) | DuckStation Android | **Title-specific Card** (`<Title>_<ID>.mcd`) | `ps1/` |
| **PS2** | PCSX2 (Qt v2.0+) | NetherSX2 (ARM64) | **Title-specific Card** (`<Title>_<ID>.ps2`) | `ps2/` |
| **PSP** | PPSSPP Windows | PPSSPP Android | Pastas `SAVEDATA` nativas | `psp/SAVEDATA/` |
| **GameCube** | Dolphin | Dolphin Android | Pastas de Região (USA, EUR, JAP) e GCI individuais | `gc/` |
| **Dreamcast** | Flycast | Flycast Android | Arquivo VMU padrão (`vms0.bin`) | `dc/` |

> [!IMPORTANT]
> **Padronização de Nomenclatura Sem Espaços:**  
> O Android Scoped Storage e o Syncthing têm alta sensibilidade a arquivos com espaços, aspas ou caracteres especiais (`'"~^!?\:;*<>|#`), especialmente ao operar sobre cartões microSD formatados em FAT32 ou exFAT. O pipeline de ingestão (`uv run retrogame-lab import-rom`) e o lançador (`scripts/launch.ps1`) garantem que todos os arquivos sejam previamente higienizados no PC antes do envio unidirecional para o dispositivo móvel.

---

## 4. Script de Provisionamento de Emuladores para Android (`setup_android_emulators.ps1`)

Este script em PowerShell utiliza o **Android Debug Bridge (ADB)** para:

1. Validar a conexão ADB, selecionando automaticamente o dispositivo alvo mesmo com múltiplos aparelhos conectados.
2. Criar a estrutura hierárquica completa em `/storage/emulated/0/RetroGames/`.
3. Conceder permissão especial **`MANAGE_EXTERNAL_STORAGE`** (Scoped Storage do Android 11+).
4. Configurar whitelist de economia de bateria para o Syncthing (`dumpsys deviceidle`).
5. Baixar e instalar automaticamente os APKs ARM64 compatíveis (com fallback para cache offline).
6. Injetar o arquivo `.stignore` no diretório de saves do Android.

Salvo em `scripts/setup_android_emulators.ps1`:

```powershell
[CmdletBinding()]
param (
    [string]$DeviceId = "",
    [string]$TargetDevicePath = "/storage/emulated/0/RetroGames",
    [switch]$SkipDownload = $false
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $BaseDir "tools"
$ApkCacheDir = Join-Path $BaseDir "tools\android_apks"

if (-not (Test-Path $ApkCacheDir)) {
    New-Item -ItemType Directory -Path $ApkCacheDir -Force | Out-Null
}

Write-Host ">>> Identificando conexões via ADB..." -ForegroundColor Cyan

# 1. Resolução Segura de Dispositivo (Suporte a Multi-Device)
try {
    $DeviceLines = (adb devices | Out-String) -split "`r?`n" | Where-Object { $_ -match "\bdevice\b" -and $_ -notmatch "List of devices" }
} catch {
    Write-Error "O utilitário adb não foi encontrado no PATH. Execute scripts/bootstrap.ps1 para instalar o Google.PlatformTools."
}

if (-not $DeviceLines) {
    Write-Error "Nenhum dispositivo Android autorizado foi detectado. Ative a Depuração USB e autorize o computador."
}

if (-not $DeviceId) {
    $DeviceId = ($DeviceLines[0] -split "\s+")[0]
    Write-Host ">>> Dispositivo selecionado automaticamente: $DeviceId" -ForegroundColor Yellow
}

$AdbArgs = @("-s", $DeviceId)

# Identificação Dinâmica da Arquitetura
& adb @AdbArgs start-server 2>$null | Out-Null
$DeviceModelRaw = (& adb @AdbArgs shell "getprop ro.product.model") | Out-String
$DeviceAbiRaw   = (& adb @AdbArgs shell "getprop ro.product.cpu.abi") | Out-String

$DeviceModel = ($DeviceModelRaw.Trim() -split "`r?`n")[-1].Trim()
$DeviceAbi   = ($DeviceAbiRaw.Trim() -split "`r?`n")[-1].Trim()
Write-Host ">>> Dispositivo Alvo: $DeviceModel (ABI: $DeviceAbi)" -ForegroundColor Green

if ($DeviceAbi -notmatch "arm64") {
    Write-Warning "O dispositivo conectado não reporta ABI arm64-v8a ($DeviceAbi). Alguns APKs podem falhar."
}

# 2. Estruturação Completa de Pastas no Android
Write-Host ">>> Criando estrutura hierárquica no armazenamento interno..." -ForegroundColor Cyan
$Directories = @(
    "$TargetDevicePath/bios/ps1",
    "$TargetDevicePath/bios/ps2",
    "$TargetDevicePath/bios/dc",
    "$TargetDevicePath/roms/snes",
    "$TargetDevicePath/roms/ps1",
    "$TargetDevicePath/roms/ps2",
    "$TargetDevicePath/roms/psp",
    "$TargetDevicePath/roms/gc",
    "$TargetDevicePath/roms/dc",
    "$TargetDevicePath/saves/snes",
    "$TargetDevicePath/saves/ps1",
    "$TargetDevicePath/saves/ps2",
    "$TargetDevicePath/saves/psp",
    "$TargetDevicePath/saves/gc",
    "$TargetDevicePath/saves/dc"
)

foreach ($Dir in $Directories) {
    & adb @AdbArgs shell "mkdir -p `"$Dir`""
}

# 3. Injeção de Regras .stignore no Android
$StIgnoreContent = @"
// .stignore para retrogames-saves
*.state*
*.s[0-9][0-9]
*.nvram.bak
*.tmp*
*.lock*
*.lck
*.wal
*.shm
(?d).DS_Store
(?d)thumbs.db
(?d)desktop.ini
(?d).syncthing.*
"@
$TempStIgnore = [System.IO.Path]::GetTempFileName()
Set-Content -Path $TempStIgnore -Value $StIgnoreContent -Encoding UTF8
& adb @AdbArgs push $TempStIgnore "$TargetDevicePath/saves/.stignore" | Out-Null
Remove-Item -Path $TempStIgnore -Force

# 4. Definição do Catálogo de Emuladores ARM64
$Emulators = @(
    @{
        Name    = "RetroArch (Universal)"
        Package = "com.retroarch.aarch64"
        Url     = "https://buildbot.libretro.com/nightly/android/RetroArch_aarch64.apk"
        File    = Join-Path $ApkCacheDir "RetroArch_aarch64.apk"
    },
    @{
        Name    = "DuckStation (PS1)"
        Package = "com.github.stenzek.duckstation"
        Url     = "" # DuckStation Android é mantido preferencialmente em cache local
        File    = Join-Path $ApkCacheDir "duckstation-android.apk"
    },
    @{
        Name    = "PPSSPP (PSP)"
        Package = "org.ppsspp.ppsspp"
        Url     = "https://www.ppsspp.org/files/1_18_1/ppsspp.apk"
        File    = Join-Path $ApkCacheDir "ppsspp.apk"
    },
    @{
        Name    = "Dolphin (GameCube/Wii)"
        Package = "org.dolphinemu.dolphinemu"
        Url     = "https://dolphin-emu.org/download/get/latest/dolphin-master.apk"
        File    = Join-Path $ApkCacheDir "dolphin-android.apk"
    },
    @{
        Name    = "Flycast (Dreamcast)"
        Package = "com.flyinghead.flycast"
        Url     = "https://github.com/flyinghead/flycast/releases/download/v2.4/flycast-release.apk"
        File    = Join-Path $ApkCacheDir "flycast-android.apk"
    }
)

# 5. Download e Instalação dos APKs
foreach ($Emu in $Emulators) {
    Write-Host "`n--- Processando: $($Emu.Name) ---" -ForegroundColor Yellow

    if (-not $SkipDownload -and $Emu.Url) {
        if (-not (Test-Path $Emu.File) -or (Get-Item $Emu.File).Length -lt 1024) {
            Write-Host "Baixando pacote atualizado ($($Emu.Url))..." -ForegroundColor Gray
            try {
                Invoke-WebRequest -Uri $Emu.Url -OutFile $Emu.File -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
            } catch {
                if (Test-Path $Emu.File) { Remove-Item $Emu.File -Force }
                Write-Warning "Falha no download online de $($Emu.Name). Verifique a URL ou forneça o APK em tools\android_apks\"
            }
        }
    }

    if ((Test-Path $Emu.File) -and (Get-Item $Emu.File).Length -ge 1024) {
        Write-Host "Instalando/Atualizando APK no dispositivo Android..." -ForegroundColor Green
        & adb @AdbArgs install -r -d -g $Emu.File

        # Concessão mandatória de MANAGE_EXTERNAL_STORAGE (Android 11+)
        Write-Host "Concedendo permissão MANAGE_EXTERNAL_STORAGE..." -ForegroundColor Gray
        & adb @AdbArgs shell "appops set $($Emu.Package) MANAGE_EXTERNAL_STORAGE allow" 2>$null
    } else {
        Write-Warning "APK válido para $($Emu.Name) não encontrado em $($Emu.File). Etapa ignorada."
    }
}

# 6. Tratamento Especial para o NetherSX2 (PS2)
$NetherApk = Join-Path $ApkCacheDir "NetherSX2.apk"
if (Test-Path $NetherApk) {
    Write-Host "`n--- Instalando NetherSX2 (PS2) do cache local ---" -ForegroundColor Yellow
    & adb @AdbArgs install -r -d -g $NetherApk
    & adb @AdbArgs shell "appops set xyz.aethersx2.android MANAGE_EXTERNAL_STORAGE allow" 2>$null
} else {
    Write-Host "`n[AVISO] NetherSX2.apk não encontrado em tools\android_apks\. Copie o APK patcheado para concluir a instalação do PS2." -ForegroundColor Magenta
}

# 7. Otimização do Syncthing contra Doze Mode (Economia de Bateria)
Write-Host "`n>>> Inserindo Syncthing na whitelist de economia de bateria..." -ForegroundColor Cyan
$SyncthingPackages = @(
    "com.nutomic.syncthingandroid",
    "com.github.catfriend1.syncthingandroid",
    "com.nutomic.syncthingcb"
)
foreach ($Pkg in $SyncthingPackages) {
    & adb @AdbArgs shell "dumpsys deviceidle whitelist +$Pkg" 2>$null
}

Write-Host "`n=== Provisionamento Android Concluído com Sucesso! ===" -ForegroundColor Green
```

---

## 5. Procedimento de Configuração Operacional

> [!TIP]
> Para um passo a passo detalhado voltado a novos usuários, consulte o [Guia de Início e Integração Multiplataforma](guia-inicio.md).

1. **Inicialização do Syncthing:**
   * **No Windows:** Instale via Winget (`winget install Syncthing.Syncthing`) e inicie o serviço. Acesse `http://127.0.0.1:8384`.
   * **No Android:** Instale o app do Syncthing via F-Droid ou Play Store. Conceda permissão de *Acesso a todos os arquivos*.
2. **Pareamento de Dispositivos:**
   * Adicione o ID do dispositivo de cada ponta no painel do outro.
   * Ative a opção **Local Discovery (LAN)** para garantir que as transferências ocorram em rede local de alta velocidade sem passar por relays de internet.
3. **Mapeamento de Pastas:**
   * `retrogames-saves`: Mapeia `data\saves\` (Windows) $\leftrightarrow$ `/storage/emulated/0/RetroGames/saves/` (Android) no modo **Send & Receive**.
   * `retrogames-bios`: Mapeia `data\bios\` $\rightarrow$ `/storage/emulated/0/RetroGames/bios/` no modo **Send Only** no PC.
   * `retrogames-roms`: Mapeia `data\roms\` $\rightarrow$ `/storage/emulated/0/RetroGames/roms/` no modo **Send Only** no PC.
4. **Provisionamento Automatizado via ADB:**
   * Conecte o dispositivo Android via cabo USB com Depuração USB ativada.
   * Execute:
     ```powershell
     pwsh -File .\scripts\setup_android_emulators.ps1
     ```
5. **Configuração dos Emuladores no Android:**
   * **DuckStation:** Mapear pasta de Memory Cards para `RetroGames/saves/ps1/` e marcar modo "Separate card per title".
   * **NetherSX2:** Mapear Memory Cards para `RetroGames/saves/ps2/`.
   * **PPSSPP:** Mapear o diretório de Memory Stick para `RetroGames/saves/psp/`.
   * **Dolphin:** Mapear pasta de saves de GameCube para `RetroGames/saves/gc/`.
   * **Flycast:** Mapear pasta de VMU para `RetroGames/saves/dc/`.

---

## 6. Rotina de Cross-Save Segura

1. **Sempre salve pelo menu in-game:** Use save points ou memory card do jogo; nunca confie em savestate para troca de aparelhos.
2. **Feche o aplicativo antes de trocar:** Os emuladores gravam em cache de memória e só descarregam as alterações no arquivo físico no momento do encerramento da sessão.
3. **Aguarde a sincronização (2 a 5 segundos):** Na mesma rede Wi-Fi local, o Syncthing sincroniza o delta do arquivo de save quase instantaneamente antes de você abrir o jogo na outra ponta.
4. **Preserve a nomenclatura higienizada:** Arquivos sem espaços garantem que os parsers dos emuladores Android (baseados em Linux/POSIX) e o sistema de arquivos FAT32/exFAT não gerem erros de I/O ou arquivos temporários não sincronizáveis.
