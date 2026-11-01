"""Módulo de sanitização e padronização de nomenclatura de ROMs e saves.

Garante conformidade com o padrão estrito de arquivos sem espaços (substituindo
por sublinhado '_') e sem caracteres especiais (aspas simples, duplas, crases).
"""

import re
from pathlib import Path


def sanitize_filename(filename: str) -> str:
    """Higieniza o nome de um arquivo substituindo espaços por '_' e removendo caracteres especiais.

    Remove aspas simples ('), duplas ("), crases (`), sinais de pontuação conflitantes
    (!, ?, :, ;, *, <, >, |, #) e converte sequências de espaços em sublinhado único.
    Preserva a extensão original do arquivo.

    Args:
        filename: Nome original do arquivo (com extensão).

    Returns:
        Nome do arquivo higienizado, sem espaços e sem caracteres especiais.

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
            matched_ext = filename[-len(comp) :]
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

    # 1. Remove aspas simples, duplas, crases e caracteres especiais inválidos
    stem = re.sub(r"['\"`\~\^\!\?\:\;\*\<\>\|\#]", "", stem)

    # 2. Converte qualquer sequência de espaços em '_'
    stem = re.sub(r"\s+", "_", stem)

    # 3. Colapsa múltiplos sublinhados consecutivos em um único
    stem = re.sub(r"_+", "_", stem)

    # 4. Remove sublinhados residuais nas pontas
    stem = stem.strip("_")

    if not stem:
        stem = "unnamed"

    return f"{stem}{matched_ext}"


def sanitize_path(file_path: Path) -> Path:
    """Calcula o novo caminho de um arquivo aplicando a higienização em seu nome.

    Args:
        file_path: Objeto Path do arquivo a ser sanitizado.

    Returns:
        Novo objeto Path com o nome do arquivo higienizado.

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
    # Ordena com arquivos mais profundos primeiro para segurança
    all_files = sorted(
        [f for f in target_dir.rglob("*") if f.is_file()],
        key=lambda p: len(p.parts),
        reverse=True,
    )

    for file_path in all_files:
        sanitized_name = sanitize_filename(file_path.name)
        if file_path.name != sanitized_name:
            new_path = file_path.with_name(sanitized_name)
            changes.append((file_path, new_path))
            if not dry_run:
                file_path.rename(new_path)

    return changes
