"""Testes unitários para o módulo de sanitização de nomenclatura de ROMs e saves.

Valida a conversão de espaços em sublinhados '_', remoção de aspas e caracteres
especiais, e operações recursivas de renomeação em diretórios.
"""

from pathlib import Path

import pytest

from retrogame_lab.sanitizer import (
    sanitize_directory,
    sanitize_filename,
    sanitize_path,
)


def test_sanitize_filename_spaces_and_quotes() -> None:
    """Verifica a substituição de espaços por '_' e remoção de aspas simples, duplas e crases.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    assert sanitize_filename("Super Mario World (USA).sfc") == "Super_Mario_World_(USA).sfc"
    assert sanitize_filename("Tony Hawk's Pro Skater 2.chd") == "Tony_Hawks_Pro_Skater_2.chd"
    assert sanitize_filename('Sonic\'s "Special" `Edition`!.iso') == "Sonics_Special_Edition.iso"


def test_sanitize_filename_collapse_and_trim_underscores() -> None:
    """Verifica se múltiplos sublinhados são colapsados e extremidades são podadas.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    assert sanitize_filename("___Game___Title___.chd") == "Game_Title.chd"
    assert sanitize_filename("  Final   Fantasy   VII  .chd") == "Final_Fantasy_VII.chd"


def test_sanitize_filename_compound_extension() -> None:
    """Verifica a preservação correta de extensões compostas (.nvram.bak).

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    assert sanitize_filename("Legend of Zelda Save.nvram.bak") == "Legend_of_Zelda_Save.nvram.bak"


def test_sanitize_filename_empty_raises_error() -> None:
    """Verifica se string vazia levanta ValueError.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    with pytest.raises(ValueError, match="não pode ser vazio"):
        sanitize_filename("")


def test_sanitize_path() -> None:
    """Verifica a higienização de um objeto Path completo.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    original = Path("data/roms/ps1/Final Fantasy VII (Disc 1).chd")
    sanitized = sanitize_path(original)
    assert sanitized.name == "Final_Fantasy_VII_(Disc_1).chd"
    assert sanitized.parent == original.parent


def test_sanitize_directory_dry_run_and_apply(tmp_path: Path) -> None:
    """Verifica o comportamento de simulação (dry_run) vs aplicação real em diretório.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None.

    Raises:
        None.
    """
    subdir = tmp_path / "ps1"
    subdir.mkdir()

    file1 = subdir / "Final Fantasy VII (Disc 1).chd"
    file1.write_text("dummy", encoding="utf-8")

    file2 = subdir / "Castlevania - Symphony of the Night.chd"
    file2.write_text("dummy", encoding="utf-8")

    file_clean = subdir / "Clean_Game.chd"
    file_clean.write_text("dummy", encoding="utf-8")

    # 1. Modo Simulação (dry_run=True)
    changes_sim = sanitize_directory(tmp_path, dry_run=True)
    assert len(changes_sim) == 2
    assert file1.exists()
    assert file2.exists()

    # 2. Modo Real (dry_run=False)
    changes_real = sanitize_directory(tmp_path, dry_run=False)
    assert len(changes_real) == 2
    assert not file1.exists()
    assert not file2.exists()
    assert (subdir / "Final_Fantasy_VII_(Disc_1).chd").exists()
    assert (subdir / "Castlevania_-_Symphony_of_the_Night.chd").exists()
    assert file_clean.exists()


def test_sanitize_directory_invalid_path(tmp_path: Path) -> None:
    """Verifica exceções para caminhos inexistentes ou que não sejam pastas.

    Args:
        tmp_path: Diretório temporário.

    Returns:
        None.

    Raises:
        None.
    """
    with pytest.raises(FileNotFoundError, match="não encontrado"):
        sanitize_directory(tmp_path / "non_existent")

    regular_file = tmp_path / "file.txt"
    regular_file.write_text("hello", encoding="utf-8")
    with pytest.raises(NotADirectoryError, match="não é um diretório"):
        sanitize_directory(regular_file)
