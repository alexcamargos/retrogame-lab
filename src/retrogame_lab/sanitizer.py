"""Módulo de sanitização e padronização de nomenclatura de ROMs e saves.

Garante conformidade com o padrão estrito de arquivos sem espaços (substituindo
por sublinhado '_'), sem caracteres especiais (aspas simples, duplas, crases)
e com caracteres totalmente convertidos para letras minúsculas.
"""

import os
import re
import warnings
from pathlib import Path

from retrogame_lab.config import INVALID_FILENAME_CHARS_PATTERN


def sanitize_filename(filename: str) -> str:
    """Higieniza o nome de um arquivo substituindo espaços por '_' e convertendo para minúsculas.

    Remove aspas simples ('), duplas ("), crases (`), sinais de pontuação conflitantes
    (!, ?, :, ;, *, <, >, |, #), converte todas as letras para minúsculas e normaliza
    sequências de espaços em sublinhado único. Preserva a extensão original do arquivo
    (também convertida para minúsculas).

    Args:
        filename: Nome original do arquivo (com extensão).

    Returns:
        Nome do arquivo higienizado, sem espaços, sem caracteres especiais e em minúsculas.

    Raises:
        ValueError: Se a string fornecida for vazia.
    """
    if not filename:
        raise ValueError("O nome do arquivo não pode ser vazio.")

    # Tratamento especial para extensões compostas conhecidas
    compound_exts = [".nvram.bak", ".sync-conflict"]
    matched_ext = ""
    stem = filename

    for comp in compound_exts:
        if filename.lower().endswith(comp):
            matched_ext = comp
            stem = filename[: -len(comp)]
            break

    if not matched_ext:
        if "." in filename:
            parts = filename.rsplit(".", 1)
            stem = parts[0]
            matched_ext = "." + parts[1]
        else:
            stem = filename
            matched_ext = ""

    # 1. Converte stem e extensão para letras minúsculas
    stem = stem.lower()
    matched_ext = matched_ext.lower()

    # 2. Converte qualquer sequência de espaços em '_'
    stem = re.sub(r"\s+", "_", stem)

    # 3. Remove aspas simples, duplas, crases e caracteres especiais inválidos
    stem = re.sub(INVALID_FILENAME_CHARS_PATTERN, "", stem)

    # 4. Colapsa múltiplos sublinhados consecutivos em um único
    stem = re.sub(r"_+", "_", stem)

    # 5. Remove sublinhados residuais nas pontas
    stem = stem.strip("_")

    if not stem:
        stem = "unnamed"

    return f"{stem}{matched_ext}"


def sanitize_path(file_path: Path) -> Path:
    """Calcula o novo caminho de um arquivo aplicando a higienização em seu nome.

    Args:
        file_path: Objeto Path do arquivo a ser sanitizado.

    Returns:
        Novo objeto Path com o nome do arquivo higienizado em minúsculas.

    Raises:
        None.
    """
    new_name = sanitize_filename(file_path.name)
    return file_path.with_name(new_name)


def sanitize_directory(target_dir: Path, dry_run: bool = True) -> list[tuple[Path, Path]]:
    """Varre um diretório recursivamente e renomeia arquivos fora do padrão sanitizado.

    Args:
        target_dir: Diretório raiz para a busca de arquivos a higienizar.
        dry_run: Se True, apenas simula as alterações sem renomear fisicamente.

    Returns:
        Lista de tuplas (caminho_antigo, novo_caminho) para cada arquivo alterado.

    Raises:
        FileNotFoundError: Se o diretório alvo não existir.
        NotADirectoryError: Se o caminho não apontar para um diretório.
    """
    if not target_dir.exists():
        raise FileNotFoundError(f"Diretório não encontrado: {target_dir}")
    if not target_dir.is_dir():
        raise NotADirectoryError(f"O caminho especificado não é um diretório: {target_dir}")

    changes: list[tuple[Path, Path]] = []
    # Saves nativos e metadados têm nomes definidos pelo jogo ou pelo Syncthing.
    # Mídias com descritores são unidades compostas e não podem ser renomeadas isoladamente.
    all_files = sorted(
        [f for f in target_dir.rglob("*") if f.is_file()],
        key=lambda p: len(p.parts),
        reverse=True,
    )

    for file_path in all_files:
        relative = file_path.relative_to(target_dir)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if "saves" in (part.lower() for part in file_path.parts):
            continue
        if file_path.suffix.lower() in {".cue", ".gdi", ".bin"}:
            if file_path.name != sanitize_filename(file_path.name):
                warnings.warn(
                    f"Mídia composta preservada; converta antes de renomear: {file_path}",
                    stacklevel=2,
                )
            continue
        sanitized_name = sanitize_filename(file_path.name)
        if file_path.name != sanitized_name:
            new_path = file_path.with_name(sanitized_name)
            # Não desvincular um save que usa o nome original da ROM.
            parts_lower = [part.lower() for part in file_path.parts]
            if "roms" in parts_lower:
                idx = parts_lower.index("roms")
                if idx + 1 < len(file_path.parts):
                    platform = file_path.parts[idx + 1].lower()
                    saves = Path(*file_path.parts[:idx]) / "saves" / platform
                    save_files = (
                        (p for p in saves.rglob("*") if p.is_file()) if saves.is_dir() else ()
                    )
                    # Algumas plataformas usam IDs internos, não o nome da ROM.
                    if any(
                        platform not in {"snes", "n64"}
                        or p.stem.casefold() == file_path.stem.casefold()
                        for p in save_files
                    ):
                        warnings.warn(
                            f"ROM preservada: existe save associado a {file_path.name}",
                            stacklevel=2,
                        )
                        continue
            is_case_only = file_path.name.lower() == sanitized_name.lower()
            if new_path.exists() and not is_case_only:
                warnings.warn(
                    f"Colisão ao sanitizar {file_path}: {new_path} já existe", stacklevel=2
                )
                continue
            changes.append((file_path, new_path))
    # Detecta também colisões entre dois arquivos ainda não renomeados.
    destinations: dict[str, list[Path]] = {}
    for old_path, new_path in changes:
        destinations.setdefault(str(new_path).casefold(), []).append(old_path)
    collisions = {key for key, sources in destinations.items() if len(sources) > 1}
    if collisions:
        for key in sorted(collisions):
            warnings.warn(f"Colisão entre arquivos para o destino {key}", stacklevel=2)
        changes = [(old, new) for old, new in changes if str(new).casefold() not in collisions]

    if not dry_run:
        for file_path, new_path in changes:
            try:
                file_path.rename(new_path)
            except OSError:
                if file_path.name.casefold() != new_path.name.casefold():
                    raise
                # Em filesystems que colidem no case-only, usa passo intermediário reversível.
                temp_path = file_path.with_name(f"{file_path.name}.tmp_{os.getpid()}")
                if temp_path.exists():
                    raise FileExistsError(f"Arquivo temporário já existe: {temp_path}") from None
                file_path.rename(temp_path)
                try:
                    temp_path.rename(new_path)
                except OSError:
                    temp_path.rename(file_path)
                    raise

    return changes
