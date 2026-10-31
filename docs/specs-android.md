# Especificação Técnica: Sincronização e Pareamento Multiplataforma (Windows 11 $\leftrightarrow$ Android) via Syncthing e ADB

Esta especificação define o pipeline contínuo de sincronização de dados (saves, BIOS, ROMs) e o provisionamento de emuladores compatíveis entre a estação de trabalho **Windows 11** (RTX 4050 / Core i5-12th) e o **Motorola Signature** (Snapdragon 8 Gen 5 / Android).

---

## 1. Topologia de Sincronização no Syncthing

Para evitar conflitos de gravação, perda de progresso e preservar a banda de rede local, o ecossistema divide as pastas compartilhadas em três categorias operacionais de acordo com a mutabilidade dos dados:

```
+---------------------------------------------------------------------------------------------------------+
|                                           TOPOLOGIA SYNCTHING                                           |
|                                                                                                         |
|   Windows 11 (Host Portátil)                                  Android (Motorola Signature)              |
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
(?d).DS_Store
(?d)thumbs.db
(?d)desktop.ini
*.state*
*.nvram.bak
*.tmp
// Ignorar arquivos temporários do Syncthing
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
| **GameCube** | Dolphin | Dolphin Android | Cartões GCI individuais por jogo | `gc/USA/Card A/` |
| **Dreamcast** | Flycast | Flycast Android | Arquivo VMU (`vmu_save_A1.bin`) | `dc/` |

---

## 4. Script de Provisionamento de Emuladores para Android (`setup_android_emulators.ps1`)

Este script em PowerShell utiliza o **Android Debug Bridge (ADB)** para:

1. Validar a conexão com o Motorola Signature via USB ou Wi-Fi Debugging.
2. Criar a estrutura hierárquica em `/storage/emulated/0/RetroGames/` (incluindo Dreamcast).
3. Conceder permissão especial **`MANAGE_EXTERNAL_STORAGE`** (Scoped Storage do Android 11+).
4. Configurar whitelist de economia de bateria para o Syncthing (`dumpsys deviceidle`).
5. Baixar e instalar automaticamente os APKs ARM64 compatíveis (RetroArch, DuckStation, NetherSX2, PPSSPP, Dolphin, Flycast).
6. Injetar o arquivo `.stignore` no diretório de saves do Android.

Salvo em `scripts/setup_android_emulators.ps1`:

```powershell
[CmdletBinding()]
param (
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

Write-Host ">>> Verificando conexão com o dispositivo via ADB..." -ForegroundColor Cyan
$Devices = adb devices | Out-String
if ($Devices -notmatch "\bdevice\b") {
    Write-Error "Nenhum dispositivo Android autorizado foi detectado. Ative a Depuração USB e autorize o PC."
}

# 1. Estruturação Completa de Pastas no Android
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
    adb shell "mkdir -p `"$Dir`""
}

# 2. Injeta regra .stignore diretamente no Android
$StIgnoreContent = @"
(?d).DS_Store
(?d)thumbs.db
(?d)desktop.ini
*.state*
*.nvram.bak
*.tmp
(?d).syncthing.*
"@
$TempStIgnore = [System.IO.Path]::GetTempFileName()
Set-Content -Path $TempStIgnore -Value $StIgnoreContent -Encoding UTF8
adb push $TempStIgnore "$TargetDevicePath/saves/.stignore" | Out-Null
Remove-Item -Path $TempStIgnore -Force

# 3. Definição do Catálogo de Emuladores ARM64 Homologados
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
        Url     = "https://github.com/stenzek/duckstation/releases/download/latest/duckstation-android.apk"
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

# 4. Download e Instalação dos APKs
foreach ($Emu in $Emulators) {
    Write-Host "`n--- Processando: $($Emu.Name) ---" -ForegroundColor Yellow

    if (-not $SkipDownload) {
        if (-not (Test-Path $Emu.File)) {
            Write-Host "Baixando pacote atualizado ($($Emu.Url))..." -ForegroundColor Gray
            Invoke-WebRequest -Uri $Emu.Url -OutFile $Emu.File -MaximumRedirection 10 -UserAgent "Mozilla/5.0"
        }
    }

    if (Test-Path $Emu.File) {
        Write-Host "Instalando/Atualizando APK no Motorola..." -ForegroundColor Green
        adb install -r -d -g $Emu.File

        # Concede permissão irrestrita de armazenamento (Scoped Storage Android 11+)
        Write-Host "Concedendo permissão MANAGE_EXTERNAL_STORAGE..." -ForegroundColor Gray
        adb shell "appops set $($Emu.Package) MANAGE_EXTERNAL_STORAGE allow" 2>$null
    }
}

# 5. Tratamento Especial para o NetherSX2 (PS2)
$NetherApk = Join-Path $ApkCacheDir "NetherSX2.apk"
if (Test-Path $NetherApk) {
    Write-Host "`n--- Instalando NetherSX2 (PS2) do cache local ---" -ForegroundColor Yellow
    adb install -r -d -g $NetherApk
    adb shell "appops set xyz.aethersx2.android MANAGE_EXTERNAL_STORAGE allow" 2>$null
} else {
    Write-Host "`n[AVISO] NetherSX2.apk não encontrado em tools\android_apks\. Copie o APK patcheado para concluir a instalação do emulador de PS2." -ForegroundColor Magenta
}

# 6. Otimização do Syncthing contra Doze Mode (Economia de Bateria)
Write-Host "`n>>> Inserindo Syncthing na whitelist de economia de bateria..." -ForegroundColor Cyan
adb shell "dumpsys deviceidle whitelist +com.nutomic.syncthingcb" 2>$null

Write-Host "`n=== Provisionamento Android Concluído com Sucesso! ===" -ForegroundColor Green
```

---

## 5. Procedimento de Configuração Operacional

1. **Inicialização do Syncthing:**
   * **No Windows:** Instale via Winget (`winget install Syncthing.Syncthing`) e inicie o serviço. Acesse `http://127.0.0.1:8384`.
   * **No Android:** Instale o app do Syncthing via F-Droid ou Play Store. Conceda permissão de *Acesso a todos os arquivos*.
2. **Pareamento de Dispositivos:**
   * Adicione o ID do dispositivo de cada ponta no painel do outro.
   * Ative a opção **Local Discovery (LAN)** para garantir que as transferências ocorram via Wi-Fi 6 de alta velocidade sem passar por relays de internet.
3. **Mapeamento de Pastas:**
   * `retrogames-saves`: Mapeia `data\saves\` (Windows) $\leftrightarrow$ `/storage/emulated/0/RetroGames/saves/` (Android) no modo **Send & Receive**.
   * `retrogames-bios`: Mapeia `data\bios\` $\rightarrow$ `/storage/emulated/0/RetroGames/bios/` no modo **Send Only** no PC.
   * `retrogames-roms`: Mapeia `data\roms\` $\rightarrow$ `/storage/emulated/0/RetroGames/roms/` no modo **Send Only** no PC.
4. **Provisionamento Automatizado via ADB:**
   * Conecte o Motorola Signature via cabo USB com Depuração USB ativada.
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
