"""Testes unitários para o módulo de ingestão e importação de ROMs.

Valida a cópia/movimentação, verificação de extensões aceitas e proibidas,
higienização de nomes no ato da importação e processamento em lote.
"""

from pathlib import Path

import pytest

from retrogame_lab.ingestion import import_rom, import_roms_batch


def test_import_rom_single_copy(tmp_path: Path, mock_repo_root: Path) -> None:
    """Verifica a importação de uma ROM individual no modo cópia (padrão).

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.
        mock_repo_root: Fixture de raiz mockada do repositório.

    Returns:
        None.

    Raises:
        None.
    """
    source_file = tmp_path / "Super Mario World (USA).sfc"
    source_file.write_text("dummy", encoding="utf-8")

    dest = import_rom(source_file, "snes", move=False, repo_root=mock_repo_root)

    assert dest.exists()
    assert dest.name == "Super_Mario_World_(USA).sfc"
    assert dest.parent == mock_repo_root / "data" / "roms" / "snes"
    assert source_file.exists()  # Preservado no modo cópia


def test_import_rom_single_move(tmp_path: Path, mock_repo_root: Path) -> None:
    """Verifica a importação de uma ROM individual no modo movimentação (move=True).

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.
        mock_repo_root: Fixture de raiz mockada do repositório.

    Returns:
        None.

    Raises:
        None.
    """
    source_file = tmp_path / "Tony Hawk's Pro Skater 2.chd"
    source_file.write_text("dummy", encoding="utf-8")

    dest = import_rom(source_file, "ps1", move=True, repo_root=mock_repo_root)

    assert dest.exists()
    assert dest.name == "Tony_Hawks_Pro_Skater_2.chd"
    assert not source_file.exists()  # Movido com sucesso


def test_import_rom_prohibited_extension(tmp_path: Path, mock_repo_root: Path) -> None:
    """Verifica se extensões proibidas para a plataforma levantam ValueError.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.
        mock_repo_root: Fixture de raiz mockada do repositório.

    Returns:
        None.

    Raises:
        None.
    """
    # .chd é proibido no GameCube (exige .rvz)
    bad_gc = tmp_path / "smash_melee.chd"
    bad_gc.write_text("dummy", encoding="utf-8")

    with pytest.raises(ValueError, match="é proibida para a plataforma"):
        import_rom(bad_gc, "gc", repo_root=mock_repo_root)


def test_import_rom_unsupported_extension(tmp_path: Path, mock_repo_root: Path) -> None:
    """Verifica se extensão não catalogada levanta ValueError.

    Args:
        tmp_path: Diretório temporário.
        mock_repo_root: Fixture de raiz mockada.

    Returns:
        None.

    Raises:
        None.
    """
    bad_ext = tmp_path / "game.txt"
    bad_ext.write_text("dummy", encoding="utf-8")

    with pytest.raises(ValueError, match="não suportada"):
        import_rom(bad_ext, "snes", repo_root=mock_repo_root)


def test_import_rom_invalid_platform(tmp_path: Path, mock_repo_root: Path) -> None:
    """Verifica se código de plataforma inválido levanta ValueError.

    Args:
        tmp_path: Diretório temporário.
        mock_repo_root: Fixture de raiz mockada.

    Returns:
        None.

    Raises:
        None.
    """
    sample = tmp_path / "game.sfc"
    sample.write_text("dummy", encoding="utf-8")

    with pytest.raises(ValueError, match="não suportada"):
        import_rom(sample, "invalid_platform", repo_root=mock_repo_root)


def test_import_rom_missing_file_raises_error(mock_repo_root: Path) -> None:
    """Verifica se arquivo inexistente levanta FileNotFoundError.

    Args:
        mock_repo_root: Fixture de raiz mockada.

    Returns:
        None.

    Raises:
        None.
    """
    missing = Path("missing_game.sfc")
    with pytest.raises(FileNotFoundError, match="não encontrado"):
        import_rom(missing, "snes", repo_root=mock_repo_root)


def test_import_rom_directory_as_source_raises_error(tmp_path: Path, mock_repo_root: Path) -> None:
    """Verifica se passar pasta para import_rom levanta IsADirectoryError.

    Args:
        tmp_path: Diretório temporário.
        mock_repo_root: Fixture de raiz mockada.

    Returns:
        None.

    Raises:
        None.
    """
    folder = tmp_path / "my_games"
    folder.mkdir()

    with pytest.raises(IsADirectoryError, match="é um diretório"):
        import_rom(folder, "snes", repo_root=mock_repo_root)


def test_import_rom_target_already_exists(tmp_path: Path, mock_repo_root: Path) -> None:
    """Verifica se destino já existente levanta FileExistsError.

    Args:
        tmp_path: Diretório temporário.
        mock_repo_root: Fixture de raiz mockada.

    Returns:
        None.

    Raises:
        None.
    """
    target = mock_repo_root / "data" / "roms" / "snes" / "game.sfc"
    target.write_text("existing", encoding="utf-8")

    source = tmp_path / "game.sfc"
    source.write_text("new", encoding="utf-8")

    with pytest.raises(FileExistsError, match="já existe"):
        import_rom(source, "snes", repo_root=mock_repo_root)


def test_import_roms_batch(tmp_path: Path, mock_repo_root: Path) -> None:
    """Verifica a importação em lote filtrando apenas arquivos compatíveis.

    Args:
        tmp_path: Diretório temporário.
        mock_repo_root: Fixture de raiz mockada.

    Returns:
        None.

    Raises:
        None.
    """
    batch_dir = tmp_path / "batch_downloads"
    batch_dir.mkdir()

    (batch_dir / "Chrono Trigger.sfc").write_text("dummy", encoding="utf-8")
    (batch_dir / "Super Metroid.smc").write_text("dummy", encoding="utf-8")
    (batch_dir / "readme.txt").write_text("ignored", encoding="utf-8")

    imported = import_roms_batch(batch_dir, "snes", move=False, repo_root=mock_repo_root)

    assert len(imported) == 2
    assert (mock_repo_root / "data" / "roms" / "snes" / "Chrono_Trigger.sfc").exists()
    assert (mock_repo_root / "data" / "roms" / "snes" / "Super_Metroid.smc").exists()
    assert not (mock_repo_root / "data" / "roms" / "snes" / "readme.txt").exists()
