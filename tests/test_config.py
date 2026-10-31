"""Testes unitários para o módulo config do RetroGame Lab.

Valida a localização da raiz do projeto, cálculo de diretórios canônicos
e definições das plataformas suportadas.
"""

from pathlib import Path

import pytest

from retrogame_lab.config import (
    SUPPORTED_PLATFORMS,
    find_repo_root,
    get_bin_dir,
    get_bios_dir,
    get_data_dir,
    get_roms_dir,
    get_saves_dir,
    get_tools_dir,
)


def test_find_repo_root_success(mock_repo_root: Path) -> None:
    """Verifica se find_repo_root localiza a raiz simulada com marcadores presentes.

    Args:
        mock_repo_root: Fixture com a raiz do repositório mockado.

    Returns:
        None.

    Raises:
        None.
    """
    sub_dir = mock_repo_root / "data" / "roms" / "ps1"
    detected = find_repo_root(sub_dir)
    assert detected == mock_repo_root


def test_find_repo_root_failure(tmp_path: Path) -> None:
    """Verifica se find_repo_root levanta FileNotFoundError quando não há marcadores.

    Args:
        tmp_path: Diretório temporário vazio.

    Returns:
        None.

    Raises:
        None.
    """
    isolated_dir = tmp_path / "isolated"
    isolated_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="Não foi possível localizar a raiz"):
        find_repo_root(isolated_dir)


def test_get_directory_paths(mock_repo_root: Path) -> None:
    """Verifica a correta resolução de caminhos das pastas de dados e binários.

    Args:
        mock_repo_root: Fixture com a raiz do repositório mockado.

    Returns:
        None.

    Raises:
        None.
    """
    assert get_data_dir(mock_repo_root) == mock_repo_root / "data"
    assert get_bios_dir(mock_repo_root) == mock_repo_root / "data" / "bios"
    assert get_roms_dir(mock_repo_root) == mock_repo_root / "data" / "roms"
    assert get_saves_dir(mock_repo_root) == mock_repo_root / "data" / "saves"
    assert get_bin_dir(mock_repo_root) == mock_repo_root / "bin"
    assert get_tools_dir(mock_repo_root) == mock_repo_root / "tools"


def test_supported_platforms_metadata() -> None:
    """Verifica se todas as plataformas homologadas estão configuradas e íntegras.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    expected_codes = {"snes", "ps1", "ps2", "psp", "gc", "dc"}
    assert set(SUPPORTED_PLATFORMS.keys()) == expected_codes

    for code, info in SUPPORTED_PLATFORMS.items():
        assert info.code == code
        assert len(info.name) > 0
        assert info.canonical_format.startswith(".")
        assert len(info.accepted_extensions) > 0
        assert len(info.emulator_name) > 0
