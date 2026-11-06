"""Módulo de validação e provisionamento do Syncthing para Windows e Android.

Fornece auditoria das regras de sincronização, detecção de colisões de salvamento,
validação de diretórios, permissões Scoped Storage / Doze mode via ADB, e geração
automática de configurações para o cliente desktop e Syncthing-Fork no Android.
"""

import contextlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from retrogame_lab.config import find_repo_root, get_bios_dir, get_roms_dir, get_saves_dir

# Pacotes do Syncthing para Android (prioridade para Syncthing-Fork mantido)
SYNCTHING_ANDROID_PACKAGES: list[str] = [
    "com.github.catfriend1.syncthingandroid",
    "com.nutomic.syncthingandroid",
    "com.nutomic.syncthingcb",
]

# Regras canônicas para o .stignore de salvamentos
STIGNORE_SAVE_RULES: list[str] = [
    "// .stignore para retrogames-saves",
    "",
    "// 1. Proibir Savestates (Incompatibilidade binaria x86_64 vs ARM64)",
    "*.state*",
    "*.s[0-9][0-9]",
    "*.nvram.bak",
    "",
    "// 2. Proibir Arquivos de Lock e Temporarios Ativos",
    "*.tmp*",
    "*.lock*",
    "*.lck",
    "*.wal",
    "*.shm",
    "",
    "// 3. Metadados do Sistema Operacional e do Syncthing",
    "(?d).DS_Store",
    "(?d)thumbs.db",
    "(?d)desktop.ini",
    "(?d).syncthing.*",
    "",
    "// 4. Plataformas Exclusivas de Desktop (Windows-only - isolamento mobile)",
    "ps3/",
    "xbox360/",
    "switch/",
]

# Padrões obrigatórios que devem estar presentes no .stignore
MANDATORY_IGNORE_PATTERNS: list[str] = [
    "*.state*",
    "*.s[0-9][0-9]",
    "*.nvram.bak",
    "*.tmp*",
    "*.lock*",
    "*.lck",
    "*.wal",
    "*.shm",
    "(?d).syncthing.*",
    "ps3/",
    "xbox360/",
    "switch/",
]

# Definição canônica das pastas gerenciadas pelo ecossistema
SYNCTHING_MANAGED_FOLDERS: dict[str, dict[str, Any]] = {
    "saves": {
        "default_id": "retrogames-saves",
        "label": "retrogames-saves",
        "rel_path": "data/saves",
        "android_path": "/storage/emulated/0/RetroGames/saves",
        "type": "sendreceive",
        "fs_watcher": True,
        "watcher_delay_s": 10,
        "rescan_interval_s": 3600,
        "has_stignore": True,
        "versioning": {
            "type": "simple",
            "params": {"cleanoutDays": "0", "keep": "5"},
        },
    },
    "roms": {
        "default_id": "retrogames-roms",
        "label": "retrogames-roms",
        "rel_path": "data/roms",
        "android_path": "/storage/emulated/0/RetroGames/roms",
        "type": "sendreceive",
        "fs_watcher": True,
        "watcher_delay_s": 10,
        "rescan_interval_s": 3600,
        "has_stignore": False,
        "versioning": None,
    },
    "bios": {
        "default_id": "retrogames-bios",
        "label": "retrogames-bios",
        "rel_path": "data/bios",
        "android_path": "/storage/emulated/0/RetroGames/bios",
        "type": "sendreceive",
        "fs_watcher": True,
        "watcher_delay_s": 10,
        "rescan_interval_s": 3600,
        "has_stignore": False,
        "versioning": None,
    },
}


class ValidationStatus(str, Enum):
    """Níveis de severidade para checagens de validação."""

    OK = "OK"
    WARNING = "AVISO"
    ERROR = "ERRO"


@dataclass
class ValidationItem:
    """Item individual de validação do subsistema Syncthing.

    Attributes:
        target: Plataforma do item ('Windows', 'Android', 'Rede').
        category: Categoria técnica (ex.: 'Binário', 'Processo', 'Configuração').
        status: Status de conformidade do item.
        message: Descrição sumária do diagnóstico.
        details: Detalhes complementares ou orientações de remediação.
    """

    target: str
    category: str
    status: ValidationStatus
    message: str
    details: str = ""


@dataclass
class SyncthingFolderConfig:
    """Configuração de uma pasta compartilhada no Syncthing.

    Attributes:
        id: Identificador único da pasta no cluster de sincronização.
        label: Rótulo amigável da pasta.
        path: Caminho no sistema de arquivos local.
        folder_type: Tipo de sincronização ('sendreceive', 'sendonly', 'receiveonly').
        watcher_enabled: Se o monitorador inotify/file-watcher está ativo.
        watcher_delay_s: Tempo de espera em segundos para o gatilho inotify.
        versioning_type: Tipo de versionamento ('simple', 'staggered', ou None).
        devices: Lista de identificadores de dispositivos compartilhados.
    """

    id: str
    label: str
    path: str
    folder_type: str = "sendreceive"
    watcher_enabled: bool = True
    watcher_delay_s: int = 10
    versioning_type: str | None = None
    devices: list[str] = field(default_factory=list)


@dataclass
class SyncthingDeviceInfo:
    """Informações sobre um dispositivo registrado no Syncthing.

    Attributes:
        id: Identificador público do dispositivo (hash de 50-64 caracteres).
        name: Nome legível do dispositivo.
        introducer: Se o dispositivo atua como introdutor de outros nós.
        auto_accept_folders: Se pastas oferecidas são aceitas automaticamente.
    """

    id: str
    name: str
    introducer: bool = False
    auto_accept_folders: bool = False


@dataclass
class SyncthingValidationReport:
    """Relatório consolidado de auditoria do Syncthing.

    Attributes:
        items: Lista de itens verificados.
        windows_config_path: Caminho do arquivo config.xml no host Windows.
        windows_running: Se o processo syncthing.exe está ativo.
        windows_device_id: ID do dispositivo do computador Windows.
        windows_folders: Lista de pastas configuradas no Windows.
        windows_devices: Lista de dispositivos pareados no Windows.
        android_connected: Se há dispositivo Android acessível via ADB.
        android_device_id: ID do dispositivo Android detectado via ADB.
        android_package: Pacote do Syncthing instalado no Android.
        android_model: Modelo do smartphone Android.
        has_errors: Se foram identificados erros bloqueantes.
    """

    items: list[ValidationItem] = field(default_factory=list)
    windows_config_path: Path | None = None
    windows_running: bool = False
    windows_device_id: str | None = None
    windows_folders: list[SyncthingFolderConfig] = field(default_factory=list)
    windows_devices: list[SyncthingDeviceInfo] = field(default_factory=list)
    android_connected: bool = False
    android_device_id: str | None = None
    android_package: str | None = None
    android_model: str | None = None

    @property
    def has_errors(self) -> bool:
        """Indica se há algum item com severidade de ERRO."""
        return any(item.status == ValidationStatus.ERROR for item in self.items)

    @property
    def has_warnings(self) -> bool:
        """Indica se há algum item com severidade de AVISO."""
        return any(item.status == ValidationStatus.WARNING for item in self.items)


# ==============================================================================
# Métodos de Validação no Windows
# ==============================================================================


def find_windows_syncthing_binary() -> Path | None:
    """Localiza o binário syncthing.exe no PATH ou nos diretórios padrão do Windows.

    Args:
        None.

    Returns:
        Path absoluto para o executável syncthing.exe ou None se não encontrado.

    Raises:
        None.
    """
    which_path = shutil.which("syncthing")
    if which_path:
        return Path(which_path).resolve()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        winget_link = (
            Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "syncthing.exe"
        )
        if winget_link.is_file():
            return winget_link

    return None


def is_windows_syncthing_running() -> bool:
    """Verifica se o processo do Syncthing está ativo no Windows.

    Args:
        None.

    Returns:
        True se o processo syncthing.exe estiver rodando, False caso contrário.

    Raises:
        None.
    """
    try:
        output = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq syncthing.exe", "/FO", "CSV"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return "syncthing.exe" in output.lower()
    except Exception:
        return False


def find_windows_syncthing_config() -> Path | None:
    """Localiza o arquivo de configuração config.xml do Syncthing no Windows.

    Args:
        None.

    Returns:
        Path para config.xml se existir, ou None se não encontrado.

    Raises:
        None.
    """
    candidates = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Syncthing" / "config.xml")

    app_data = os.environ.get("APPDATA")
    if app_data:
        candidates.append(Path(app_data) / "Syncthing" / "config.xml")

    for cand in candidates:
        if cand.is_file():
            return cand

    return candidates[0] if candidates else None


def parse_windows_syncthing_config(
    config_path: Path,
) -> tuple[str | None, str | None, list[SyncthingFolderConfig], list[SyncthingDeviceInfo]]:
    """Analisa o config.xml e extrai api_key, dispositivo local, pastas e dispositivos.

    Args:
        config_path: Caminho para o arquivo config.xml.

    Returns:
        Tupla com (api_key, local_device_id, lista_de_pastas, lista_de_dispositivos).

    Raises:
        ET.ParseError: Se o arquivo XML for inválido.
        FileNotFoundError: Se o arquivo não existir.
    """
    if not config_path.is_file():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {config_path}")

    tree = ET.parse(config_path)
    root = tree.getroot()

    # Chave de API da GUI
    api_key_elem = root.find(".//gui/apikey")
    api_key = api_key_elem.text.strip() if api_key_elem is not None and api_key_elem.text else None

    # Dispositivos globais (filhos diretos de <configuration>)
    devices: list[SyncthingDeviceInfo] = []
    for dev_elem in root.findall("./device"):
        dev_id = dev_elem.get("id", "").strip()
        dev_name = dev_elem.get("name", "").strip()
        dev_intro = dev_elem.get("introducer", "false").lower() == "true"
        auto_accept = dev_elem.get("autoAcceptFolders", "false").lower() == "true"
        if dev_id:
            devices.append(
                SyncthingDeviceInfo(
                    id=dev_id,
                    name=dev_name,
                    introducer=dev_intro,
                    auto_accept_folders=auto_accept,
                )
            )

    # Identificar o dispositivo local via syncthing device-id se disponível
    local_device_id = None
    with contextlib.suppress(Exception):
        dev_id_out = subprocess.check_output(
            ["syncthing", "device-id"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        if dev_id_out:
            local_device_id = dev_id_out

    if not local_device_id and devices:
        local_device_id = devices[0].id

    # Pastas globais (filhas diretas de <configuration>)
    folders: list[SyncthingFolderConfig] = []
    for f_elem in root.findall("./folder"):
        f_id = f_elem.get("id", "").strip()
        f_label = f_elem.get("label", "").strip()
        f_path = f_elem.get("path", "").strip()
        f_type = f_elem.get("type", "sendreceive").strip()
        watcher_enabled = f_elem.get("fsWatcherEnabled", "false").lower() == "true"
        try:
            watcher_delay = int(f_elem.get("fsWatcherDelayS", "10"))
        except ValueError:
            watcher_delay = 10

        versioning_elem = f_elem.find("versioning")
        v_type = versioning_elem.get("type") if versioning_elem is not None else None

        f_devices: list[str] = [
            d_elem.get("id", "").strip()
            for d_elem in f_elem.findall("device")
            if d_elem.get("id")
        ]

        folders.append(
            SyncthingFolderConfig(
                id=f_id,
                label=f_label,
                path=f_path,
                folder_type=f_type,
                watcher_enabled=watcher_enabled,
                watcher_delay_s=watcher_delay,
                versioning_type=v_type,
                devices=f_devices,
            )
        )

    return api_key, local_device_id, folders, devices


def check_syncthing_rest_api(
    api_key: str | None,
    port: int = 8384,
) -> dict[str, Any] | None:
    """Testa a conectividade com a API REST do Syncthing.

    Args:
        api_key: Chave de API da GUI do Syncthing.
        port: Porta de escuta da GUI/API (padrão 8384).

    Returns:
        Dicionário com o estado do sistema se acessível, ou None em caso de falha.

    Raises:
        None.
    """
    if not api_key:
        return None

    url = f"http://127.0.0.1:{port}/rest/system/status"
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return None


def validate_stignore_content(stignore_path: Path) -> tuple[bool, list[str]]:
    """Verifica se o arquivo .stignore contém todas as regras mandatórias anti-conflito.

    Args:
        stignore_path: Caminho do arquivo .stignore.

    Returns:
        Tupla (is_valid, missing_rules) indicando conformidade e regras faltantes.

    Raises:
        None.
    """
    if not stignore_path.is_file():
        return False, list(MANDATORY_IGNORE_PATTERNS)

    try:
        content = stignore_path.read_text(encoding="utf-8")
    except Exception:
        return False, list(MANDATORY_IGNORE_PATTERNS)

    lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("//")
    ]
    missing = [pat for pat in MANDATORY_IGNORE_PATTERNS if pat not in lines]
    return len(missing) == 0, missing


def audit_windows_syncthing(repo_root: Path) -> tuple[list[ValidationItem], dict[str, Any]]:
    """Audita o subsistema Syncthing no host Windows 11.

    Args:
        repo_root: Raiz do repositório RetroGame Lab.

    Returns:
        Tupla com lista de itens de validação e dicionário de metadados coletados.

    Raises:
        None.
    """
    items: list[ValidationItem] = []
    meta: dict[str, Any] = {
        "binary_path": None,
        "is_running": False,
        "config_path": None,
        "api_key": None,
        "local_device_id": None,
        "folders": [],
        "devices": [],
        "api_status": None,
    }

    # 1. Binário
    bin_path = find_windows_syncthing_binary()
    meta["binary_path"] = bin_path
    if bin_path:
        items.append(
            ValidationItem(
                target="Windows",
                category="Binário",
                status=ValidationStatus.OK,
                message=f"Executável do Syncthing detectado ({bin_path.name}).",
                details=str(bin_path),
            )
        )
    else:
        items.append(
            ValidationItem(
                target="Windows",
                category="Binário",
                status=ValidationStatus.WARNING,
                message="syncthing.exe não detectado no PATH.",
                details="Instale com 'winget install Syncthing.Syncthing' ou via bootstrap.ps1.",
            )
        )

    # 2. Processo
    running = is_windows_syncthing_running()
    meta["is_running"] = running
    if running:
        items.append(
            ValidationItem(
                target="Windows",
                category="Processo",
                status=ValidationStatus.OK,
                message="Serviço do Syncthing está em execução em segundo plano.",
            )
        )
    else:
        items.append(
            ValidationItem(
                target="Windows",
                category="Processo",
                status=ValidationStatus.WARNING,
                message="Syncthing não está em execução no Windows.",
                details="Inicie com 'Start-Process syncthing -ArgumentList -no-browser'.",
            )
        )

    # 3. Config.xml
    cfg_path = find_windows_syncthing_config()
    meta["config_path"] = cfg_path
    folders_by_label: dict[str, SyncthingFolderConfig] = {}

    if cfg_path and cfg_path.is_file():
        items.append(
            ValidationItem(
                target="Windows",
                category="Configuração",
                status=ValidationStatus.OK,
                message=f"Arquivo de configuração detectado ({cfg_path.name}).",
                details=str(cfg_path),
            )
        )
        try:
            api_key, local_dev_id, folders, devices = parse_windows_syncthing_config(cfg_path)
            meta["api_key"] = api_key
            meta["local_device_id"] = local_dev_id
            meta["folders"] = folders
            meta["devices"] = devices
            folders_by_label = {f.label: f for f in folders}

            # 4. API REST
            if api_key:
                if running:
                    api_resp = check_syncthing_rest_api(api_key)
                    meta["api_status"] = api_resp
                    if api_resp:
                        uptime_s = api_resp.get("uptime", 0)
                        items.append(
                            ValidationItem(
                                target="Windows",
                                category="API REST",
                                status=ValidationStatus.OK,
                                message="API REST respondendo na porta 8384.",
                                details=f"Uptime: {uptime_s}s | ID: {local_dev_id}",
                            )
                        )
                    else:
                        items.append(
                            ValidationItem(
                                target="Windows",
                                category="API REST",
                                status=ValidationStatus.WARNING,
                                message="Porta 8384 não respondeu à chave de API.",
                            )
                        )
                else:
                    items.append(
                        ValidationItem(
                            target="Windows",
                            category="API REST",
                            status=ValidationStatus.OK,
                            message="Chave de API configurada para o daemon.",
                        )
                    )
            else:
                items.append(
                    ValidationItem(
                        target="Windows",
                        category="API REST",
                        status=ValidationStatus.WARNING,
                        message="Nenhuma chave de API configurada na seção <gui>.",
                    )
                )

        except Exception as err:
            items.append(
                ValidationItem(
                    target="Windows",
                    category="Configuração",
                    status=ValidationStatus.ERROR,
                    message="Falha ao analisar o arquivo config.xml do Syncthing.",
                    details=str(err),
                )
            )
    else:
        items.append(
            ValidationItem(
                target="Windows",
                category="Configuração",
                status=ValidationStatus.WARNING,
                message="Arquivo config.xml não encontrado nas pastas padrão.",
                details=str(cfg_path) if cfg_path else "Caminho indefinido",
            )
        )

    # 5. Validação das Pastas Canônicas no Host
    saves_dir = get_saves_dir(repo_root)
    roms_dir = get_roms_dir(repo_root)
    bios_dir = get_bios_dir(repo_root)

    folder_targets = [
        ("saves", saves_dir),
        ("roms", roms_dir),
        ("bios", bios_dir),
    ]

    for key, f_path in folder_targets:
        spec = SYNCTHING_MANAGED_FOLDERS[key]
        label = spec["label"]

        # 5.1 Diretório físico e marcador .stfolder
        if not f_path.is_dir():
            items.append(
                ValidationItem(
                    target="Windows",
                    category="Pastas",
                    status=ValidationStatus.ERROR,
                    message=f"Diretório físico '{spec['rel_path']}' não existe.",
                    details=str(f_path),
                )
            )
        else:
            stfolder = f_path / ".stfolder"
            if stfolder.exists():
                items.append(
                    ValidationItem(
                        target="Windows",
                        category="Pastas",
                        status=ValidationStatus.OK,
                        message=f"Pasta '{label}' com marcador .stfolder presente.",
                        details=str(f_path),
                    )
                )
            else:
                items.append(
                    ValidationItem(
                        target="Windows",
                        category="Pastas",
                        status=ValidationStatus.WARNING,
                        message=f"Marcador .stfolder ausente em '{spec['rel_path']}'.",
                        details="Necessário para o Syncthing iniciar o pareamento sem falhas.",
                    )
                )

        # 5.2 Mapeamento no config.xml
        cfg_folder = folders_by_label.get(label)
        if not cfg_folder:
            items.append(
                ValidationItem(
                    target="Windows",
                    category="Configuração",
                    status=ValidationStatus.WARNING,
                    message=f"Pasta '{label}' não cadastrada no config.xml do Syncthing.",
                    details=f"Esperado caminho: {f_path.resolve()}",
                )
            )
        else:
            cfg_p = Path(cfg_folder.path).resolve()
            if cfg_p != f_path.resolve():
                items.append(
                    ValidationItem(
                        target="Windows",
                        category="Configuração",
                        status=ValidationStatus.WARNING,
                        message=f"Caminho da pasta '{label}' no config.xml diverge da raiz.",
                        details=f"No config.xml: {cfg_p} | No repositório: {f_path.resolve()}",
                    )
                )

            if not cfg_folder.watcher_enabled:
                items.append(
                    ValidationItem(
                        target="Windows",
                        category="Configuração",
                        status=ValidationStatus.WARNING,
                        message=f"Monitorador de arquivos (fsWatcher) inativo para '{label}'.",
                        details="Ative fsWatcherEnabled para sincronização em tempo real.",
                    )
                )

            if key == "saves":
                if cfg_folder.versioning_type != "simple":
                    items.append(
                        ValidationItem(
                            target="Windows",
                            category="Saves",
                            status=ValidationStatus.WARNING,
                            message="Versionamento simples não configurado em 'retrogames-saves'.",
                            details="Recomenda-se tipo 'simple' com 5 cópias para prevenção.",
                        )
                    )
                else:
                    items.append(
                        ValidationItem(
                            target="Windows",
                            category="Saves",
                            status=ValidationStatus.OK,
                            message="Versionamento preventivo ativo para salvamentos (simple).",
                        )
                    )

    # 6. Validação do .stignore de salvamentos
    stignore_file = saves_dir / ".stignore"
    is_stignore_valid, missing_rules = validate_stignore_content(stignore_file)
    if is_stignore_valid:
        items.append(
            ValidationItem(
                target="Windows",
                category="Saves",
                status=ValidationStatus.OK,
                message="Regras .stignore de proteção de saves em total conformidade.",
                details="Savestates, temporários de emuladores e desktop platforms isolados.",
            )
        )
    else:
        items.append(
            ValidationItem(
                target="Windows",
                category="Saves",
                status=ValidationStatus.WARNING,
                message=f".stignore em '{saves_dir.name}' incompleto ou ausente.",
                details=f"Regras ausentes: {', '.join(missing_rules)}",
            )
        )

    return items, meta


# ==============================================================================
# Métodos de Validação no Android (via ADB)
# ==============================================================================


def run_adb_command(args: list[str], device_id: str = "") -> tuple[int, str, str]:
    """Executa um comando ADB de forma segura e resiliente.

    Args:
        args: Argumentos a serem passados para o comando adb.
        device_id: Identificador opcional do dispositivo alvo (-s).

    Returns:
        Tupla com (exit_code, stdout, stderr).

    Raises:
        None.
    """
    cmd = ["adb"]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(args)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return -1, "", "adb não encontrado no PATH"
    except subprocess.TimeoutExpired:
        return -2, "", "Tempo limite excedido na execução do adb"
    except Exception as err:
        return -3, "", str(err)


def get_connected_adb_devices() -> list[str]:
    """Retorna lista de identificadores de dispositivos Android autorizados via ADB.

    Args:
        None.

    Returns:
        Lista de strings com os IDs dos dispositivos conectados.

    Raises:
        None.
    """
    code, stdout, _ = run_adb_command(["devices"])
    if code != 0:
        return []

    devices: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def audit_android_syncthing(
    repo_root: Path,
    device_id: str = "",
) -> tuple[list[ValidationItem], dict[str, Any]]:
    """Audita o ecossistema Syncthing no dispositivo Android conectado via ADB.

    Args:
        repo_root: Raiz do repositório RetroGame Lab.
        device_id: ID do dispositivo Android opcional.

    Returns:
        Tupla com lista de itens de validação e dicionário de metadados do Android.

    Raises:
        None.
    """
    items: list[ValidationItem] = []
    meta: dict[str, Any] = {
        "device_id": None,
        "model": None,
        "abi": None,
        "installed_package": None,
        "has_storage_perm": False,
        "is_doze_whitelisted": False,
        "folders_status": {},
        "stignore_ok": False,
    }

    # 1. Checagem de conectividade ADB
    devices = get_connected_adb_devices()
    if not devices:
        items.append(
            ValidationItem(
                target="Android",
                category="Conexão",
                status=ValidationStatus.WARNING,
                message="Nenhum dispositivo Android autorizado detectado via ADB.",
                details="Ative a Depuração USB, conecte o aparelho e autorize o computador.",
            )
        )
        return items, meta

    target_device = device_id if device_id in devices else devices[0]
    meta["device_id"] = target_device

    # Obter modelo e ABI
    _, model_out, _ = run_adb_command(["shell", "getprop", "ro.product.model"], target_device)
    _, abi_out, _ = run_adb_command(["shell", "getprop", "ro.product.cpu.abi"], target_device)
    model = model_out.strip()
    abi = abi_out.strip()
    meta["model"] = model
    meta["abi"] = abi

    items.append(
        ValidationItem(
            target="Android",
            category="Conexão",
            status=ValidationStatus.OK,
            message=f"Dispositivo Android conectado: {model} ({target_device}).",
            details=f"Arquitetura ABI: {abi}",
        )
    )

    # 2. Pacote Syncthing
    _, pm_out, _ = run_adb_command(["shell", "pm", "list", "packages"], target_device)
    installed_pkg = None
    for cand in SYNCTHING_ANDROID_PACKAGES:
        if f"package:{cand}" in pm_out:
            installed_pkg = cand
            break

    meta["installed_package"] = installed_pkg
    if installed_pkg:
        items.append(
            ValidationItem(
                target="Android",
                category="App",
                status=ValidationStatus.OK,
                message=f"Cliente Syncthing detectado no Android ({installed_pkg}).",
            )
        )
    else:
        items.append(
            ValidationItem(
                target="Android",
                category="App",
                status=ValidationStatus.WARNING,
                message="Nenhum cliente Syncthing instalado no dispositivo móvel.",
                details="Instale o Syncthing-Fork via 'retrogame android' ou tools/android_apks/.",
            )
        )

    # 3. Permissões de Scoped Storage (MANAGE_EXTERNAL_STORAGE)
    if installed_pkg:
        _, appops_out, _ = run_adb_command(
            ["shell", "appops", "get", installed_pkg, "MANAGE_EXTERNAL_STORAGE"],
            target_device,
        )
        has_storage = "allow" in appops_out.lower()
        meta["has_storage_perm"] = has_storage
        if has_storage:
            items.append(
                ValidationItem(
                    target="Android",
                    category="Permissões",
                    status=ValidationStatus.OK,
                    message=f"Permissão MANAGE_EXTERNAL_STORAGE concedida para {installed_pkg}.",
                )
            )
        else:
            items.append(
                ValidationItem(
                    target="Android",
                    category="Permissões",
                    status=ValidationStatus.WARNING,
                    message=f"Permissão de acesso total a arquivos ausente em {installed_pkg}.",
                    details=f"Conceda com: adb appops set {installed_pkg} "
                    "MANAGE_EXTERNAL_STORAGE allow",
                )
            )

        # 4. Whitelist de Economia de Energia (Doze Mode)
        _, dump_out, _ = run_adb_command(
            ["shell", "dumpsys", "deviceidle", "whitelist"],
            target_device,
        )
        is_whitelisted = installed_pkg in dump_out
        meta["is_doze_whitelisted"] = is_whitelisted
        if is_whitelisted:
            items.append(
                ValidationItem(
                    target="Android",
                    category="Bateria",
                    status=ValidationStatus.OK,
                    message=f"Syncthing ({installed_pkg}) isento de suspensão (Doze Mode).",
                )
            )
        else:
            items.append(
                ValidationItem(
                    target="Android",
                    category="Bateria",
                    status=ValidationStatus.WARNING,
                    message=f"Syncthing ({installed_pkg}) fora da whitelist de bateria.",
                    details=f"Execute: adb shell dumpsys deviceidle whitelist +{installed_pkg}",
                )
            )

    # 5. Estrutura de Diretórios no Armazenamento Interno
    for key, spec in SYNCTHING_MANAGED_FOLDERS.items():
        android_dir = spec["android_path"]
        label = spec["label"]

        # Checar se diretório existe
        code_dir, out_dir, _ = run_adb_command(
            ["shell", f"[ -d '{android_dir}' ] && echo 'exists' || echo 'missing'"],
            target_device,
        )
        dir_exists = code_dir == 0 and "exists" in out_dir

        # Checar se .stfolder existe
        code_stf, out_stf, _ = run_adb_command(
            ["shell", f"[ -d '{android_dir}/.stfolder' ] && echo 'exists' || echo 'missing'"],
            target_device,
        )
        stfolder_exists = code_stf == 0 and "exists" in out_stf
        meta["folders_status"][key] = {"dir": dir_exists, "stfolder": stfolder_exists}

        if dir_exists and stfolder_exists:
            items.append(
                ValidationItem(
                    target="Android",
                    category="Pastas",
                    status=ValidationStatus.OK,
                    message=f"Pasta '{label}' e marcador .stfolder presentes no Android.",
                    details=android_dir,
                )
            )
        elif dir_exists:
            items.append(
                ValidationItem(
                    target="Android",
                    category="Pastas",
                    status=ValidationStatus.WARNING,
                    message=f"Marcador .stfolder ausente na pasta '{label}' no Android.",
                    details=f"Execute: adb shell mkdir -p '{android_dir}/.stfolder'",
                )
            )
        else:
            items.append(
                ValidationItem(
                    target="Android",
                    category="Pastas",
                    status=ValidationStatus.WARNING,
                    message=f"Diretório móvel '{android_dir}' não criado no Android.",
                    details=f"Execute: adb shell mkdir -p '{android_dir}'",
                )
            )

    # 6. Validação do .stignore no Android
    saves_android_stignore = f"{SYNCTHING_MANAGED_FOLDERS['saves']['android_path']}/.stignore"
    ret_cat, cat_out, _ = run_adb_command(["shell", "cat", saves_android_stignore], target_device)

    if ret_cat == 0 and "state" in cat_out:
        lines = [
            line.strip()
            for line in cat_out.splitlines()
            if line.strip() and not line.strip().startswith("//")
        ]
        missing = [pat for pat in MANDATORY_IGNORE_PATTERNS if pat not in lines]
        meta["stignore_ok"] = len(missing) == 0
        if len(missing) == 0:
            items.append(
                ValidationItem(
                    target="Android",
                    category="Saves",
                    status=ValidationStatus.OK,
                    message="Arquivo .stignore presente e íntegro no Android.",
                    details=saves_android_stignore,
                )
            )
        else:
            items.append(
                ValidationItem(
                    target="Android",
                    category="Saves",
                    status=ValidationStatus.WARNING,
                    message=".stignore no Android possui regras faltantes.",
                    details=f"Faltam: {', '.join(missing)}",
                )
            )
    else:
        items.append(
            ValidationItem(
                target="Android",
                category="Saves",
                status=ValidationStatus.WARNING,
                message="Arquivo .stignore ausente em saves/ no armazenamento do Android.",
                details="Risco crítico de sincronização de savestates e arquivos de trava.",
            )
        )

    return items, meta


# ==============================================================================
# Execução da Auditoria Completa
# ==============================================================================


def run_syncthing_validation(
    repo_root: Path | None = None,
    check_android: bool = True,
    check_windows: bool = True,
    device_id: str = "",
) -> SyncthingValidationReport:
    """Executa a auditoria combinada do Syncthing nos ambientes Windows e Android.

    Args:
        repo_root: Caminho raiz do repositório RetroGame Lab.
        check_android: Se deve realizar as verificações no Android via ADB.
        check_windows: Se deve realizar as verificações no host Windows.
        device_id: ID do dispositivo Android opcional para direcionamento do ADB.

    Returns:
        Instância de SyncthingValidationReport com diagnósticos consolidados.

    Raises:
        FileNotFoundError: Se a raiz do repositório não for encontrada.
    """
    root = repo_root or find_repo_root()
    report = SyncthingValidationReport()

    if check_windows:
        win_items, win_meta = audit_windows_syncthing(root)
        report.items.extend(win_items)
        report.windows_config_path = win_meta.get("config_path")
        report.windows_running = win_meta.get("is_running", False)
        report.windows_device_id = win_meta.get("local_device_id")
        report.windows_folders = win_meta.get("folders", [])
        report.windows_devices = win_meta.get("devices", [])

    if check_android:
        and_items, and_meta = audit_android_syncthing(root, device_id=device_id)
        report.items.extend(and_items)
        report.android_connected = bool(and_meta.get("device_id"))
        report.android_device_id = and_meta.get("device_id")
        report.android_package = and_meta.get("installed_package")
        report.android_model = and_meta.get("model")

    return report


# ==============================================================================
# Automação e Auto-Configuração (Apply)
# ==============================================================================


def apply_windows_syncthing_config(
    repo_root: Path,
    android_device_id: str | None = None,
) -> list[str]:
    """Cria e corrige automaticamente as configurações do Syncthing no Windows.

    Garante a existência de .stfolder em cada pasta, grava o .stignore de saves,
    e atualiza o config.xml com as pastas canônicas, versionamento e dispositivos.

    Args:
        repo_root: Raiz do repositório RetroGame Lab.
        android_device_id: ID opcional do dispositivo Android para vinculação automática.

    Returns:
        Lista de ações bem-sucedidas realizadas durante a aplicação.

    Raises:
        FileNotFoundError: Se a raiz do repositório não puder ser resolvida.
    """
    actions: list[str] = []

    # 1. Garantir diretórios locais e marcadores .stfolder
    saves_dir = get_saves_dir(repo_root)
    roms_dir = get_roms_dir(repo_root)
    bios_dir = get_bios_dir(repo_root)

    for p, label in [(saves_dir, "saves"), (roms_dir, "roms"), (bios_dir, "bios")]:
        p.mkdir(parents=True, exist_ok=True)
        stfolder = p / ".stfolder"
        if not stfolder.exists():
            stfolder.mkdir(parents=True, exist_ok=True)
            actions.append(f"Criado marcador .stfolder em data/{label}/")

    # 2. Gravar .stignore canônico em data/saves/.stignore
    stignore_path = saves_dir / ".stignore"
    expected_content = "\n".join(STIGNORE_SAVE_RULES) + "\n"
    current_content = stignore_path.read_text(encoding="utf-8") if stignore_path.is_file() else ""
    if current_content != expected_content:
        stignore_path.write_text(expected_content, encoding="utf-8")
        actions.append("Atualizado data/saves/.stignore com regras anti-conflito completas")

    # 3. Localizar ou Inicializar config.xml
    cfg_path = find_windows_syncthing_config()
    if not cfg_path:
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            cfg_path = Path(local_app) / "Syncthing" / "config.xml"
        else:
            cfg_path = repo_root / "config.xml"

    # Se o arquivo não existir fisicamente, tenta gerar via syncthing generate
    if not cfg_path.is_file():
        bin_path = find_windows_syncthing_binary()
        if bin_path:
            with contextlib.suppress(Exception):
                subprocess.run(
                    [str(bin_path), "generate"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                actions.append("Inicializada nova configuração base via 'syncthing generate'")

    if not cfg_path.is_file():
        # Cria um esqueleto XML limpo se ainda não existir
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        base_xml = """<configuration version="44">
    <gui enabled="true" tls="false">
        <address>127.0.0.1:8384</address>
        <apikey>syncthing-retrogame-lab-default-key</apikey>
    </gui>
</configuration>"""
        cfg_path.write_text(base_xml, encoding="utf-8")
        actions.append(f"Criado arquivo de configuração base em {cfg_path}")

    # Backup de segurança antes de alterar
    backup_path = cfg_path.with_suffix(".xml.bak")
    with contextlib.suppress(Exception):
        shutil.copyfile(cfg_path, backup_path)

    # 4. Modificação estruturada do XML
    tree = ET.parse(cfg_path)
    root = tree.getroot()

    # Detectar dispositivos existentes no nível raiz
    existing_devices = [d.get("id") for d in root.findall("./device") if d.get("id")]

    # Se informado um ID de Android e ele não constar na lista global de dispositivos, adiciona
    if android_device_id and android_device_id not in existing_devices:
        new_dev = ET.SubElement(
            root,
            "device",
            {
                "id": android_device_id,
                "name": "Dispositivo-Android",
                "compression": "metadata",
                "introducer": "false",
                "skipIntroductionRemovals": "false",
                "autoAcceptFolders": "true",
            },
        )
        addr = ET.SubElement(new_dev, "address")
        addr.text = "dynamic"
        existing_devices.append(android_device_id)
        actions.append(f"Adicionado dispositivo Android ({android_device_id}) à lista global")

    # Mapeamento e atualização de cada pasta
    folder_paths_map = {
        "retrogames-saves": saves_dir.resolve(),
        "retrogames-roms": roms_dir.resolve(),
        "retrogames-bios": bios_dir.resolve(),
    }

    for _key, spec in SYNCTHING_MANAGED_FOLDERS.items():
        label = spec["label"]
        target_path_str = str(folder_paths_map[label])

        found_folder = None
        for f_elem in root.findall("./folder"):
            if f_elem.get("label") == label or f_elem.get("id") == spec["default_id"]:
                found_folder = f_elem
                break

        if found_folder is None:
            found_folder = ET.SubElement(
                root,
                "folder",
                {
                    "id": spec["default_id"],
                    "label": label,
                    "path": target_path_str,
                    "type": spec["type"],
                    "rescanIntervalS": str(spec["rescan_interval_s"]),
                    "fsWatcherEnabled": "true" if spec["fs_watcher"] else "false",
                    "fsWatcherDelayS": str(spec["watcher_delay_s"]),
                    "fsWatcherTimeoutS": "0",
                    "ignorePerms": "false",
                    "autoNormalize": "true",
                },
            )
            fs_type = ET.SubElement(found_folder, "filesystemType")
            fs_type.text = "basic"
            actions.append(f"Criada pasta '{label}' no config.xml apontando para {target_path_str}")
        else:
            found_folder.set("path", target_path_str)
            found_folder.set("fsWatcherEnabled", "true")
            found_folder.set("fsWatcherDelayS", str(spec["watcher_delay_s"]))
            actions.append(f"Atualizada pasta '{label}' no config.xml (Watcher ativo)")

        if spec.get("versioning"):
            v_spec = spec["versioning"]
            v_elem = found_folder.find("versioning")
            if v_elem is None:
                v_elem = ET.SubElement(found_folder, "versioning", {"type": v_spec["type"]})
            else:
                v_elem.set("type", v_spec["type"])

            for k, val in v_spec["params"].items():
                param_elem = v_elem.find(f"./param[@key='{k}']")
                if param_elem is None:
                    ET.SubElement(v_elem, "param", {"key": k, "val": str(val)})
                else:
                    param_elem.set("val", str(val))
            v_type = v_spec["type"]
            actions.append(f"Configurado versionamento '{v_type}' (5 cópias) para '{label}'")

        current_folder_devs = [
            d.get("id") for d in found_folder.findall("device") if d.get("id")
        ]
        for dev_id in existing_devices:
            if dev_id and dev_id not in current_folder_devs:
                d_elem = ET.SubElement(found_folder, "device", {"id": dev_id, "introducedBy": ""})
                ET.SubElement(d_elem, "encryptionPassword")
                actions.append(f"Vinculado dispositivo {dev_id[:7]}... à pasta '{label}'")

    with contextlib.suppress(Exception):
        ET.indent(tree, space="    ")

    tree.write(cfg_path, encoding="utf-8", xml_declaration=True)
    actions.append(f"Salvo arquivo de configuração atualizado: {cfg_path}")

    # Se o daemon estiver ativo e houver API key, solicita recarga
    api_key_elem = root.find(".//gui/apikey")
    if api_key_elem is not None and api_key_elem.text and is_windows_syncthing_running():
        key = api_key_elem.text.strip()
        with contextlib.suppress(Exception):
            req = urllib.request.Request(
                "http://127.0.0.1:8384/rest/system/restart",
                data=b"{}",
                headers={"X-API-Key": key, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3.0):
                actions.append("Notificado daemon Syncthing para recarregar via API REST")

    return actions


def generate_android_syncthing_config(
    windows_device_id: str,
    folder_ids_map: dict[str, str],
) -> str:
    """Gera um arquivo config.xml calibrado para importação direta no Syncthing Android.

    Args:
        windows_device_id: ID do dispositivo do computador Windows.
        folder_ids_map: Mapeamento de nome de pasta ('saves', 'roms', 'bios') para Folder ID.

    Returns:
        String formatada em XML compatível com a função Importar Configuração do Syncthing.

    Raises:
        None.
    """
    root = ET.Element("configuration", {"version": "44"})

    # Pastas
    for key, spec in SYNCTHING_MANAGED_FOLDERS.items():
        folder_id = folder_ids_map.get(key, spec["default_id"])
        label = spec["label"]
        android_p = spec["android_path"]

        f_elem = ET.SubElement(
            root,
            "folder",
            {
                "id": folder_id,
                "label": label,
                "path": android_p,
                "type": "sendreceive",
                "rescanIntervalS": "3600",
                "fsWatcherEnabled": "true",
                "fsWatcherDelayS": "10",
                "fsWatcherTimeoutS": "0",
                "ignorePerms": "false",
                "autoNormalize": "true",
            },
        )
        fs_type = ET.SubElement(f_elem, "filesystemType")
        fs_type.text = "basic"

        d_elem = ET.SubElement(f_elem, "device", {"id": windows_device_id, "introducedBy": ""})
        ET.SubElement(d_elem, "encryptionPassword")

        if spec.get("versioning"):
            v_spec = spec["versioning"]
            v_elem = ET.SubElement(f_elem, "versioning", {"type": v_spec["type"]})
            for k, val in v_spec["params"].items():
                ET.SubElement(v_elem, "param", {"key": k, "val": str(val)})

        ET.SubElement(f_elem, "markerName").text = ".stfolder"

    # Dispositivo do Computador Windows
    dev_elem = ET.SubElement(
        root,
        "device",
        {
            "id": windows_device_id,
            "name": "PC-Windows",
            "compression": "metadata",
            "introducer": "false",
            "skipIntroductionRemovals": "false",
            "autoAcceptFolders": "true",
        },
    )
    addr = ET.SubElement(dev_elem, "address")
    addr.text = "dynamic"
    ET.SubElement(dev_elem, "autoAcceptFolders").text = "true"

    # GUI Android
    gui = ET.SubElement(root, "gui", {"enabled": "true", "tls": "false"})
    ET.SubElement(gui, "address").text = "127.0.0.1:8384"

    with contextlib.suppress(Exception):
        ET.indent(root, space="    ")

    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def apply_android_syncthing_setup(
    repo_root: Path,
    device_id: str = "",
    windows_device_id: str | None = None,
) -> list[str]:
    """Aplica correções e provisiona arquivos de configuração no Android via ADB.

    Cria diretórios, marcadores .stfolder, injeta .stignore, concede permissões de
    armazenamento e Doze mode, e gera o arquivo de importação do Syncthing.

    Args:
        repo_root: Raiz do repositório RetroGame Lab.
        device_id: ID do dispositivo Android opcional.
        windows_device_id: ID do dispositivo do computador Windows.

    Returns:
        Lista de ações realizadas com sucesso.

    Raises:
        RuntimeError: Se nenhum dispositivo Android autorizado for detectado.
    """
    actions: list[str] = []
    devices = get_connected_adb_devices()
    if not devices:
        raise RuntimeError("Nenhum dispositivo Android autorizado detectado via ADB.")

    target_device = device_id if device_id in devices else devices[0]

    # 1. Criar estrutura de diretórios e marcadores .stfolder no Android
    for spec in SYNCTHING_MANAGED_FOLDERS.values():
        p = spec["android_path"]
        run_adb_command(["shell", "mkdir", "-p", p], target_device)
        run_adb_command(["shell", "mkdir", "-p", f"{p}/.stfolder"], target_device)
        actions.append(f"Criada pasta e marcador .stfolder em {p}/")

    # 2. Injetar data/saves/.stignore no Android
    saves_dir = get_saves_dir(repo_root)
    local_stignore = saves_dir / ".stignore"
    if not local_stignore.is_file():
        local_stignore.write_text("\n".join(STIGNORE_SAVE_RULES) + "\n", encoding="utf-8")

    android_stignore_target = f"{SYNCTHING_MANAGED_FOLDERS['saves']['android_path']}/.stignore"
    code, _, err = run_adb_command(
        ["push", str(local_stignore), android_stignore_target], target_device
    )
    if code == 0:
        actions.append(f"Enviado .stignore com regras anti-conflito para {android_stignore_target}")
    else:
        actions.append(f"Aviso: Falha ao enviar .stignore via adb push ({err.strip()})")

    # 3. Detectar pacote instalado e conceder permissões
    _, pm_out, _ = run_adb_command(["shell", "pm", "list", "packages"], target_device)
    installed_pkg = None
    for cand in SYNCTHING_ANDROID_PACKAGES:
        if f"package:{cand}" in pm_out:
            installed_pkg = cand
            break

    if installed_pkg:
        run_adb_command(
            ["shell", "appops", "set", installed_pkg, "MANAGE_EXTERNAL_STORAGE", "allow"],
            target_device,
        )
        actions.append(f"Concedida permissão MANAGE_EXTERNAL_STORAGE para {installed_pkg}")

        run_adb_command(
            ["shell", "dumpsys", "deviceidle", "whitelist", f"+{installed_pkg}"],
            target_device,
        )
        actions.append("Syncthing inserido na whitelist de economia de bateria (Doze Mode)")

    # 4. Gerar e Enviar Arquivo de Importação para o Syncthing Android
    if windows_device_id:
        cfg_path = find_windows_syncthing_config()
        folder_ids_map = {}
        if cfg_path and cfg_path.is_file():
            with contextlib.suppress(Exception):
                _, _, f_list, _ = parse_windows_syncthing_config(cfg_path)
                for f in f_list:
                    if f.label == "retrogames-saves":
                        folder_ids_map["saves"] = f.id
                    elif f.label == "retrogames-roms":
                        folder_ids_map["roms"] = f.id
                    elif f.label == "retrogames-bios":
                        folder_ids_map["bios"] = f.id

        xml_content = generate_android_syncthing_config(windows_device_id, folder_ids_map)
        scratch_dir = repo_root / "scratch"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        local_xml_path = scratch_dir / "syncthing_android_config.xml"
        local_xml_path.write_text(xml_content, encoding="utf-8")

        run_adb_command(
            ["shell", "mkdir", "-p", "/storage/emulated/0/RetroGames/config"],
            target_device,
        )
        dest_cfg = "/storage/emulated/0/RetroGames/config/syncthing_android_config.xml"
        run_adb_command(["push", str(local_xml_path), dest_cfg], target_device)

        dest_down = "/storage/emulated/0/Download/syncthing_android_config.xml"
        run_adb_command(["push", str(local_xml_path), dest_down], target_device)

        actions.append(
            "Gerado arquivo de auto-configuração do Syncthing em "
            "/storage/emulated/0/RetroGames/config/syncthing_android_config.xml e Download/"
        )

    # 5. Iniciar o app Syncthing no Android
    if installed_pkg:
        run_adb_command(
            ["shell", "monkey", "-p", installed_pkg, "-c", "android.intent.category.LAUNCHER", "1"],
            target_device,
        )
        actions.append(f"Iniciado aplicativo {installed_pkg} no Android")

    return actions


# ==============================================================================
# Apresentação Visual no Terminal (Rich)
# ==============================================================================


def render_syncthing_report(
    report: SyncthingValidationReport,
    console: Console | None = None,
) -> None:
    """Renderiza o relatório de auditoria do Syncthing em tabela colorida no terminal.

    Args:
        report: Instância de SyncthingValidationReport a ser exibida.
        console: Instância do Console do Rich (se None, utiliza padrão).

    Returns:
        None.

    Raises:
        None.
    """
    c = console or Console()

    c.print("\n[bold green]=== Auditoria de Sincronização Syncthing ===[/bold green]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Alvo", width=10, style="cyan")
    table.add_column("Categoria", width=14, style="yellow")
    table.add_column("Status", width=10)
    table.add_column("Diagnóstico / Recomendação")

    status_color_map = {
        ValidationStatus.OK: "[bold green][OK][/bold green]",
        ValidationStatus.WARNING: "[bold yellow][AVISO][/bold yellow]",
        ValidationStatus.ERROR: "[bold red][ERRO][/bold red]",
    }

    for item in report.items:
        stat_formatted = status_color_map.get(item.status, item.status.value)
        msg_full = item.message
        if item.details:
            msg_full += f"\n[dim]{item.details}[/dim]"
        table.add_row(item.target, item.category, stat_formatted, msg_full)

    c.print(table)

    c.print("\n[bold cyan]Parâmetros do Cluster de Sincronização:[/bold cyan]")
    if report.windows_device_id:
        c.print(f"  • [green]ID Dispositivo Windows:[/green] {report.windows_device_id}")
    if report.android_device_id:
        desc = f"{report.android_model} ({report.android_device_id})"
        c.print(f"  • [green]Dispositivo Android Alvo:[/green] {desc}")

    if report.has_errors:
        c.print("\n[bold red][!] Falhas impeditivas na configuração do Syncthing.[/bold red]")
        c.print("Execute [yellow].\\retrogame syncthing --apply[/yellow] para auto-corrigir.\n")
    elif report.has_warnings:
        c.print("\n[bold yellow][*] O sistema possui avisos ou pendências.[/bold yellow]")
        c.print("Execute [yellow].\\retrogame syncthing --apply[/yellow] para aplicar correções.\n")
    else:
        c.print("\n[bold green][V] Configurações do Syncthing 100% íntegras![/bold green]\n")
