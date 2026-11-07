"""Testes unitários e de integração para o subsistema de validação e provisionamento do Syncthing.

Valida regras de .stignore, detecção do executável, parse do config.xml, testes de API REST,
auditoria no Android via ADB, geração de configurações portáteis e comandos CLI.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from retrogame_lab.cli import app
from retrogame_lab.syncthing import (
    MANDATORY_IGNORE_PATTERNS,
    STIGNORE_SAVE_RULES,
    SyncthingFolderConfig,
    SyncthingValidationReport,
    ValidationItem,
    ValidationStatus,
    apply_android_syncthing_setup,
    apply_windows_syncthing_config,
    audit_android_syncthing,
    audit_windows_syncthing,
    check_syncthing_rest_api,
    find_windows_syncthing_binary,
    find_windows_syncthing_config,
    generate_android_syncthing_config,
    get_connected_adb_devices,
    is_valid_syncthing_device_id,
    is_windows_syncthing_running,
    parse_windows_syncthing_config,
    render_syncthing_report,
    run_adb_command,
    run_syncthing_validation,
    start_windows_syncthing_daemon,
    validate_stignore_content,
)

runner = CliRunner()


def test_validate_stignore_content_valid(tmp_path: Path) -> None:
    """Verifica se um .stignore completo com todas as regras é validado como True.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None.

    Raises:
        None.
    """
    stignore = tmp_path / ".stignore"
    stignore.write_text("\n".join(STIGNORE_SAVE_RULES), encoding="utf-8")

    is_valid, missing = validate_stignore_content(stignore)
    assert is_valid is True
    assert missing == []


def test_validate_stignore_content_missing_rules(tmp_path: Path) -> None:
    """Verifica a detecção de regras ausentes no arquivo .stignore.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None.

    Raises:
        None.
    """
    stignore = tmp_path / ".stignore"
    stignore.write_text("*.state*\n*.tmp*\n", encoding="utf-8")

    is_valid, missing = validate_stignore_content(stignore)
    assert is_valid is False
    assert "*.s[0-9][0-9]" in missing
    assert "*.ppst" in missing
    assert "PPSSPP_STATE/" in missing
    assert "ps3/" in missing


def test_validate_stignore_content_missing_file(tmp_path: Path) -> None:
    """Verifica o comportamento quando o arquivo .stignore não existe fisicamente.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None.

    Raises:
        None.
    """
    stignore = tmp_path / "non_existent_.stignore"
    is_valid, missing = validate_stignore_content(stignore)
    assert is_valid is False
    assert len(missing) == len(MANDATORY_IGNORE_PATTERNS)


def test_find_windows_syncthing_binary_in_path(mocker: MockerFixture, tmp_path: Path) -> None:
    """Verifica a localização do binário syncthing.exe quando presente no PATH.

    Args:
        mocker: Fixture do pytest-mock.
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None.

    Raises:
        None.
    """
    fake_bin = tmp_path / "syncthing.exe"
    fake_bin.touch()
    mocker.patch("shutil.which", return_value=str(fake_bin))

    found = find_windows_syncthing_binary()
    assert found == fake_bin.resolve()


def test_find_windows_syncthing_binary_via_winget(
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifica a localização do syncthing.exe no link simbólico do WinGet.

    Args:
        mocker: Fixture do pytest-mock.
        tmp_path: Diretório temporário fornecido pelo pytest.
        monkeypatch: Fixture de variáveis de ambiente.

    Returns:
        None.

    Raises:
        None.
    """
    mocker.patch("shutil.which", return_value=None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    winget_dir = tmp_path / "Microsoft" / "WinGet" / "Links"
    winget_dir.mkdir(parents=True, exist_ok=True)
    winget_bin = winget_dir / "syncthing.exe"
    winget_bin.touch()

    found = find_windows_syncthing_binary()
    assert found == winget_bin


def test_is_windows_syncthing_running(mocker: MockerFixture) -> None:
    """Verifica a identificação do processo do Syncthing em execução e parado.

    Args:
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mocker.patch(
        "subprocess.check_output",
        return_value='"syncthing.exe","1234","Console","1","45.000 K"',
    )
    assert is_windows_syncthing_running() is True

    mocker.patch(
        "subprocess.check_output",
        return_value="INFO: No tasks are running which match the specified criteria.",
    )
    assert is_windows_syncthing_running() is False

    mocker.patch("subprocess.check_output", side_effect=Exception("tasklist error"))
    assert is_windows_syncthing_running() is False


def test_is_valid_syncthing_device_id() -> None:
    """Verifica a validação rigorosa de formato de Device ID do Syncthing.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    valid_id = "AFMVTPS-CB2OY5G-NQ55K45-6LCQIU2-YAMHTS2-C4PGASG-QJB3RIY-DEUAHAM"
    assert is_valid_syncthing_device_id(valid_id) is True

    valid_raw = valid_id.replace("-", "")
    assert is_valid_syncthing_device_id(valid_raw) is True

    assert is_valid_syncthing_device_id("0091208971") is False
    assert is_valid_syncthing_device_id("emulator-5554") is False
    assert is_valid_syncthing_device_id("") is False
    assert is_valid_syncthing_device_id(None) is False


def test_start_windows_syncthing_daemon(mocker: MockerFixture) -> None:
    """Verifica a inicialização desacoplada do processo do Syncthing.

    Args:
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mocker.patch("retrogame_lab.syncthing.is_windows_syncthing_running", return_value=True)
    assert start_windows_syncthing_daemon() is True

    mocker.patch("retrogame_lab.syncthing.is_windows_syncthing_running", return_value=False)
    mocker.patch("retrogame_lab.syncthing.find_windows_syncthing_binary", return_value=None)
    assert start_windows_syncthing_daemon() is False

    mocker.patch(
        "retrogame_lab.syncthing.find_windows_syncthing_binary",
        return_value=Path("C:/bin/syncthing.exe"),
    )
    mock_popen = mocker.patch("subprocess.Popen")
    assert start_windows_syncthing_daemon() is True
    assert mock_popen.called


def test_find_windows_syncthing_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica a localização prioritária do config.xml em LOCALAPPDATA ou APPDATA.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.
        monkeypatch: Fixture de variáveis de ambiente.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))

    cfg_dir = tmp_path / "local" / "Syncthing"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "config.xml"
    cfg_file.touch()

    found = find_windows_syncthing_config()
    assert found == cfg_file


def test_parse_windows_syncthing_config(tmp_path: Path, mocker: MockerFixture) -> None:
    """Verifica o parse de config.xml, extraindo chave de API, pastas e dispositivos.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mocker.patch("subprocess.check_output", return_value="LOCAL-DEV-ID-12345")

    xml_content = """<configuration version="44">
    <folder id="retrogames-saves" label="retrogames-saves" path="c:\\data\\saves"
            type="sendreceive" fsWatcherEnabled="true" fsWatcherDelayS="10">
        <device id="DEVICE-PHONE" />
        <versioning type="simple">
            <param key="keep" val="5" />
        </versioning>
    </folder>
    <device id="LOCAL-DEV-ID-12345" name="PC-Local" introducer="false" autoAcceptFolders="true" />
    <device id="DEVICE-PHONE" name="Smartphone" introducer="false" autoAcceptFolders="false" />
    <gui enabled="true">
        <address>127.0.0.1:8384</address>
        <apikey>test-api-key-12345</apikey>
    </gui>
</configuration>"""
    cfg_file = tmp_path / "config.xml"
    cfg_file.write_text(xml_content, encoding="utf-8")

    api_key, local_id, folders, devices = parse_windows_syncthing_config(cfg_file)
    assert api_key == "test-api-key-12345"
    assert local_id == "LOCAL-DEV-ID-12345"
    assert len(folders) == 1
    assert folders[0].id == "retrogames-saves"
    assert folders[0].watcher_enabled is True
    assert folders[0].versioning_type == "simple"
    assert "DEVICE-PHONE" in folders[0].devices
    assert len(devices) == 2


def test_parse_windows_syncthing_config_missing_file(tmp_path: Path) -> None:
    """Verifica que FileNotFoundError é lançado ao analisar arquivo inexistente.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None.

    Raises:
        None.
    """
    with pytest.raises(FileNotFoundError):
        parse_windows_syncthing_config(tmp_path / "nao_existe.xml")


def test_check_syncthing_rest_api(mocker: MockerFixture) -> None:
    """Verifica a consulta da API REST com sucesso e tratamento de erros.

    Args:
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    assert check_syncthing_rest_api(None) is None

    mock_resp = mocker.MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({"uptime": 3600, "myID": "DEV-123"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    mocker.patch("urllib.request.urlopen", return_value=mock_resp)
    status = check_syncthing_rest_api("test-key")
    assert status is not None
    assert status["uptime"] == 3600

    mocker.patch("urllib.request.urlopen", side_effect=Exception("Connection refused"))
    assert check_syncthing_rest_api("test-key") is None


def test_audit_windows_syncthing(mock_repo_root: Path, mocker: MockerFixture) -> None:
    """Verifica a auditoria completa do ambiente Windows em um repositório mockado.

    Args:
        mock_repo_root: Fixture de raiz mockada.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    saves_dir = mock_repo_root / "data" / "saves"
    roms_dir = mock_repo_root / "data" / "roms"
    bios_dir = mock_repo_root / "data" / "bios"

    (saves_dir / ".stfolder").mkdir(parents=True, exist_ok=True)
    (roms_dir / ".stfolder").mkdir(parents=True, exist_ok=True)
    (bios_dir / ".stfolder").mkdir(parents=True, exist_ok=True)
    (saves_dir / ".stignore").write_text("\n".join(STIGNORE_SAVE_RULES), encoding="utf-8")

    mocker.patch(
        "retrogame_lab.syncthing.find_windows_syncthing_binary",
        return_value=Path("C:/bin/syncthing.exe"),
    )
    mocker.patch("retrogame_lab.syncthing.is_windows_syncthing_running", return_value=True)

    fake_folders = [
        SyncthingFolderConfig(
            id="retrogames-saves",
            label="retrogames-saves",
            path=str(saves_dir),
            folder_type="sendreceive",
            watcher_enabled=True,
            watcher_delay_s=10,
            versioning_type="simple",
        ),
        SyncthingFolderConfig(
            id="retrogames-roms",
            label="retrogames-roms",
            path=str(roms_dir),
            folder_type="sendreceive",
            watcher_enabled=True,
            watcher_delay_s=10,
        ),
        SyncthingFolderConfig(
            id="retrogames-bios",
            label="retrogames-bios",
            path=str(bios_dir),
            folder_type="sendreceive",
            watcher_enabled=True,
            watcher_delay_s=10,
        ),
    ]

    mocker.patch(
        "retrogame_lab.syncthing.parse_windows_syncthing_config",
        return_value=("fake-key", "LOCAL-ID", fake_folders, []),
    )
    fake_cfg = mock_repo_root / "config.xml"
    fake_cfg.touch()
    mocker.patch("retrogame_lab.syncthing.find_windows_syncthing_config", return_value=fake_cfg)
    mocker.patch("retrogame_lab.syncthing.check_syncthing_rest_api", return_value={"uptime": 120})

    items, meta = audit_windows_syncthing(mock_repo_root)
    assert any(i.category == "Binário" and i.status == ValidationStatus.OK for i in items)
    assert any(i.category == "Processo" and i.status == ValidationStatus.OK for i in items)
    assert any(i.category == "Saves" and "conformidade" in i.message for i in items)
    assert meta["is_running"] is True


def test_run_adb_command(mocker: MockerFixture) -> None:
    """Verifica a execução resiliente de comandos ADB e captura de exceções.

    Args:
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mock_proc = mocker.MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "12345 device"
    mock_proc.stderr = ""
    mocker.patch("subprocess.run", return_value=mock_proc)

    code, out, _ = run_adb_command(["devices"])
    assert code == 0
    assert "12345 device" in out

    mocker.patch("subprocess.run", side_effect=FileNotFoundError("adb not found"))
    code_err, _, err = run_adb_command(["devices"])
    assert code_err == -1
    assert "não encontrado" in err


def test_get_connected_adb_devices(mocker: MockerFixture) -> None:
    """Verifica o parsing de dispositivos autorizados no comando adb devices.

    Args:
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mocker.patch(
        "retrogame_lab.syncthing.run_adb_command",
        return_value=(
            0,
            "List of devices attached\nemulator-5554\tdevice\nphone-1234\tunauthorized\n",
            "",
        ),
    )
    devices = get_connected_adb_devices()
    assert devices == ["emulator-5554"]

    mocker.patch(
        "retrogame_lab.syncthing.run_adb_command",
        return_value=(1, "", "daemon not running"),
    )
    assert get_connected_adb_devices() == []


def test_audit_android_syncthing_connected(mock_repo_root: Path, mocker: MockerFixture) -> None:
    """Verifica a auditoria no Android quando o dispositivo e permissões estão íntegros.

    Args:
        mock_repo_root: Fixture de raiz mockada.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mocker.patch("retrogame_lab.syncthing.get_connected_adb_devices", return_value=["phone-001"])

    def mock_adb(args: list[str], dev: str = "") -> tuple[int, str, str]:
        cmd_str = " ".join(args)
        if "getprop ro.product.model" in cmd_str:
            return 0, "Pixel 8 Pro", ""
        if "getprop ro.product.cpu.abi" in cmd_str:
            return 0, "arm64-v8a", ""
        if "pm list packages" in cmd_str:
            return 0, "package:com.github.catfriend1.syncthingandroid", ""
        if "appops get" in cmd_str:
            return 0, "allow", ""
        if "dumpsys deviceidle whitelist" in cmd_str:
            return 0, "com.github.catfriend1.syncthingandroid", ""
        if "echo 'exists'" in cmd_str:
            return 0, "exists", ""
        if "cat" in cmd_str and ".stignore" in cmd_str:
            return 0, "\n".join(STIGNORE_SAVE_RULES), ""
        return 0, "", ""

    mocker.patch("retrogame_lab.syncthing.run_adb_command", side_effect=mock_adb)

    items, meta = audit_android_syncthing(mock_repo_root)
    assert meta["model"] == "Pixel 8 Pro"
    assert meta["has_storage_perm"] is True
    assert meta["is_doze_whitelisted"] is True
    assert meta["stignore_ok"] is True
    assert all(i.status == ValidationStatus.OK for i in items)


def test_audit_android_syncthing_disconnected(mock_repo_root: Path, mocker: MockerFixture) -> None:
    """Verifica que um aviso é registrado quando nenhum dispositivo Android está conectado.

    Args:
        mock_repo_root: Fixture de raiz mockada.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mocker.patch("retrogame_lab.syncthing.get_connected_adb_devices", return_value=[])
    items, meta = audit_android_syncthing(mock_repo_root)
    assert meta["device_id"] is None
    assert any(i.category == "Conexão" and i.status == ValidationStatus.WARNING for i in items)


def test_apply_windows_syncthing_config(
    mock_repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifica a auto-configuração no Windows criando .stfolder, .stignore e config.xml.

    Args:
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture de variáveis de ambiente.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(mock_repo_root))
    cfg_file = mock_repo_root / "Syncthing" / "config.xml"

    valid_android_id = "AFMVTPS-CB2OY5G-NQ55K45-6LCQIU2-YAMHTS2-C4PGASG-QJB3RIY-DEUAHAM"
    actions = apply_windows_syncthing_config(mock_repo_root, android_device_id=valid_android_id)

    saves_dir = mock_repo_root / "data" / "saves"
    roms_dir = mock_repo_root / "data" / "roms"
    bios_dir = mock_repo_root / "data" / "bios"

    assert (saves_dir / ".stfolder").is_dir()
    assert (roms_dir / ".stfolder").is_dir()
    assert (bios_dir / ".stfolder").is_dir()

    stignore = saves_dir / ".stignore"
    assert stignore.is_file()
    assert "*.state*" in stignore.read_text(encoding="utf-8")

    _, _, folders, devices = parse_windows_syncthing_config(cfg_file)
    assert len(folders) == 3
    assert any(d.id == valid_android_id for d in devices)

    saves_f = next(f for f in folders if f.label == "retrogames-saves")
    assert saves_f.versioning_type == "simple"
    assert saves_f.watcher_enabled is True
    assert valid_android_id in saves_f.devices
    assert len(actions) > 0


def test_apply_windows_syncthing_config_sanitizes_invalid_id(
    mock_repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifica o auto-expurgo de IDs de dispositivos inválidos (ex: serial ADB).

    Args:
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture de variáveis de ambiente.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(mock_repo_root))
    cfg_dir = mock_repo_root / "Syncthing"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "config.xml"

    bad_xml = """<configuration version="44">
    <folder id="retrogames-saves" label="retrogames-saves" path="c:\\saves" type="sendreceive">
        <device id="0091208971" />
    </folder>
    <device id="0091208971" name="Dispositivo-Android" />
    <gui enabled="true"><address>127.0.0.1:8384</address><apikey>key</apikey></gui>
</configuration>"""
    cfg_file.write_text(bad_xml, encoding="utf-8")

    actions = apply_windows_syncthing_config(mock_repo_root, android_device_id="0091208971")

    _, _, folders, devices = parse_windows_syncthing_config(cfg_file)
    assert not any(d.id == "0091208971" for d in devices)
    assert not any("0091208971" in f.devices for f in folders)
    assert any("Removido identificador inválido" in a for a in actions)


def test_generate_android_syncthing_config() -> None:
    """Verifica a estrutura XML gerada para importação no Syncthing Android.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    xml_str = generate_android_syncthing_config(
        windows_device_id="WIN-DEV-12345",
        folder_ids_map={"saves": "id-saves-1", "roms": "id-roms-2", "bios": "id-bios-3"},
    )
    root = ET.fromstring(xml_str)
    assert root.tag == "configuration"

    folders = root.findall("./folder")
    assert len(folders) == 3

    saves_elem = next(f for f in folders if f.get("id") == "id-saves-1")
    assert saves_elem.get("path") == "/storage/emulated/0/RetroGames/saves"
    assert saves_elem.find("versioning") is not None

    win_dev = root.find("./device[@id='WIN-DEV-12345']")
    assert win_dev is not None
    assert win_dev.get("name") == "PC-Windows"


def test_apply_android_syncthing_setup(mock_repo_root: Path, mocker: MockerFixture) -> None:
    """Verifica o provisionamento no Android disparando criação de pastas e push de configs.

    Args:
        mock_repo_root: Fixture de raiz mockada.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mocker.patch("retrogame_lab.syncthing.get_connected_adb_devices", return_value=["phone-001"])
    adb_calls: list[list[str]] = []

    def mock_adb(args: list[str], dev: str = "") -> tuple[int, str, str]:
        adb_calls.append(args)
        if "pm list packages" in " ".join(args):
            return 0, "package:com.github.catfriend1.syncthingandroid", ""
        return 0, "", ""

    mocker.patch("retrogame_lab.syncthing.run_adb_command", side_effect=mock_adb)

    actions = apply_android_syncthing_setup(
        mock_repo_root,
        windows_device_id="WIN-DEV-12345",
    )
    assert len(actions) > 0
    call_strs = [" ".join(c) for c in adb_calls]
    assert any("mkdir -p /storage/emulated/0/RetroGames/saves" in c for c in call_strs)
    assert any("push" in c and ".stignore" in c for c in call_strs)
    assert any("appops set com.github.catfriend1.syncthingandroid" in c for c in call_strs)
    assert any("dumpsys deviceidle whitelist" in c for c in call_strs)


def test_run_syncthing_validation(mock_repo_root: Path, mocker: MockerFixture) -> None:
    """Verifica a função agregadora run_syncthing_validation.

    Args:
        mock_repo_root: Fixture de raiz mockada.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mocker.patch(
        "retrogame_lab.syncthing.audit_windows_syncthing",
        return_value=(
            [
                ValidationItem(
                    target="Windows", category="Binário", status=ValidationStatus.OK, message="OK"
                )
            ],
            {"local_device_id": "WIN-123", "is_running": True},
        ),
    )
    valid_android_id = "AFMVTPS-CB2OY5G-NQ55K45-6LCQIU2-YAMHTS2-C4PGASG-QJB3RIY-DEUAHAM"
    mocker.patch(
        "retrogame_lab.syncthing.audit_android_syncthing",
        return_value=(
            [
                ValidationItem(
                    target="Android", category="Conexão", status=ValidationStatus.OK, message="OK"
                )
            ],
            {
                "adb_serial": "AND-456",
                "syncthing_device_id": valid_android_id,
                "model": "Pixel",
            },
        ),
    )

    report = run_syncthing_validation(mock_repo_root)
    assert report.windows_running is True
    assert report.windows_device_id == "WIN-123"
    assert report.android_connected is True
    assert report.android_adb_serial == "AND-456"
    assert report.android_device_id == valid_android_id
    assert len(report.items) == 2


def test_render_syncthing_report(mocker: MockerFixture) -> None:
    """Verifica a renderização em console do relatório sem exceções.

    Args:
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mock_console = mocker.MagicMock()
    report = SyncthingValidationReport(
        items=[
            ValidationItem(
                target="Windows", category="Binário", status=ValidationStatus.OK, message="Ok"
            ),
            ValidationItem(
                target="Android", category="App", status=ValidationStatus.WARNING, message="Aviso"
            ),
            ValidationItem(
                target="Windows", category="Pastas", status=ValidationStatus.ERROR, message="Erro"
            ),
        ],
        windows_device_id="WIN-123",
        android_device_id="AND-456",
        android_model="Pixel",
    )
    render_syncthing_report(report, console=mock_console)
    assert mock_console.print.call_count >= 3


def test_cli_syncthing_json(mock_repo_root: Path, mocker: MockerFixture) -> None:
    """Verifica o comando CLI retrogame-lab syncthing com saída em formato JSON.

    Args:
        mock_repo_root: Fixture de raiz mockada.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mocker.patch(
        "retrogame_lab.syncthing.audit_windows_syncthing",
        return_value=(
            [
                ValidationItem(
                    target="Windows", category="Binário", status=ValidationStatus.OK, message="OK"
                )
            ],
            {},
        ),
    )
    mocker.patch(
        "retrogame_lab.syncthing.audit_android_syncthing",
        return_value=([], {}),
    )

    result = runner.invoke(app, ["syncthing", "-p", str(mock_repo_root), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "windows" in data
    assert "android" in data
    assert "items" in data


def test_cli_syncthing_apply(mock_repo_root: Path, mocker: MockerFixture) -> None:
    """Verifica o comando CLI retrogame-lab syncthing --apply.

    Args:
        mock_repo_root: Fixture de raiz mockada.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mock_apply_win = mocker.patch(
        "retrogame_lab.cli.apply_windows_syncthing_config",
        return_value=["Criado marcador .stfolder"],
    )
    mocker.patch(
        "retrogame_lab.cli.run_syncthing_validation",
        return_value=SyncthingValidationReport(
            items=[
                ValidationItem(
                    target="Windows", category="Binário", status=ValidationStatus.OK, message="OK"
                )
            ],
            android_connected=False,
        ),
    )

    result = runner.invoke(app, ["syncthing", "-p", str(mock_repo_root), "--apply", "--no-android"])
    assert result.exit_code == 0
    assert "Aplicando auto-configuração" in result.stdout
    assert mock_apply_win.called


def test_cli_syncthing_start(mock_repo_root: Path, mocker: MockerFixture) -> None:
    """Verifica o acionamento do daemon via flag --start no CLI.

    Args:
        mock_repo_root: Raiz mockada do repositório.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mock_start = mocker.patch(
        "retrogame_lab.cli.start_windows_syncthing_daemon",
        return_value=True,
    )
    mocker.patch(
        "retrogame_lab.cli.run_syncthing_validation",
        return_value=SyncthingValidationReport(
            items=[
                ValidationItem(
                    target="Windows", category="Binário", status=ValidationStatus.OK, message="OK"
                )
            ],
            windows_running=False,
            android_connected=False,
        ),
    )

    result = runner.invoke(
        app, ["syncthing", "-p", str(mock_repo_root), "--start", "--no-android"]
    )
    assert result.exit_code == 0
    assert "Daemon iniciado em segundo plano" in result.stdout
    assert mock_start.called

