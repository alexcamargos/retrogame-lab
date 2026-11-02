"""Testes unitários para a CLI do RetroGame Lab.

Valida subcomandos version, info e audit, incluindo relatórios em console e JSON.
"""

import json
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from retrogame_lab.cli import app

runner = CliRunner()


def test_cli_version() -> None:
    """Verifica se o comando version exibe a versão correta do pacote.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "RetroGame Lab" in result.stdout
    assert "0.1.0" in result.stdout


def test_cli_info(mock_repo_root: Path) -> None:
    """Verifica se o comando info exibe a tabela de plataformas homologadas.

    Args:
        mock_repo_root: Fixture de raiz mockada.

    Returns:
        None.

    Raises:
        None.
    """
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "Plataformas Homologadas" in result.stdout
    assert "snes" in result.stdout
    assert "ps1" in result.stdout
    assert "gc" in result.stdout


def test_cli_audit_clean(mock_repo_root: Path) -> None:
    """Verifica se a auditoria em repositório limpo conclui com sucesso (código 0).

    Args:
        mock_repo_root: Fixture de raiz mockada.

    Returns:
        None.

    Raises:
        None.
    """
    result = runner.invoke(app, ["audit", "--path", str(mock_repo_root)])
    assert result.exit_code == 0
    assert "Auditoria de Integridade" in result.stdout


def test_cli_audit_json(mock_repo_root: Path) -> None:
    """Verifica se a flag --json-output gera uma carga JSON válida.

    Args:
        mock_repo_root: Fixture de raiz mockada.

    Returns:
        None.

    Raises:
        None.
    """
    result = runner.invoke(app, ["audit", "--path", str(mock_repo_root), "--json-output"])
    assert result.exit_code == 0

    parsed = json.loads(result.stdout)
    assert "bios" in parsed
    assert "roms" in parsed
    assert "saves" in parsed
    assert parsed["has_errors"] is False


def test_cli_audit_json_alias_and_full(mock_repo_root: Path) -> None:
    """Verifica se os aliases --json e --full são aceitos sem erro.

    Args:
        mock_repo_root: Fixture de raiz mockada.

    Returns:
        None.

    Raises:
        None.
    """
    result = runner.invoke(app, ["audit", "--path", str(mock_repo_root), "--json", "--full"])
    assert result.exit_code == 0

    parsed = json.loads(result.stdout)
    assert "bios" in parsed
    assert parsed["has_errors"] is False


def test_cli_audit_error_exit_code(mock_repo_root: Path) -> None:
    """Verifica se a auditoria encerra com código 1 quando há erros críticos.

    Args:
        mock_repo_root: Fixture de raiz mockada.

    Returns:
        None.

    Raises:
        None.
    """
    # Criar um savestate ilegal para disparar erro crítico
    illegal_savestate = mock_repo_root / "data" / "saves" / "snes" / "game.state"
    illegal_savestate.write_text("corrupted", encoding="utf-8")

    result = runner.invoke(app, ["audit", "--path", str(mock_repo_root)])
    assert result.exit_code == 1
    assert "Auditoria concluída com erros críticos" in result.stdout


def test_cli_sanitize_dry_run_and_apply(tmp_path: Path) -> None:
    """Verifica a execução do comando sanitize em modo dry-run e apply.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None.

    Raises:
        None.
    """
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    dirty_rom = roms_dir / "Super Mario World (USA).sfc"
    dirty_rom.write_text("dummy", encoding="utf-8")

    # 1. Simulação (--dry-run)
    res_dry = runner.invoke(app, ["sanitize", "--path", str(tmp_path), "--dry-run"])
    assert res_dry.exit_code == 0
    assert "Super Mario World (USA).sfc" in res_dry.stdout
    assert "super_mario_world_(usa).sfc" in res_dry.stdout
    assert dirty_rom.exists()

    # 2. Aplicação real (--apply)
    res_apply = runner.invoke(app, ["sanitize", "--path", str(tmp_path), "--apply"])
    assert res_apply.exit_code == 0
    assert not dirty_rom.exists()
    assert (roms_dir / "super_mario_world_(usa).sfc").exists()


def test_cli_sanitize_missing_directory(tmp_path: Path) -> None:
    """Verifica se o comando sanitize encerra com código 1 quando a pasta não existe.

    Args:
        tmp_path: Diretório temporário.

    Returns:
        None.

    Raises:
        None.
    """
    res = runner.invoke(app, ["sanitize", "--path", str(tmp_path / "missing")])
    assert res.exit_code == 1
    assert "não encontrado" in res.stdout


def test_cli_import_rom_single(
    tmp_path: Path, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica a importação de uma ROM individual via comando CLI import-rom.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest para alteração de diretório de trabalho.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)

    source_rom = tmp_path / "Chrono Trigger 'Special Edition'.sfc"
    source_rom.write_text("dummy", encoding="utf-8")

    res = runner.invoke(app, ["import-rom", str(source_rom), "--platform", "snes"])
    assert res.exit_code == 0
    assert "Sucesso" in res.stdout
    assert "chrono_trigger_special_edition.sfc" in res.stdout

    expected_target = (
        mock_repo_root / "data" / "roms" / "snes" / "chrono_trigger_special_edition.sfc"
    )
    assert expected_target.exists()


def test_cli_import_rom_batch(
    tmp_path: Path, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica a importação em lote via comando CLI import-rom passando um diretório.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest para alteração de diretório de trabalho.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)

    batch_dir = tmp_path / "batch_roms"
    batch_dir.mkdir()
    (batch_dir / "Castlevania 4.sfc").write_text("dummy", encoding="utf-8")
    (batch_dir / "Zelda 3.smc").write_text("dummy", encoding="utf-8")

    res = runner.invoke(app, ["import-rom", str(batch_dir), "--platform", "snes"])
    assert res.exit_code == 0
    assert "Ingestão em Lote" in res.stdout
    assert "castlevania_4.sfc" in res.stdout
    assert "zelda_3.smc" in res.stdout


def test_cli_import_rom_error(
    tmp_path: Path, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica se erro de validação (extensão proibida) encerra com código 1 no CLI.

    Args:
        tmp_path: Diretório temporário.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)

    bad_rom = tmp_path / "game.chd"
    bad_rom.write_text("dummy", encoding="utf-8")

    res = runner.invoke(app, ["import-rom", str(bad_rom), "--platform", "gc"])
    assert res.exit_code == 1
    assert "Erro de Ingestão" in res.stdout


def test_cli_audit_library_alias(mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica se o alias audit-library invoca a auditoria corretamente.

    Args:
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    result = runner.invoke(app, ["audit-library"])
    assert result.exit_code == 0
    assert "Auditoria de Integridade" in result.stdout


def test_cli_bootstrap(
    mocker: MockerFixture, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica se o comando bootstrap despacha para o script PowerShell.

    Args:
        mocker: Fixture do pytest-mock.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    mock_run = mocker.patch("retrogame_lab.cli.run_pwsh_script", return_value=0)

    res = runner.invoke(app, ["bootstrap", "--skip-winget", "--download-emulators"])
    assert res.exit_code == 0
    mock_run.assert_called_once_with("bootstrap.ps1", ["-SkipWinget", "-DownloadEmulators"])


def test_cli_download_emulators(
    mocker: MockerFixture, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica se o comando download-emulators despacha para o script PowerShell.

    Args:
        mocker: Fixture do pytest-mock.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    mock_run = mocker.patch("retrogame_lab.cli.run_pwsh_script", return_value=0)

    res = runner.invoke(app, ["download-emulators", "-e", "pcsx2,duckstation", "--force"])
    assert res.exit_code == 0
    mock_run.assert_called_once_with(
        "download_emulators.ps1", ["-Emulators", "pcsx2,duckstation", "-Force"]
    )


def test_cli_check_updates(
    mocker: MockerFixture, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica se o comando check-updates despacha com a flag -CheckOnly.

    Args:
        mocker: Fixture do pytest-mock.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    mock_run = mocker.patch("retrogame_lab.cli.run_pwsh_script", return_value=0)

    res = runner.invoke(app, ["check-updates"])
    assert res.exit_code == 0
    mock_run.assert_called_once_with("download_emulators.ps1", ["-CheckOnly"])


def test_cli_update_emulators(
    mocker: MockerFixture, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica se o comando update-emulators despacha com a flag -Update.

    Args:
        mocker: Fixture do pytest-mock.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    mock_run = mocker.patch("retrogame_lab.cli.run_pwsh_script", return_value=0)

    res = runner.invoke(app, ["update-emulators", "-e", "pcsx2"])
    assert res.exit_code == 0
    mock_run.assert_called_once_with("download_emulators.ps1", ["-Emulators", "pcsx2", "-Update"])


def test_cli_bootstrap_failure(
    mocker: MockerFixture, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica propagação de código de saída de erro no comando bootstrap.

    Args:
        mocker: Fixture do pytest-mock.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    mocker.patch("retrogame_lab.cli.run_pwsh_script", return_value=42)

    res = runner.invoke(app, ["bootstrap"])
    assert res.exit_code == 42


def test_cli_launch(
    mocker: MockerFixture, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica despacho do comando launch para o script PowerShell.

    Args:
        mocker: Fixture do pytest-mock.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    mock_run = mocker.patch("retrogame_lab.cli.run_pwsh_script", return_value=0)

    rom_file = mock_repo_root / "data" / "roms" / "ps1" / "game.chd"
    rom_file.write_text("dummy", encoding="utf-8")

    res = runner.invoke(app, ["launch", "ps1", str(rom_file), "--windowed", "--gpu-mode", "dgpu"])
    assert res.exit_code == 0
    mock_run.assert_called_once_with(
        "launch.ps1",
        ["-Platform", "ps1", "-RomPath", str(rom_file), "-GpuMode", "dgpu", "-Windowed"],
    )


def test_cli_launch_fullscreen(
    mocker: MockerFixture, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica despacho do comando launch em modo fullscreen padrão.

    Args:
        mocker: Fixture do pytest-mock.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    mock_run = mocker.patch("retrogame_lab.cli.run_pwsh_script", return_value=0)

    rom_file = mock_repo_root / "data" / "roms" / "ps1" / "game.chd"
    rom_file.write_text("dummy", encoding="utf-8")

    res = runner.invoke(app, ["launch", "ps1", str(rom_file)])
    assert res.exit_code == 0
    mock_run.assert_called_once_with(
        "launch.ps1",
        ["-Platform", "ps1", "-RomPath", str(rom_file), "-GpuMode", "auto", "-Fullscreen"],
    )


def test_cli_convert_chd(
    mocker: MockerFixture, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica despacho do comando convert-chd para o script PowerShell.

    Args:
        mocker: Fixture do pytest-mock.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    mock_run = mocker.patch("retrogame_lab.cli.run_pwsh_script", return_value=0)

    source_dir = mock_repo_root / "staging"
    source_dir.mkdir()

    res = runner.invoke(app, ["convert-chd", str(source_dir), "--media-type", "dvd"])
    assert res.exit_code == 0
    mock_run.assert_called_once_with(
        "convert_chd.ps1",
        ["-SourceDirectory", str(source_dir), "-MediaType", "dvd"],
    )


def test_cli_setup_android(
    mocker: MockerFixture, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica despacho do comando setup-android para o script PowerShell.

    Args:
        mocker: Fixture do pytest-mock.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    mock_run = mocker.patch("retrogame_lab.cli.run_pwsh_script", return_value=0)

    res = runner.invoke(
        app,
        ["setup-android", "--device-id", "device123", "--skip-download"],
    )
    assert res.exit_code == 0
    mock_run.assert_called_once_with(
        "setup_android_emulators.ps1",
        [
            "-TargetDevicePath",
            "/storage/emulated/0/RetroGames",
            "-DeviceId",
            "device123",
            "-SkipDownload",
        ],
    )


def test_run_pwsh_script_missing(mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica se FileNotFoundError é levantado quando o script não existe.

    Args:
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    from retrogame_lab.cli import run_pwsh_script

    with pytest.raises(FileNotFoundError, match="Script PowerShell não encontrado"):
        run_pwsh_script("inexistente.ps1", [])


def test_cli_fetch_snes(
    mocker: MockerFixture, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica o acionamento do comando fetch-snes no CLI.

    Args:
        mocker: Fixture do pytest-mock.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    mock_interactive = mocker.patch("retrogame_lab.cli.run_interactive_fetcher")

    res = runner.invoke(app, ["fetch-snes", "--query", "mario"])
    assert res.exit_code == 0
    mock_interactive.assert_called_once()
    _, kwargs = mock_interactive.call_args
    assert kwargs["platform_code"] == "snes"
    assert kwargs["query"] == "mario"


@pytest.mark.parametrize("platform", ["snes", "ps1", "ps2", "psp", "gc", "dc"])
def test_cli_fetch_platform_shortcuts(
    platform: str,
    mocker: MockerFixture,
    mock_repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifica todos os atalhos diretos fetch-<plataforma> no CLI.

    Args:
        platform: Código da plataforma testada.
        mocker: Fixture do pytest-mock.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    mock_fetcher = mocker.patch("retrogame_lab.cli.run_interactive_fetcher")

    res = runner.invoke(app, [f"fetch-{platform}", "--query", "teste", "-i", "custom_id"])
    assert res.exit_code == 0
    mock_fetcher.assert_called_once()
    _, kwargs = mock_fetcher.call_args
    assert kwargs["platform_code"] == platform
    assert kwargs["query"] == "teste"
    assert kwargs["identifier"] == "custom_id"


def test_cli_fetch_roms_generic(
    mocker: MockerFixture, mock_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica o acionamento do comando fetch-roms especificando plataforma.

    Args:
        mocker: Fixture do pytest-mock.
        mock_repo_root: Fixture de raiz mockada.
        monkeypatch: Fixture do pytest.

    Returns:
        None.

    Raises:
        None.
    """
    monkeypatch.chdir(mock_repo_root)
    mock_fetcher = mocker.patch("retrogame_lab.cli.run_interactive_fetcher")

    res = runner.invoke(app, ["fetch-roms", "-p", "ps1", "-q", "crash"])
    assert res.exit_code == 0
    mock_fetcher.assert_called_once()
    _, kwargs = mock_fetcher.call_args
    assert kwargs["platform_code"] == "ps1"
    assert kwargs["query"] == "crash"
