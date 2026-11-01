"""Módulo de ingestão e importação controlada de ROMs no RetroGame Lab.

Implementa a esteira de validação estrutural de formatos, verificação de extensões
permitidas e proibidas por plataforma e higienização automática de nomenclatura
(eliminando espaços e caracteres especiais) no momento da adição de jogos.
"""

import shutil
from pathlib import Path

from retrogame_lab.config import SUPPORTED_PLATFORMS, get_roms_dir
from retrogame_lab.sanitizer import sanitize_filename


def import_rom(
    source_path: Path,
    platform_code: str,
    move: bool = False,
    repo_root: Path | None = None,
) -> Path:
    """Importa uma ROM para a biblioteca canônica, validando extensão e higienizando o nome.

    Verifica a compatibilidade com a plataforma alvo, bloqueia extensões proibidas,
    aplica a higienização de nomenclatura (espaços -> '_', remoção de aspas e especiais)
    e copia ou move o arquivo para 'data/roms/<platform_code>/'.

    Args:
        source_path: Caminho do arquivo de origem a ser importado.
        platform_code: Código da plataforma alvo (ex.: 'snes', 'ps1', 'ps2', 'psp', 'gc', 'dc').
        move: Se True, move o arquivo de origem. Se False, copia preservando o original.
        repo_root: Caminho opcional da raiz do repositório.

    Returns:
        Path absoluto do arquivo importado e sanitizado dentro de data/roms/<platform_code>/.

    Raises:
        FileNotFoundError: Se o arquivo de origem não existir.
        IsADirectoryError: Se source_path apontar para uma pasta em vez de um arquivo.
        ValueError: Se a plataforma for desconhecida ou a extensão for inválida/proibida.
        FileExistsError: Se o arquivo de destino já existir no repositório.
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Arquivo de origem não encontrado: {source_path}")
    if source_path.is_dir():
        raise IsADirectoryError(
            f"O caminho de origem é um diretório, não um arquivo: {source_path}"
        )

    plat_key = platform_code.lower().strip()
    platform = SUPPORTED_PLATFORMS.get(plat_key)
    if not platform:
        valid_keys = ", ".join(SUPPORTED_PLATFORMS.keys())
        raise ValueError(
            f"Plataforma '{platform_code}' não suportada. Opções válidas: {valid_keys}."
        )

    ext = source_path.suffix.lower()

    # 1. Validação estrita de extensões proibidas (ex.: .chd para GameCube)
    if ext in platform.prohibited_extensions:
        raise ValueError(
            f"Extensão '{ext}' é proibida para a plataforma '{platform.name}'. "
            f"Formato canônico homologado: {platform.canonical_format}."
        )

    # 2. Validação estrita de extensões aceitas
    if ext not in platform.accepted_extensions:
        accepted = ", ".join(platform.accepted_extensions)
        raise ValueError(
            f"Extensão '{ext}' não suportada para '{platform.name}'. Extensões aceitas: {accepted}."
        )

    # 3. Higienização mandatória do nome do arquivo
    sanitized_name = sanitize_filename(source_path.name)
    roms_dir = get_roms_dir(repo_root)
    target_dir = roms_dir / plat_key
    target_dir.mkdir(parents=True, exist_ok=True)

    destination_path = target_dir / sanitized_name
    if destination_path.exists() and destination_path.resolve() != source_path.resolve():
        raise FileExistsError(f"O arquivo de destino já existe na biblioteca: {destination_path}")

    # 4. Ingestão física (cópia ou movimentação)
    if move:
        shutil.move(str(source_path), str(destination_path))
    else:
        shutil.copy2(str(source_path), str(destination_path))

    return destination_path


def import_roms_batch(
    source_dir: Path,
    platform_code: str,
    move: bool = False,
    repo_root: Path | None = None,
) -> list[Path]:
    """Importa em lote todos os arquivos compatíveis de um diretório para uma plataforma.

    Args:
        source_dir: Diretório de origem contendo os arquivos a importar.
        platform_code: Código da plataforma alvo.
        move: Se True, move os arquivos. Se False, copia.
        repo_root: Caminho opcional da raiz do repositório.

    Returns:
        Lista de Paths dos arquivos importados com sucesso.

    Raises:
        FileNotFoundError: Se source_dir não existir.
        NotADirectoryError: Se source_dir não for um diretório.
        ValueError: Se platform_code for inválido.
    """
    if not source_dir.exists():
        raise FileNotFoundError(f"Diretório de origem não encontrado: {source_dir}")
    if not source_dir.is_dir():
        raise NotADirectoryError(f"O caminho de origem não é um diretório: {source_dir}")

    plat_key = platform_code.lower().strip()
    platform = SUPPORTED_PLATFORMS.get(plat_key)
    if not platform:
        valid_keys = ", ".join(SUPPORTED_PLATFORMS.keys())
        raise ValueError(
            f"Plataforma '{platform_code}' não suportada. Opções válidas: {valid_keys}."
        )

    imported: list[Path] = []
    for file_path in sorted(source_dir.iterdir()):
        if not file_path.is_file():
            continue
        ext = file_path.suffix.lower()
        if ext in platform.accepted_extensions and ext not in platform.prohibited_extensions:
            dest = import_rom(file_path, plat_key, move=move, repo_root=repo_root)
            imported.append(dest)

    return imported
