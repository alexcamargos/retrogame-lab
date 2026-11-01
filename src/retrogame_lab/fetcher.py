"""Módulo de busca, download e ingestão de ROMs a partir de acervos de preservação digital.

Permite consultar catálogos remotos (como acervos No-Intro e Redump no Internet Archive)
para todas as plataformas homologadas (SNES, PS1, PS2, PSP, GC, DC), filtrar títulos
interativamente, realizar o download para a área volátil (scratch/) e iniciar
automaticamente o pipeline de ingestão e higienização canônica do RetroGame Lab.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Prompt
from rich.table import Table

from retrogame_lab.config import SUPPORTED_PLATFORMS, find_repo_root
from retrogame_lab.ingestion import import_rom

USER_AGENT = "RetroGameLab-Fetcher/1.0 (Digital Preservation Tool)"
DEFAULT_CACHE_TTL_HOURS = 24


@dataclass(frozen=True)
class PlatformArchiveConfig:
    """Configuração de fontes de preservação digital para uma plataforma.

    Attributes:
        platform_code: Código interno da plataforma (ex.: 'snes', 'ps1').
        default_identifier: Identificador padrão da coleção no Internet Archive.
        accepted_extensions: Extensões de arquivos no acervo que representam mídias válidas.
        description: Descrição legível da iniciativa de preservação de referência.
    """

    platform_code: str
    default_identifier: str
    accepted_extensions: tuple[str, ...]
    description: str


# Catálogo de coleções canônicas de preservação (No-Intro e Redump) por plataforma
PLATFORM_ARCHIVE_CONFIGS: dict[str, PlatformArchiveConfig] = {
    "snes": PlatformArchiveConfig(
        platform_code="snes",
        default_identifier="nointro-snes",
        accepted_extensions=(".sfc", ".smc", ".zip"),
        description="No-Intro Super Nintendo Entertainment System",
    ),
    "ps1": PlatformArchiveConfig(
        platform_code="ps1",
        default_identifier="ps1-psx-roms",
        accepted_extensions=(".chd", ".zip"),
        description="Redump Sony PlayStation 1 (CHD Collection)",
    ),
    "ps2": PlatformArchiveConfig(
        platform_code="ps2",
        default_identifier="sony-playstation-2-j-redump-collection",
        accepted_extensions=(".chd", ".iso", ".zip"),
        description="Redump Sony PlayStation 2 (CHD/ISO Collection)",
    ),
    "psp": PlatformArchiveConfig(
        platform_code="psp",
        default_identifier="sony-playstation-portable-redump",
        accepted_extensions=(".cso", ".chd", ".iso", ".zip"),
        description="Redump Sony PlayStation Portable (ISO/CSO/CHD Collection)",
    ),
    "gc": PlatformArchiveConfig(
        platform_code="gc",
        default_identifier="first-party-dolphin-rvz",
        accepted_extensions=(".rvz", ".zip"),
        description="Redump Nintendo GameCube (RVZ Collection)",
    ),
    "dc": PlatformArchiveConfig(
        platform_code="dc",
        default_identifier="karous-eng",
        accepted_extensions=(".chd", ".zip"),
        description="Redump Sega Dreamcast 1G1R (CHD Collection)",
    ),
}


@dataclass
class ArchiveRomEntry:
    """Representa um item de ROM disponível no catálogo de preservação.

    Attributes:
        filename: Nome exato do arquivo no acervo (ex.: 'Super Mario World (USA).zip').
        title: Nome limpo para exibição (sem extensão de arquivo).
        size_bytes: Tamanho do arquivo em bytes.
        download_url: URL direta para download do arquivo.
    """

    filename: str
    title: str
    size_bytes: int
    download_url: str


def get_archive_catalog(
    identifier: str = "nointro-snes",
    platform_code: str = "snes",
    repo_root: Path | None = None,
    force_refresh: bool = False,
) -> list[ArchiveRomEntry]:
    """Consulta os metadados de arquivos de uma coleção do Internet Archive com cache local.

    Armazena a lista de arquivos em 'scratch/cache_<identifier>_files.json' para evitar
    requisições repetitivas de rede durante buscas interativas.

    Args:
        identifier: Identificador da coleção no Internet Archive.
        platform_code: Código da plataforma para validar extensões aceitas.
        repo_root: Caminho raiz opcional do repositório.
        force_refresh: Se True, ignora o cache local e faz nova requisição remota.

    Returns:
        Lista de objetos ArchiveRomEntry com os títulos compatíveis encontrados.

    Raises:
        ValueError: Se a plataforma informada for desconhecida.
        RuntimeError: Se houver falha de comunicação com a API remota e não houver cache.
    """
    plat_key = platform_code.lower().strip()
    if plat_key not in SUPPORTED_PLATFORMS:
        valid = ", ".join(SUPPORTED_PLATFORMS.keys())
        raise ValueError(f"Plataforma '{platform_code}' desconhecida. Opções: {valid}.")

    root = repo_root or find_repo_root()
    cache_dir = root / "scratch"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"cache_{identifier}_files.json"

    files_data: list[dict[str, Any]] = []

    if not force_refresh and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if isinstance(cached, list) and cached:
                    files_data = cached
        except (json.JSONDecodeError, OSError):
            files_data = []

    if not files_data:
        metadata_url = f"https://archive.org/metadata/{identifier}/files"
        req = urllib.request.Request(metadata_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result = data.get("result", [])
                if isinstance(result, list):
                    files_data = result
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(files_data, f, ensure_ascii=False)
        except Exception as err:
            raise RuntimeError(
                f"Falha ao consultar catálogo remoto do Internet Archive ({identifier}): {err}"
            ) from err

    entries: list[ArchiveRomEntry] = []
    base_download_url = f"https://archive.org/download/{identifier}"

    # Extensões válidas para esta plataforma
    config = PLATFORM_ARCHIVE_CONFIGS.get(plat_key)
    valid_extensions = (
        config.accepted_extensions
        if config
        else (".zip", ".chd", ".iso", ".cso", ".rvz", ".sfc", ".smc")
    )

    for item in files_data:
        name = item.get("name", "")
        if not name.lower().endswith(valid_extensions):
            continue
        if name.startswith((".", "_")) or "xml" in name.lower() or "sqlite" in name.lower():
            continue

        size = int(item.get("size", 0)) if str(item.get("size", "0")).isdigit() else 0
        clean_title = re.sub(
            r"\.(zip|sfc|smc|chd|iso|cso|rvz|7z)$", "", name, flags=re.IGNORECASE
        )
        encoded_name = urllib.parse.quote(name)
        download_url = f"{base_download_url}/{encoded_name}"

        entries.append(
            ArchiveRomEntry(
                filename=name,
                title=clean_title,
                size_bytes=size,
                download_url=download_url,
            )
        )

    entries.sort(key=lambda x: x.title.lower())
    return entries


def search_catalog(
    catalog: list[ArchiveRomEntry],
    query: str = "",
    limit: int = 50,
) -> list[ArchiveRomEntry]:
    """Filtra títulos do catálogo a partir de termos de busca.

    Args:
        catalog: Lista de entradas do catálogo de ROMs.
        query: Termo ou termos de pesquisa (insensível a maiúsculas/minúsculas).
        limit: Quantidade máxima de resultados a retornar.

    Returns:
        Lista filtrada contendo até 'limit' entradas correspondentes.

    Raises:
        None.
    """
    if not query.strip():
        return catalog[:limit]

    tokens = [t.lower() for t in query.strip().split() if t.strip()]
    filtered = [
        item for item in catalog if all(token in item.title.lower() for token in tokens)
    ]
    return filtered[:limit]


def download_and_extract_rom(
    entry: ArchiveRomEntry,
    target_dir: Path,
    platform_code: str = "snes",
    console: Console | None = None,
) -> Path:
    """Faz o download do arquivo do acervo e extrai a imagem da ROM se for compactada.

    Args:
        entry: Entrada do catálogo a ser baixada.
        target_dir: Diretório temporário de destino para gravação e extração.
        platform_code: Plataforma alvo para validar o arquivo extraído.
        console: Instância opcional do Console do Rich para renderizar progresso.

    Returns:
        Caminho Path da ROM extraída compatível com a plataforma.

    Raises:
        RuntimeError: Se o download falhar ou se o arquivo compactado não contiver uma ROM válida.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    temp_archive_path = target_dir / entry.filename

    req = urllib.request.Request(entry.download_url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            total_size = int(resp.headers.get("Content-Length", entry.size_bytes or 0))

            if console:
                with Progress(
                    TextColumn("[bold cyan]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(f"Baixando: {entry.title}", total=total_size)
                    with open(temp_archive_path, "wb") as f:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))
            else:
                with open(temp_archive_path, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
    except Exception as err:
        if temp_archive_path.exists():
            temp_archive_path.unlink(missing_ok=True)
        raise RuntimeError(f"Falha durante o download de '{entry.title}': {err}") from err

    plat_info = SUPPORTED_PLATFORMS.get(platform_code.lower())
    accepted_exts = (
        plat_info.accepted_extensions if plat_info else (".sfc", ".smc", ".chd", ".iso")
    )
    inner_target_exts = tuple(ext for ext in accepted_exts if ext != ".zip") or (
        ".sfc",
        ".smc",
        ".chd",
        ".rvz",
        ".iso",
        ".cso",
    )

    # Se for arquivo zip, extrai a imagem compatível interna
    if temp_archive_path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(temp_archive_path, "r") as zf:
                rom_members = [
                    m
                    for m in zf.namelist()
                    if m.lower().endswith(inner_target_exts) and not m.startswith("__MACOSX")
                ]
                if not rom_members:
                    acc_str = ", ".join(inner_target_exts)
                    raise RuntimeError(
                        f"O arquivo compactado '{entry.filename}' não contém arquivos ({acc_str})."
                    )
                extracted_name = rom_members[0]
                extracted_path = target_dir / Path(extracted_name).name
                with (
                    zf.open(extracted_name) as source_file,
                    open(extracted_path, "wb") as dest_file,
                ):
                    dest_file.write(source_file.read())

            temp_archive_path.unlink(missing_ok=True)
            return extracted_path
        except zipfile.BadZipFile as err:
            temp_archive_path.unlink(missing_ok=True)
            raise RuntimeError(f"Arquivo zip corrompido: {err}") from err

    # Se já for um arquivo descompactado no formato aceito (ex: .chd, .rvz, .sfc, .iso)
    if temp_archive_path.suffix.lower() in accepted_exts:
        return temp_archive_path

    raise RuntimeError(
        f"Formato compactado não suportado para extração: {temp_archive_path.suffix}"
    )


def fetch_and_ingest_rom(
    entry: ArchiveRomEntry,
    platform_code: str = "snes",
    repo_root: Path | None = None,
    console: Console | None = None,
) -> Path:
    """Baixa um título do catálogo, extrai e aciona a ingestão canônica no RetroGame Lab.

    Args:
        entry: Entrada do catálogo selecionada.
        platform_code: Código da plataforma alvo (snes, ps1, ps2, psp, gc, dc).
        repo_root: Raiz opcional do repositório.
        console: Instância do Console para mensagens de feedback.

    Returns:
        Caminho Path do arquivo final importado e higienizado em data/roms/<platform_code>/.

    Raises:
        RuntimeError: Se ocorrer erro no download ou extração.
        ValueError: Se a ingestão reprovar os formatos ou nomes.
    """
    root = repo_root or find_repo_root()
    temp_dir = root / "scratch" / "downloads"
    temp_dir.mkdir(parents=True, exist_ok=True)

    extracted_rom = download_and_extract_rom(
        entry, temp_dir, platform_code=platform_code, console=console
    )

    try:
        final_path = import_rom(
            source_path=extracted_rom,
            platform_code=platform_code,
            move=True,
            repo_root=root,
        )
        return final_path
    finally:
        # Garante a limpeza de qualquer sobra na pasta temporária
        if extracted_rom.exists():
            extracted_rom.unlink(missing_ok=True)


def run_interactive_fetcher(
    platform_code: str = "snes",
    query: str | None = None,
    identifier: str | None = None,
    repo_root: Path | None = None,
    console: Console | None = None,
) -> list[Path]:
    """Executa a interface interativa de busca, seleção e download de jogos por plataforma.

    Args:
        platform_code: Código da plataforma (snes, ps1, ps2, psp, gc, dc).
        query: Termo inicial opcional de pesquisa.
        identifier: Identificador personalizado opcional no Internet Archive.
        repo_root: Raiz opcional do repositório.
        console: Instância do Console para renderização de telas e tabelas.

    Returns:
        Lista de caminhos de ROMs importadas com sucesso nesta sessão.

    Raises:
        ValueError: Se a plataforma for inválida.
    """
    plat_key = platform_code.lower().strip()
    if plat_key not in SUPPORTED_PLATFORMS:
        valid = ", ".join(SUPPORTED_PLATFORMS.keys())
        raise ValueError(f"Plataforma '{platform_code}' inválida. Escolha entre: {valid}.")

    c = console or Console(highlight=False)
    root = repo_root or find_repo_root()

    plat_info = SUPPORTED_PLATFORMS[plat_key]
    preset_config = PLATFORM_ARCHIVE_CONFIGS.get(plat_key)

    active_identifier = (
        identifier
        or (preset_config.default_identifier if preset_config else "nointro-snes")
    )

    c.print(
        "\n[bold green]=== RetroGame Lab: Central de Ingestão de ROMs "
        f"({plat_info.name}) ===[/bold green]"
    )
    c.print(f"[white]Coleção Ativa:[/white] [cyan]{active_identifier}[/cyan]")
    if preset_config:
        c.print(f"[white]Iniciativa:[/white] [yellow]{preset_config.description}[/yellow]")
    c.print("[white]Consultando catálogo de preservação digital...[/white]")

    try:
        catalog = get_archive_catalog(
            identifier=active_identifier, platform_code=plat_key, repo_root=root
        )
    except Exception as err:
        c.print(f"[bold red]Erro ao carregar catálogo:[/bold red] {err}")
        return []

    c.print(f"[bold cyan]Total de títulos catalogados:[/bold cyan] {len(catalog)} itens.\n")

    current_query = query or ""
    imported_paths: list[Path] = []

    while True:
        results = search_catalog(catalog, current_query, limit=25)

        if not results:
            c.print(
                "[bold yellow]Nenhum jogo encontrado para o termo "
                f"'{current_query}'.[/bold yellow]\n"
            )
        else:
            filt_desc = current_query or "*"
            tbl_title = f"Resultados ({plat_info.name} - Filtro: '{filt_desc}')"
            table = Table(
                title=tbl_title,
                header_style="bold magenta",
            )
            table.add_column("#", style="cyan", width=4, justify="right")
            table.add_column("Título do Jogo / Versão Preservada", style="white")
            table.add_column("Tamanho Estimado", style="green", width=16, justify="right")

            for idx, item in enumerate(results, start=1):
                size_mb = f"{item.size_bytes / (1024 * 1024):.2f} MB" if item.size_bytes else "-"
                table.add_row(str(idx), item.title, size_mb)

            c.print(table)
            c.print()

        c.print("[cyan]Opções disponíveis:[/cyan]")
        c.print(
            " • Digite os números para baixar (ex: [bold green]1[/bold green] "
            "ou [bold green]1, 3, 5[/bold green])"
        )
        c.print(
            " • Digite [bold yellow]/busca <termo>[/bold yellow] para pesquisar "
            "(ex: [yellow]/busca mario[/yellow])"
        )
        c.print(
            " • Digite [bold cyan]/colecao <id>[/bold cyan] para trocar a coleção "
            "(ex: [cyan]/colecao outra-colecao[/cyan])"
        )
        c.print(" • Digite [bold red]sair[/bold red] (ou 'q') para encerrar a sessão.")

        choice = Prompt.ask("\n[bold white]Sua escolha[/bold white]", default="sair").strip()

        if choice.lower() in ("sair", "q", "exit"):
            break

        if choice.lower().startswith("/colecao ") or choice.lower().startswith("colecao "):
            parts = choice.split(maxsplit=1)
            new_id = parts[1].strip() if len(parts) > 1 else ""
            if new_id:
                active_identifier = new_id
                c.print(f"\n[cyan]Carregando catálogo da coleção '{active_identifier}'...[/cyan]")
                try:
                    catalog = get_archive_catalog(
                        identifier=active_identifier,
                        platform_code=plat_key,
                        repo_root=root,
                    )
                    c.print(
                        f"[bold green]Catálogo atualizado:[/bold green] {len(catalog)} itens.\n"
                    )
                    current_query = ""
                except Exception as err:
                    c.print(f"[bold red]Erro ao trocar coleção:[/bold red] {err}\n")
            continue

        if choice.lower().startswith("/busca ") or choice.lower().startswith("busca "):
            parts = choice.split(maxsplit=1)
            current_query = parts[1] if len(parts) > 1 else ""
            continue

        # Interpretação dos números selecionados
        indices: list[int] = []
        for part in choice.replace(";", ",").split(","):
            part_str = part.strip()
            if part_str.isdigit():
                val = int(part_str)
                if 1 <= val <= len(results):
                    indices.append(val - 1)

        if not indices:
            c.print("[bold red]Entrada não reconhecida. Tente novamente.[/bold red]\n")
            continue

        c.print(
            f"\n[bold green]Iniciando download e ingestão de {len(indices)} "
            "jogo(s)...[/bold green]\n"
        )

        for idx in indices:
            selected_entry = results[idx]
            try:
                c.print(
                    f"\n[cyan]Processando:[/cyan] [bold white]{selected_entry.title}[/bold white]"
                )
                final_path = fetch_and_ingest_rom(
                    entry=selected_entry,
                    platform_code=plat_key,
                    repo_root=root,
                    console=c,
                )
                rel_path = (
                    str(final_path.relative_to(root))
                    if final_path.is_relative_to(root)
                    else str(final_path)
                )
                c.print(
                    "[bold green][OK] Ingestão Concluída:[/bold green] "
                    f"ROM higienizada em [white]{rel_path}[/white]"
                )
                imported_paths.append(final_path)
            except Exception as err:
                c.print(f"[bold red]Falha ao importar '{selected_entry.title}':[/bold red] {err}")

        c.print("\n[bold cyan]Deseja buscar outros jogos ou baixar mais títulos?[/bold cyan]")
        again = Prompt.ask("Continuar pesquisando?", choices=["s", "n"], default="s")
        if again.lower() != "s":
            break

    c.print(
        f"\n[bold green]Sessão finalizada![/bold green] Total de {len(imported_paths)} "
        f"jogo(s) de {plat_info.name} adicionado(s) à biblioteca.\n"
    )
    return imported_paths


def run_interactive_snes_fetcher(
    query: str | None = None,
    repo_root: Path | None = None,
    console: Console | None = None,
) -> list[Path]:
    """Alias de compatibilidade para busca interativa em SNES.

    Args:
        query: Termo inicial opcional de pesquisa.
        repo_root: Raiz opcional do repositório.
        console: Instância do Console para renderização de telas e tabelas.

    Returns:
        Lista de caminhos de ROMs importadas com sucesso nesta sessão.

    Raises:
        None.
    """
    return run_interactive_fetcher(
        platform_code="snes",
        query=query,
        repo_root=repo_root,
        console=console,
    )
