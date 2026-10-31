"""Configuração global de fixtures para a suíte de testes com Pytest.

Fornece estruturas de diretórios simuladas para validação de BIOS, ROMs e saves.
"""

from pathlib import Path

import pytest


@pytest.fixture
def mock_repo_root(tmp_path: Path) -> Path:
    """Cria uma estrutura representativa do repositório para testes unitários.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        Path para a raiz do repositório simulado.

    Raises:
        None.
    """
    # Marcadores da raiz
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Test\n", encoding="utf-8")

    # Pastas de dados
    bios_dir = tmp_path / "data" / "bios"
    roms_dir = tmp_path / "data" / "roms"
    saves_dir = tmp_path / "data" / "saves"

    for d in [
        bios_dir / "ps1",
        bios_dir / "ps2",
        bios_dir / "dc",
        roms_dir / "snes",
        roms_dir / "ps1",
        roms_dir / "ps2",
        roms_dir / "psp",
        roms_dir / "gc",
        roms_dir / "dc",
        saves_dir / "snes",
        saves_dir / "ps1",
        saves_dir / "ps2",
        saves_dir / "psp",
        saves_dir / "gc",
        saves_dir / "dc",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    return tmp_path
