"""Módulo de busca, download e ingestão de ROMs a partir de acervos de preservação digital.

Permite consultar catálogos remotos (como acervos No-Intro e Redump no Internet Archive)
para todas as plataformas homologadas (SNES, PS1, PS2, PSP, GC, DC), navegar com interface
moderna em terminal (paginação, metadados, filtros dinâmicos e seleção em lote),
realizar o download para a área volátil (scratch/) e acionar a ingestão canônica.
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

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Prompt
from rich.table import Table

from retrogame_lab.config import SUPPORTED_PLATFORMS, find_repo_root
from retrogame_lab.ingestion import import_rom

USER_AGENT = "RetroGameLab-Fetcher/1.0 (Digital Preservation Tool)"
DEFAULT_PAGE_SIZE = 15


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
        clean_title: Título principal do jogo sem tags de região.
        region_tag: Tag de região detectada (ex.: 'USA', 'EUR', 'JPN', 'BRA').
        extra_info: Informações adicionais como disco, revisão ou tradução.
        extension: Extensão original do arquivo (ex.: '.chd', '.rvz', '.zip').
    """

    filename: str
    title: str
    size_bytes: int
    download_url: str
    clean_title: str = ""
    region_tag: str = "Global"
    extra_info: str = ""
    extension: str = ""


def parse_title_metadata(raw_title: str) -> tuple[str, str, str]:
    """Extrai o título limpo, região normalizada e informações extras da ROM.

    Args:
        raw_title: Título original do arquivo sem extensão.

    Returns:
        Tupla contendo (titulo_limpo, tag_regiao, detalhes_extras).

    Raises:
        None.
    """
    tags = re.findall(r"\((.*?)\)|\[(.*?)\]", raw_title)
    flat_tags = [item.strip() for sub in tags for item in sub if item.strip()]

    clean_title = re.sub(r"\(.*?\)|\[.*?\]", "", raw_title).strip()
    clean_title = re.sub(r"\s+", " ", clean_title)
    if not clean_title:
        clean_title = raw_title

    region = "Global"
    extra_parts: list[str] = []

    for tag in flat_tags:
        lower = tag.lower()
        if any(r in lower for r in ("usa", "america")):
            region = "USA"
        elif any(r in lower for r in ("europe", "eur", "pal")):
            region = "EUR"
        elif any(r in lower for r in ("japan", "jpn", "ja")):
            region = "JPN"
        elif any(r in lower for r in ("brazil", "brz", "bra", "pt")):
            region = "BRA"
        elif any(r in lower for r in ("world", "wld")):
            region = "WLD"
        else:
            extra_parts.append(tag)

    return clean_title, region, ", ".join(extra_parts)


def format_region_badge(region: str) -> str:
    """Formata o rótulo de região com cores temáticas no Rich.

    Args:
        region: Código de região ('USA', 'EUR', 'JPN', 'BRA', 'WLD', 'Global').

    Returns:
        String formatada para renderização no Rich.

    Raises:
        None.
    """
    match region:
        case "USA":
            return "[bold blue]USA[/bold blue]"
        case "EUR":
            return "[bold cyan]EUR[/bold cyan]"
        case "JPN":
            return "[bold magenta]JPN[/bold magenta]"
        case "BRA":
            return "[bold green]BRA[/bold green]"
        case "WLD":
            return "[bold yellow]WLD[/bold yellow]"
        case _:
            return "[dim white]Global[/dim white]"


def format_file_size(size_bytes: int) -> str:
    """Formata o tamanho em bytes para representação legível (KB, MB, GB).

    Args:
        size_bytes: Tamanho em bytes.

    Returns:
        Texto formatado com cores indicativas.

    Raises:
        None.
    """
    if size_bytes <= 0:
        return "[dim]-[/dim]"
    if size_bytes < 1024 * 1024:
        kb = size_bytes / 1024
        return f"[dim cyan]{kb:.1f} KB[/dim cyan]"
    mb = size_bytes / (1024 * 1024)
    if mb >= 1024:
        gb = mb / 1024
        return f"[bold yellow]{gb:.2f} GB[/bold yellow]"
    return f"[green]{mb:.1f} MB[/green]"


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
        clean_full_title = re.sub(
            r"\.(zip|sfc|smc|chd|iso|cso|rvz|7z)$", "", name, flags=re.IGNORECASE
        )
        base_name, region, extra = parse_title_metadata(clean_full_title)
        ext = Path(name).suffix.lower()

        encoded_name = urllib.parse.quote(name)
        download_url = f"{base_download_url}/{encoded_name}"

        entries.append(
            ArchiveRomEntry(
                filename=name,
                title=clean_full_title,
                size_bytes=size,
                download_url=download_url,
                clean_title=base_name,
                region_tag=region,
                extra_info=extra,
                extension=ext,
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
                    SpinnerColumn(),
                    TextColumn("[bold cyan]{task.description}"),
                    BarColumn(bar_width=30),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(f"Baixando: {entry.clean_title}", total=total_size)
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


def render_header_panel(
    platform_code: str,
    identifier: str,
    total_items: int,
    description: str,
) -> Panel:
    """Renderiza o painel superior de cabeçalho estilizado com seletor visual de plataformas.

    Args:
        platform_code: Código da plataforma em exibição.
        identifier: Identificador da coleção remota.
        total_items: Quantidade total de itens na coleção.
        description: Descrição da iniciativa de preservação.

    Returns:
        Instância de Panel estilizada com Rich.

    Raises:
        None.
    """
    plat_pills = []
    for code in SUPPORTED_PLATFORMS:
        if code == platform_code:
            plat_pills.append(f"[bold black on cyan] {code.upper()} [/bold black on cyan]")
        else:
            plat_pills.append(f"[dim white] {code.upper()} [/dim white]")

    pills_row = "  ".join(plat_pills)
    plat_info = SUPPORTED_PLATFORMS[platform_code]

    body = (
        f"[bold white]{plat_info.name}[/bold white] • [yellow]{plat_info.emulator_name}[/yellow]\n"
        f"Coleção: [cyan]{identifier}[/cyan] ({total_items} títulos disponíveis)\n"
        f"Iniciativa: [dim]{description}[/dim]\n\n"
        f"Plataformas: {pills_row}"
    )

    return Panel(
        body,
        title="[bold green]RetroGame Lab • Central de Ingestão e Preservação Digital[/bold green]",
        box=box.ROUNDED,
        border_style="cyan",
        padding=(0, 2),
    )


def render_controls_panel() -> Panel:
    """Renderiza a barra inferior de navegação e comandos rápidos.

    Args:
        None.

    Returns:
        Instância de Panel com instruções organizadas.

    Raises:
        None.
    """
    text = (
        "[bold cyan][1-N][/bold cyan] Baixar seleção (ex: [cyan]2[/cyan] ou [cyan]1, 3[/cyan])  •  "
        "[bold yellow][n / p][/bold yellow] Próxima / Anterior  •  "
        "[bold green]<texto>[/bold green] Filtrar título\n"
        "[bold magenta]/plat <snes|ps1|ps2|psp|gc|dc>[/bold magenta] Trocar plataforma  •  "
        "[bold cyan]/colecao <id>[/bold cyan] Trocar acervo  •  "
        "[bold red]sair (q)[/bold red] Fechar"
    )
    return Panel(
        text,
        title="[dim]Navegação e Comandos[/dim]",
        box=box.ROUNDED,
        border_style="dim",
        padding=(0, 1),
    )


def run_interactive_fetcher(
    platform_code: str = "snes",
    query: str | None = None,
    identifier: str | None = None,
    repo_root: Path | None = None,
    console: Console | None = None,
) -> list[Path]:
    """Executa a interface interativa e moderna de busca, navegação e download de ROMs.

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

    active_plat = plat_key
    preset_config = PLATFORM_ARCHIVE_CONFIGS.get(active_plat)
    active_identifier = (
        identifier
        or (preset_config.default_identifier if preset_config else "nointro-snes")
    )

    c.print(f"\n[cyan]Carregando acervo de preservação ({active_identifier})...[/cyan]")
    try:
        catalog = get_archive_catalog(
            identifier=active_identifier, platform_code=active_plat, repo_root=root
        )
    except Exception as err:
        c.print(f"[bold red]Erro ao carregar catálogo:[/bold red] {err}")
        return []

    current_query = query or ""
    current_page = 0
    imported_paths: list[Path] = []

    while True:
        preset_config = PLATFORM_ARCHIVE_CONFIGS.get(active_plat)
        desc = preset_config.description if preset_config else "Preservação Comunitária"

        # Filtra os itens do catálogo
        if current_query.strip():
            tokens = [t.lower() for t in current_query.strip().split() if t.strip()]
            matched_items = [
                item
                for item in catalog
                if all(tok in item.title.lower() for tok in tokens)
            ]
        else:
            matched_items = catalog

        total_matches = len(matched_items)
        total_pages = max(1, (total_matches + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE)
        if current_page >= total_pages:
            current_page = max(0, total_pages - 1)

        start_idx = current_page * DEFAULT_PAGE_SIZE
        end_idx = min(start_idx + DEFAULT_PAGE_SIZE, total_matches)
        page_items = matched_items[start_idx:end_idx]

        # Renderização visual moderna
        c.clear()
        c.print(render_header_panel(active_plat, active_identifier, len(catalog), desc))

        f_status = (
            f"[bold green]'{current_query}'[/bold green]"
            if current_query
            else "[dim]* (Todos)[/dim]"
        )
        title_str = (
            f"Resultados • Filtro: {f_status} • "
            f"Página [bold cyan]{current_page + 1}/{total_pages}[/bold cyan] "
            f"({total_matches} jogos)"
        )

        table = Table(
            title=title_str,
            box=box.ROUNDED,
            border_style="dim",
            header_style="bold cyan",
            expand=True,
        )
        table.add_column("#", style="bold cyan", width=4, justify="right")
        table.add_column("Título do Jogo", style="white", ratio=4)
        table.add_column("Região", width=8, justify="center")
        table.add_column("Detalhes", style="dim", ratio=2)
        table.add_column("Formato", style="yellow", width=8, justify="center")
        table.add_column("Tamanho", justify="right", width=12)

        if not page_items:
            table.add_row(
                "-",
                "[yellow]Nenhum jogo localizado com o filtro atual.[/yellow]",
                "-",
                "-",
                "-",
                "-",
            )
        else:
            for idx, item in enumerate(page_items, start=1):
                badge = format_region_badge(item.region_tag)
                size_str = format_file_size(item.size_bytes)
                details = item.extra_info if item.extra_info else "[dim]-[/dim]"
                table.add_row(
                    str(idx),
                    f"[bold white]{item.clean_title}[/bold white]",
                    badge,
                    details,
                    item.extension or "-",
                    size_str,
                )

        c.print(table)
        c.print(render_controls_panel())

        user_input = Prompt.ask("\n[bold cyan]retrogame-lab[/bold cyan] >", default="").strip()

        if user_input.lower() in ("sair", "q", "exit"):
            break

        # Paginação: próxima página
        if user_input.lower() in ("n", "next", "proximo", "proxima", ">"):
            if current_page < total_pages - 1:
                current_page += 1
            else:
                c.print("[yellow]Você já está na última página.[/yellow]")
            continue

        # Paginação: página anterior
        if user_input.lower() in ("p", "prev", "anterior", "<"):
            if current_page > 0:
                current_page -= 1
            continue

        # Comandos iniciados por '/'
        if user_input.startswith("/"):
            cmd_parts = user_input[1:].split(maxsplit=1)
            action = cmd_parts[0].lower()
            arg = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

            # Troca dinâmica de plataforma
            if action in ("plat", "plataforma") or action in SUPPORTED_PLATFORMS:
                target_plat = action if action in SUPPORTED_PLATFORMS else arg.lower()
                if target_plat in SUPPORTED_PLATFORMS:
                    active_plat = target_plat
                    cfg = PLATFORM_ARCHIVE_CONFIGS.get(active_plat)
                    active_identifier = cfg.default_identifier if cfg else "nointro-snes"
                    current_query = ""
                    current_page = 0
                    c.print(
                        f"\n[cyan]Carregando acervo de {target_plat.upper()} "
                        f"({active_identifier})...[/cyan]"
                    )
                    try:
                        catalog = get_archive_catalog(
                            identifier=active_identifier, platform_code=active_plat, repo_root=root
                        )
                    except Exception as err:
                        c.print(f"[bold red]Falha ao carregar catálogo:[/bold red] {err}")
                else:
                    valid_str = ", ".join(SUPPORTED_PLATFORMS.keys())
                    c.print(f"[bold red]Plataforma inválida.[/bold red] Opções: {valid_str}")
                continue

            # Troca de coleção remota
            if action in ("colecao", "collection"):
                if arg:
                    active_identifier = arg
                    current_query = ""
                    current_page = 0
                    c.print(
                        f"\n[cyan]Carregando coleção personalizada '{active_identifier}'...[/cyan]"
                    )
                    try:
                        catalog = get_archive_catalog(
                            identifier=active_identifier, platform_code=active_plat, repo_root=root
                        )
                    except Exception as err:
                        c.print(f"[bold red]Erro ao consultar coleção:[/bold red] {err}")
                continue

            # Limpar filtro
            if action in ("limpar", "clear", "todos"):
                current_query = ""
                current_page = 0
                continue

            # Comando de busca explícito
            if action in ("busca", "search"):
                current_query = arg
                current_page = 0
                continue

        # Interpretação de números de seleção para download
        is_numeric_selection = False
        selected_numbers: list[int] = []

        raw_parts = user_input.replace(";", ",").split(",")
        for part in raw_parts:
            part_str = part.strip()
            if part_str.isdigit():
                num = int(part_str)
                if 1 <= num <= len(page_items):
                    selected_numbers.append(num)
                    is_numeric_selection = True

        if is_numeric_selection and selected_numbers:
            target_entries = [page_items[n - 1] for n in selected_numbers]
            total_dl_bytes = sum(e.size_bytes for e in target_entries)
            total_dl_str = format_file_size(total_dl_bytes)

            c.print(
                f"\n[bold green]Preparando download de {len(target_entries)} "
                f"jogo(s) (~{total_dl_str}):[/bold green]"
            )
            for e in target_entries:
                c.print(f" • [white]{e.title}[/white] ({format_file_size(e.size_bytes)})")

            confirm = Prompt.ask(
                "\nConfirmar download e ingestão?", choices=["s", "n"], default="s"
            )
            if confirm.lower() == "s":
                for entry in target_entries:
                    try:
                        c.print(
                            f"\n[cyan]Processando:[/cyan] [bold white]{entry.title}[/bold white]"
                        )
                        final_p = fetch_and_ingest_rom(
                            entry=entry,
                            platform_code=active_plat,
                            repo_root=root,
                            console=c,
                        )
                        rel_path = (
                            str(final_p.relative_to(root))
                            if final_p.is_relative_to(root)
                            else str(final_p)
                        )
                        c.print(
                            "[bold green][✓] Ingestão Concluída:[/bold green] "
                            f"ROM disponível em [white]{rel_path}[/white]"
                        )
                        imported_paths.append(final_p)
                    except Exception as err:
                        c.print(f"[bold red]Falha ao importar '{entry.title}':[/bold red] {err}")

                Prompt.ask(
                    "\nPressione [bold white]Enter[/bold white] para continuar...", default=""
                )
            continue

        # Caso contrário, qualquer texto digitado funciona diretamente como filtro de busca
        if user_input:
            current_query = user_input
            current_page = 0
        else:
            current_query = ""
            current_page = 0

    c.print(
        f"\n[bold green]Sessão finalizada![/bold green] Total de {len(imported_paths)} "
        "jogo(s) adicionado(s) à biblioteca local.\n"
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
