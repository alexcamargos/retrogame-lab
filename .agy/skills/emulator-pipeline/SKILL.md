---
name: emulator-pipeline
description: Pipeline de orquestração de emulação portátil, auditoria de integridade de ROMs/BIOS e provisionamento Android no RetroGame Lab.
---

# Skill: Emulator Pipeline

Esta skill capacita agentes a executar, diagnosticar, auditar e provisionar o ecossistema portátil de emulação do **RetroGame Lab** em Windows 11 e Android ARM64.

---

## 1. Comandos Operacionais

### 1.1 Lançamento de Emulador com Perfilamento Dinâmico
Para lançar uma ROM de qualquer plataforma suportada com perfilamento de hardware automático:

```powershell
pwsh -NoProfile -File scripts/launch.ps1 -Platform <snes|ps1|ps2|psp|gc|dc> -RomPath <caminho_da_rom> [-Fullscreen] [-GpuMode auto|igpu|dgpu]
```

* **Comportamento Automático:**
  * Detecta automaticamente GPUs dedicadas (NVIDIA/Radeon/Arc) e injeta preferência de alto desempenho no registro do DirectX.
  * Em CPUs híbridas (Intel 12ª Gen+, Core Ultra), vincula processos com alta demanda de IPC (PCSX2, Dolphin) aos **P-cores (0 a 7)**.
  * Executa o processo com isolamento estrito do diretório de trabalho (*Push-Location / Pop-Location*).

---

### 1.2 Auditoria de Integridade da Biblioteca
Para escanear BIOS, formatos de ROMs e integridade de saves:

```powershell
# Relatório formatado no terminal
pwsh -NoProfile -File scripts/audit_library.ps1

# Saída estruturada em JSON (ideal para agentes e automações)
pwsh -NoProfile -File scripts/audit_library.ps1 -Json
```

* **Itens Verificados:**
  * **BIOS:** Existência de firmwares oficiais e correspondência exata de hashes SHA-256.
  * **ROMs:** Detecção de mídias de CD não convertidas para `.chd` e proibição mandatória de `.chd` no GameCube (exige `.rvz`).
  * **Saves:** Detecção e bloqueio de savestates (`*.state*`) e memory cards compartilhados globais na pasta de sincronização.

---

### 1.3 Conversão Determinística de Mídias para CHD
Para comprimir discos de PS1, PS2 e Dreamcast sem perdas:

```powershell
pwsh -NoProfile -File scripts/convert_chd.ps1 -SourceDirectory <caminho_pasta> [-MediaType auto|cd|dvd]
```

* **Diferenciação Canônica:**
  * Discos baseados em CD: comando `createcd` (setor bruto de 2352 bytes).
  * Discos baseados em DVD de PS2: comando `createdvd` (setor limpo de 2048 bytes).
  * Ignora automaticamente GameCube/Wii (que utilizam `.rvz` nativo).

---

### 1.4 Provisionamento Android via ADB
Para preparar um dispositivo móvel conectado via USB:

```powershell
pwsh -NoProfile -File scripts/setup_android_emulators.ps1 [-DeviceId <id>] [-SkipDownload]
```

* **Ações Executadas:**
  * Valida conexão ADB e verifica compatibilidade ARM64 (`ro.product.cpu.abi`).
  * Cria estrutura em `/storage/emulated/0/RetroGames/` (`bios/`, `roms/`, `saves/`).
  * Injeta o arquivo `.stignore` no dispositivo móvel para proteção anti-conflito.
  * Concede permissão de Scoped Storage `MANAGE_EXTERNAL_STORAGE` para os emuladores.
  * Configura whitelist de economia de bateria contra o Doze Mode no Syncthing.

---

### 1.5 Bootstrap Inicial do Host Windows
Para provisionar pastas e ferramentas no Windows 11:

```powershell
# Sem tocar no winget (apenas pastas e templates)
pwsh -NoProfile -File scripts/bootstrap.ps1 -SkipWinget

# Instalação completa com ferramentas oficiais via winget
pwsh -NoProfile -File scripts/bootstrap.ps1
```

---

## 2. Protocolo de Proteção e Segurança de Saves

1. **Nunca sincronizar Savestates:**
   * Arquivos com padrão `*.state*`, `*.s01`, `*.nvram.bak` dependem de arquitetura (x86_64 vs ARM64) e causam corrupção de memória.
   * Certifique-se de que `data/saves/.stignore` esteja sempre presente e ativo.
2. **Title-specific Memory Card Mandatório:**
   * Nunca criar ou orientar o uso de cartões compartilhados globais em PS1/PS2.
   * Utilizar exclusivamente `<Title>_<ID>.mcd` para PS1 e `<Title>_<ID>.ps2` para PS2.
3. **Flush de Disco Antes de Alternar Aparelhos:**
   * Oriente o encerramento completo do emulador antes de trocar de dispositivo para garantir a gravação dos dados do buffer de RAM para o disco.
