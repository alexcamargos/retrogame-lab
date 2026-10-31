"""Módulo de configuração e resolução de diretórios do RetroGame Lab.

Define caminhos canônicos da arquitetura, metadados de plataformas
suportadas, extensões válidas e diretrizes de salvamento.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformInfo:
    """Informações estruturais e regras de integridade de uma plataforma.

    Attributes:
        code: Identificador único em minúsculas (ex.: 'ps1', 'ps2').
        name: Nome legível da plataforma (ex.: 'PlayStation 1').
        canonical_format: Formato de compressão homologado (ex.: '.chd', '.rvz').
        accepted_extensions: Tupla de extensões válidas no repositório.
        prohibited_extensions: Tupla de extensões proibidas ou que exigem conversão.
        save_format_desc: Descrição da estratégia de salvamento compatível.
        emulator_name: Nome do emulador padrão de referência.
    """

    code: str
    name: str
    canonical_format: str
    accepted_extensions: tuple[str, ...]
    prohibited_extensions: tuple[str, ...]
    save_format_desc: str
    emulator_name: str


SUPPORTED_PLATFORMS: dict[str, PlatformInfo] = {
    "snes": PlatformInfo(
        code="snes",
        name="Super Nintendo Entertainment System",
        canonical_format=".sfc",
        accepted_extensions=(".sfc", ".smc", ".zip"),
        prohibited_extensions=(".state", ".s01"),
        save_format_desc="Arquivo .srm idêntico ao nome da ROM",
        emulator_name="RetroArch (Snes9x)",
    ),
    "ps1": PlatformInfo(
        code="ps1",
        name="Sony PlayStation 1",
        canonical_format=".chd",
        accepted_extensions=(".chd",),
        prohibited_extensions=(".cue", ".bin", ".iso", ".img"),
        save_format_desc="Cartão individual por jogo (.mcd)",
        emulator_name="DuckStation",
    ),
    "ps2": PlatformInfo(
        code="ps2",
        name="Sony PlayStation 2",
        canonical_format=".chd",
        accepted_extensions=(".chd", ".iso"),
        prohibited_extensions=(".cue", ".bin"),
        save_format_desc="Cartão individual por jogo (.ps2) ou Folder Memory Card",
        emulator_name="PCSX2",
    ),
    "psp": PlatformInfo(
        code="psp",
        name="Sony PlayStation Portable",
        canonical_format=".cso",
        accepted_extensions=(".cso", ".chd", ".iso"),
        prohibited_extensions=(),
        save_format_desc="Pastas nativas SAVEDATA",
        emulator_name="PPSSPP",
    ),
    "gc": PlatformInfo(
        code="gc",
        name="Nintendo GameCube",
        canonical_format=".rvz",
        accepted_extensions=(".rvz",),
        prohibited_extensions=(".chd", ".iso", ".gcm"),
        save_format_desc="Cartões GCI / Pastas de Região em gc/",
        emulator_name="Dolphin",
    ),
    "dc": PlatformInfo(
        code="dc",
        name="Sega Dreamcast",
        canonical_format=".chd",
        accepted_extensions=(".chd",),
        prohibited_extensions=(".cdi", ".gdi", ".cue", ".bin"),
        save_format_desc="Arquivo de VMU padrão (vms0.bin)",
        emulator_name="Flycast",
    ),
}


def find_repo_root(start_path: Path | None = None) -> Path:
    """Localiza a raiz do repositório retrogame-lab a partir de marcadores canônicos.

    Navega recursivamente para os diretórios pais procurando os arquivos
    'pyproject.toml' ou 'AGENTS.md'.

    Args:
        start_path: Caminho inicial para a busca. Se None, utiliza o diretório atual.

    Returns:
        Path para o diretório raiz identificado.

    Raises:
        FileNotFoundError: Se nenhum marcador de raiz for localizado nos ancestrais.
    """
    current = (start_path or Path.cwd()).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "pyproject.toml").is_file() and (parent / "AGENTS.md").is_file():
            return parent
        if (parent / ".git").is_dir():
            return parent

    raise FileNotFoundError(
        f"Não foi possível localizar a raiz do repositório a partir de '{current}'."
    )


def get_data_dir(repo_root: Path | None = None) -> Path:
    """Retorna o caminho canônico do diretório 'data/'.

    Args:
        repo_root: Raiz do repositório. Se None, é resolvida automaticamente.

    Returns:
        Path absoluto para o diretório de dados.

    Raises:
        FileNotFoundError: Se a raiz do repositório não for encontrada.
    """
    root = repo_root or find_repo_root()
    return root / "data"


def get_bios_dir(repo_root: Path | None = None) -> Path:
    """Retorna o caminho canônico do diretório de firmwares 'data/bios/'.

    Args:
        repo_root: Raiz do repositório. Se None, é resolvida automaticamente.

    Returns:
        Path absoluto para o diretório de BIOS.

    Raises:
        FileNotFoundError: Se a raiz do repositório não for encontrada.
    """
    return get_data_dir(repo_root) / "bios"


def get_roms_dir(repo_root: Path | None = None) -> Path:
    """Retorna o caminho canônico do diretório de ROMs 'data/roms/'.

    Args:
        repo_root: Raiz do repositório. Se None, é resolvida automaticamente.

    Returns:
        Path absoluto para o diretório de ROMs.

    Raises:
        FileNotFoundError: Se a raiz do repositório não for encontrada.
    """
    return get_data_dir(repo_root) / "roms"


def get_saves_dir(repo_root: Path | None = None) -> Path:
    """Retorna o caminho canônico do diretório de saves 'data/saves/'.

    Args:
        repo_root: Raiz do repositório. Se None, é resolvida automaticamente.

    Returns:
        Path absoluto para o diretório de saves.

    Raises:
        FileNotFoundError: Se a raiz do repositório não for encontrada.
    """
    return get_data_dir(repo_root) / "saves"


def get_bin_dir(repo_root: Path | None = None) -> Path:
    """Retorna o caminho canônico do diretório de emuladores 'bin/'.

    Args:
        repo_root: Raiz do repositório. Se None, é resolvida automaticamente.

    Returns:
        Path absoluto para o diretório bin.

    Raises:
        FileNotFoundError: Se a raiz do repositório não for encontrada.
    """
    root = repo_root or find_repo_root()
    return root / "bin"


def get_tools_dir(repo_root: Path | None = None) -> Path:
    """Retorna o caminho canônico do diretório de utilitários 'tools/'.

    Args:
        repo_root: Raiz do repositório. Se None, é resolvida automaticamente.

    Returns:
        Path absoluto para o diretório tools.

    Raises:
        FileNotFoundError: Se a raiz do repositório não for encontrada.
    """
    root = repo_root or find_repo_root()
    return root / "tools"
