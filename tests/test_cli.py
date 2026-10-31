"""Testes unitários para a CLI do RetroGame Lab.

Valida subcomandos version, info e audit, incluindo relatórios em console e JSON.
"""

import json
from pathlib import Path

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
