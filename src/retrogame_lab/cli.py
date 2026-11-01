"""Interface de Linha de Comando (CLI) para o RetroGame Lab.

Fornece comandos para auditoria de integridade da biblioteca de jogos,
inspeção de configurações do sistema e diagnóstico de salvamentos.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from retrogame_lab import __version__
from retrogame_lab.auditor import Severity, run_full_audit
from retrogame_lab.config import SUPPORTED_PLATFORMS, find_repo_root
from retrogame_lab.ingestion import import_rom, import_roms_batch
from retrogame_lab.sanitizer import sanitize_directory

# Configuração de encoding UTF-8 resiliente para Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

app = typer.Typer(
    name="retrogame-lab",
    help="CLI para gerenciamento, auditoria e controle de integridade do RetroGame Lab.",
    add_completion=False,
)
console = Console(highlight=False)


@app.command()
def version() -> None:
    """Exibe a versão instalada do pacote RetroGame Lab.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    console.print(f"[bold cyan]RetroGame Lab[/bold cyan] versão [green]{__version__}[/green]")


@app.command()
def info() -> None:
    """Exibe informações sobre a topologia de diretórios e plataformas suportadas.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    try:
        root = find_repo_root()
        console.print(f"[bold green]Raiz do repositório:[/bold green] {root}")
    except FileNotFoundError as err:
        console.print(f"[bold red]Aviso:[/bold red] {err}")

    table = Table(title="Plataformas Homologadas no RetroGame Lab")
    table.add_column("Código", style="cyan", no_wrap=True)
    table.add_column("Plataforma", style="white")
    table.add_column("Formato Canônico", style="green")
    table.add_column("Extensões Aceitas", style="yellow")
    table.add_column("Estratégia de Saves", style="magenta")
    table.add_column("Emulador", style="blue")

    for p in SUPPORTED_PLATFORMS.values():
        table.add_row(
            p.code,
            p.name,
            p.canonical_format,
            ", ".join(p.accepted_extensions),
            p.save_format_desc,
            p.emulator_name,
        )

    console.print(table)


@app.command()
def audit(
    repo_path: Annotated[
        Optional[Path],
        typer.Option(
            "--path",
            "-p",
            help="Caminho raiz do repositório para a auditoria. Padrão: auto-detectado.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json-output",
            "--json",
            "-j",
            help="Retorna o relatório em formato JSON estruturado.",
        ),
    ] = False,
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help="Executa auditoria completa de todos os subsistemas (comportamento padrão).",
        ),
    ] = True,
) -> None:
    """Audita a integridade de BIOS, ROMs e regras de salvamento no repositório.

    Args:
        repo_path: Caminho opcional para a raiz do repositório.
        json_output: Se True, formata a saída como documento JSON.
        full: Se True, realiza a auditoria completa de todos os subsistemas.

    Returns:
        None.

    Raises:
        typer.Exit: Se erros impeditivos (Severity.ERROR) forem detectados (código 1).
    """
    try:
        resolved_root = repo_path or find_repo_root()
    except FileNotFoundError as err:
        console.print(f"[bold red]Erro:[/bold red] {err}")
        raise typer.Exit(code=1) from err

    report = run_full_audit(resolved_root)

    if json_output:
        data = {
            "bios": {
                "scanned": report.bios.total_scanned,
                "issues": [
                    {
                        "severity": i.severity.value,
                        "message": i.message,
                        "file": str(i.file_path) if i.file_path else None,
                    }
                    for i in report.bios.issues
                ],
            },
            "roms": {
                "scanned": report.roms.total_scanned,
                "issues": [
                    {
                        "severity": i.severity.value,
                        "message": i.message,
                        "file": str(i.file_path) if i.file_path else None,
                    }
                    for i in report.roms.issues
                ],
            },
            "saves": {
                "scanned": report.saves.total_scanned,
                "issues": [
                    {
                        "severity": i.severity.value,
                        "message": i.message,
                        "file": str(i.file_path) if i.file_path else None,
                    }
                    for i in report.saves.issues
                ],
            },
            "has_errors": report.has_errors,
            "total_issues": report.total_issues,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        if report.has_errors:
            raise typer.Exit(code=1)
        return

    console.print("\n[bold green]=== Auditoria de Integridade do RetroGame Lab ===[/bold green]\n")

    summaries = [report.bios, report.roms, report.saves]
    has_any_issue = False

    for summary in summaries:
        if not summary.issues:
            console.print(
                f"[bold green][OK][/bold green] [cyan]{summary.category}[/cyan]: "
                f"{summary.total_scanned} item(ns) inspecionado(s) - 0 problemas."
            )
            continue

        has_any_issue = True
        status_color = "red" if not summary.is_healthy else "yellow"
        console.print(
            f"[{status_color}][!][/{status_color}] [bold cyan]{summary.category}[/bold cyan] "
            f"({summary.total_scanned} item(ns) inspecionado(s)):"
        )

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Severidade", width=12)
        table.add_column("Arquivo Relativo")
        table.add_column("Descrição do Apontamento")

        for issue in summary.issues:
            color = (
                "red"
                if issue.severity == Severity.ERROR
                else "yellow"
                if issue.severity == Severity.WARNING
                else "blue"
            )
            rel_path = (
                str(issue.file_path.relative_to(resolved_root))
                if issue.file_path and issue.file_path.is_relative_to(resolved_root)
                else str(issue.file_path)
                if issue.file_path
                else "-"
            )
            table.add_row(f"[{color}]{issue.severity.value}[/{color}]", rel_path, issue.message)

        console.print(table)
        console.print()

    if not has_any_issue:
        console.print(
            "[bold green]Biblioteca e regras de salvamento estão em perfeito estado![/bold green]\n"
        )
    elif report.has_errors:
        console.print(
            "[bold red]Auditoria concluída com erros críticos que exigem correção.[/bold red]\n"
        )
        raise typer.Exit(code=1)
    else:
        console.print("[bold yellow]Auditoria concluída com avisos informativos.[/bold yellow]\n")


@app.command()
def sanitize(
    target_path: Annotated[
        Optional[Path],
        typer.Option(
            "--path",
            "-p",
            help="Caminho do diretório para sanitizar. Padrão: data/ da raiz do repositório.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--apply",
            help="Simula as alterações (--dry-run) ou aplica as renomeações (--apply).",
        ),
    ] = True,
) -> None:
    """Higieniza nomes de ROMs e saves substituindo espaços por '_' e removendo aspas.

    Garante conformidade para compatibilidade perfeita com scripts, CLI e Android.

    Args:
        target_path: Caminho opcional do diretório a sanitizar.
        dry_run: Se True, apenas simula as alterações sem renomear fisicamente.

    Returns:
        None.

    Raises:
        typer.Exit: Se o diretório alvo não for encontrado.
    """
    try:
        root = find_repo_root()
        default_dir = root / "data"
    except FileNotFoundError:
        default_dir = Path.cwd() / "data"

    scan_dir = target_path or default_dir
    if not scan_dir.exists():
        console.print(f"[bold red]Erro:[/bold red] Diretório alvo não encontrado: {scan_dir}")
        raise typer.Exit(code=1)

    mode_label = (
        "[yellow](Simulação - Dry Run)[/yellow]" if dry_run else "[green](Execução Real)[/green]"
    )
    console.print(
        f"\n[bold cyan]=== Higienização de Nomes de ROMs e Saves {mode_label} ===[/bold cyan]\n"
    )
    console.print(f"Diretório alvo: [white]{scan_dir}[/white]\n")

    changes = sanitize_directory(scan_dir, dry_run=dry_run)

    if not changes:
        console.print(
            "[bold green]Todos os arquivos estão 100% em conformidade com o padrão![/bold green]\n"
        )
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Arquivo Original", style="red")
    table.add_column("Nome Sanitizado (Sem Espaços/Especiais)", style="green")

    for old_p, new_p in changes:
        try:
            rel_old = str(old_p.relative_to(scan_dir))
            rel_new = str(new_p.relative_to(scan_dir))
        except ValueError:
            rel_old = old_p.name
            rel_new = new_p.name
        table.add_row(rel_old, rel_new)

    console.print(table)
    console.print()

    if dry_run:
        console.print(
            f"[bold yellow]Simulação concluída:[/bold yellow] "
            f"{len(changes)} arquivo(s) precisam de padronização.\n"
            "Execute com [bold green]--apply[/bold green] para aplicar as alterações nos arquivos."
        )
    else:
        console.print(
            f"[bold green]Sucesso:[/bold green] {len(changes)} arquivo(s) renomeados com sucesso!"
        )


@app.command(name="import-rom")
def import_rom_cmd(
    source: Annotated[
        Path,
        typer.Argument(
            help="Caminho do arquivo ou diretório de ROMs a ser importado.",
        ),
    ],
    platform: Annotated[
        str,
        typer.Option(
            "--platform",
            "-p",
            help="Código da plataforma de destino (snes, ps1, ps2, psp, gc, dc).",
        ),
    ],
    move: Annotated[
        bool,
        typer.Option(
            "--move",
            "-m",
            help="Move o arquivo de origem em vez de copiar.",
        ),
    ] = False,
) -> None:
    """Importa uma ROM para a biblioteca canônica, validando extensão e normalizando o nome.

    Aplica sanitização automática substituindo espaços por '_' e removendo caracteres especiais.

    Args:
        source: Caminho do arquivo ou pasta a importar.
        platform: Código da plataforma alvo.
        move: Se True, move o arquivo de origem.

    Returns:
        None.

    Raises:
        typer.Exit: Se houver erro de validação ou arquivo inexistente (código 1).
    """
    try:
        resolved_root = find_repo_root()
    except FileNotFoundError:
        resolved_root = Path.cwd()

    if not source.exists():
        console.print(f"[bold red]Erro:[/bold red] Caminho de origem não encontrado: {source}")
        raise typer.Exit(code=1)

    try:
        if source.is_dir():
            console.print(
                f"\n[bold cyan]=== Ingestão em Lote: Plataforma '{platform}' ===[/bold cyan]\n"
            )
            imported_list = import_roms_batch(source, platform, move=move, repo_root=resolved_root)
            if not imported_list:
                console.print("[bold yellow]Nenhum arquivo compatível localizado.[/bold yellow]\n")
                return

            table = Table(title="ROMs Importadas com Sucesso", header_style="bold magenta")
            table.add_column("Arquivo Destino (Higienizado)", style="green")
            for dest in imported_list:
                rel = (
                    str(dest.relative_to(resolved_root))
                    if dest.is_relative_to(resolved_root)
                    else dest.name
                )
                table.add_row(rel)
            console.print(table)
            console.print(
                f"\n[bold green]Sucesso:[/bold green] {len(imported_list)} ROM(s) importada(s)!"
            )
        else:
            dest = import_rom(source, platform, move=move, repo_root=resolved_root)
            rel_dest = (
                str(dest.relative_to(resolved_root))
                if dest.is_relative_to(resolved_root)
                else dest.name
            )
            action = "Movido" if move else "Copiado"
            console.print(
                f"\n[bold green]Sucesso ({action}):[/bold green] "
                f"ROM importada e higienizada com sucesso:\n"
                f"[cyan]Destino:[/cyan] [bold white]{rel_dest}[/bold white]\n"
            )
    except (ValueError, FileExistsError, FileNotFoundError, IsADirectoryError) as err:
        console.print(f"[bold red]Erro de Ingestão:[/bold red] {err}")
        raise typer.Exit(code=1) from err


def run_pwsh_script(script_name: str, args: list[str]) -> int:
    """Executa um script PowerShell Core (pwsh) localizado no diretório scripts/.

    Args:
        script_name: Nome do arquivo de script (ex.: 'bootstrap.ps1').
        args: Lista de argumentos adicionais repassados ao script.

    Returns:
        Código de retorno (exit code) da execução do processo.

    Raises:
        FileNotFoundError: Se a raiz do projeto ou o script especificado não existirem.
    """
    root = find_repo_root()
    script_path = root / "scripts" / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Script PowerShell não encontrado: {script_path}")

    cmd = ["pwsh", "-NoProfile", "-File", str(script_path)] + args
    result = subprocess.run(cmd, check=False)
    return result.returncode


@app.command()
def bootstrap(
    skip_winget: Annotated[
        bool,
        typer.Option(
            "--skip-winget",
            "-s",
            help="Cria pastas e marcadores de portabilidade sem instalar ferramentas via winget.",
        ),
    ] = False,
) -> None:
    """Executa o provisionamento de diretórios, templates e runtimes via PowerShell.

    Args:
        skip_winget: Se True, omite a etapa de verificação e instalação de pacotes winget.

    Returns:
        None.

    Raises:
        typer.Exit: Se o processo pwsh retornar código de erro ou falhar na execução.
    """
    pwsh_args = []
    if skip_winget:
        pwsh_args.append("-SkipWinget")

    try:
        code = run_pwsh_script("bootstrap.ps1", pwsh_args)
        if code != 0:
            raise typer.Exit(code=code)
    except FileNotFoundError as err:
        console.print(f"[bold red]Erro:[/bold red] {err}")
        raise typer.Exit(code=1) from err


@app.command(name="audit-library", hidden=True)
def audit_library_alias(
    repo_path: Annotated[
        Optional[Path],
        typer.Option(
            "--path",
            "-p",
            help="Caminho raiz do repositório para a auditoria. Padrão: auto-detectado.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json-output",
            "--json",
            "-j",
            help="Retorna o relatório em formato JSON estruturado.",
        ),
    ] = False,
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help="Executa auditoria completa de todos os subsistemas.",
        ),
    ] = True,
) -> None:
    """Alias para o comando de auditoria 'audit'.

    Args:
        repo_path: Caminho opcional para a raiz do repositório.
        json_output: Se True, formata a saída como documento JSON.
        full: Se True, realiza a auditoria completa de todos os subsistemas.

    Returns:
        None.

    Raises:
        typer.Exit: Se a auditoria detectar erros críticos.
    """
    audit(repo_path=repo_path, json_output=json_output, full=full)


@app.command()
def launch(
    platform: Annotated[
        str,
        typer.Argument(
            help="Código da plataforma suportada (snes, ps1, ps2, psp, gc, dc).",
        ),
    ],
    rom_path: Annotated[
        Path,
        typer.Argument(
            help="Caminho do arquivo de ROM a ser inicializado.",
        ),
    ],
    fullscreen: Annotated[
        bool,
        typer.Option(
            "--fullscreen/--windowed",
            help="Inicia o emulador em tela cheia (padrão) ou modo janela.",
        ),
    ] = True,
    gpu_mode: Annotated[
        str,
        typer.Option(
            "--gpu-mode",
            "-g",
            help="Modo de seleção de GPU ('auto', 'igpu', 'dgpu'). Padrão: 'auto'.",
        ),
    ] = "auto",
) -> None:
    """Inicializa um jogo emulando a plataforma com calibração dinâmica de hardware.

    Args:
        platform: Plataforma do jogo.
        rom_path: Caminho da ROM.
        fullscreen: Flag para tela cheia ou janela.
        gpu_mode: Modo de preferência de GPU.

    Returns:
        None.

    Raises:
        typer.Exit: Se a execução do emulador falhar.
    """
    pwsh_args = [
        "-Platform",
        platform,
        "-RomPath",
        str(rom_path),
        "-GpuMode",
        gpu_mode,
    ]
    if fullscreen:
        pwsh_args.append("-Fullscreen")
    else:
        pwsh_args.append("-Windowed")

    try:
        code = run_pwsh_script("launch.ps1", pwsh_args)
        if code != 0:
            raise typer.Exit(code=code)
    except FileNotFoundError as err:
        console.print(f"[bold red]Erro:[/bold red] {err}")
        raise typer.Exit(code=1) from err


@app.command(name="convert-chd")
def convert_chd(
    source_dir: Annotated[
        Path,
        typer.Argument(
            help="Diretório contendo imagens bin/cue/iso para compactação determinística.",
        ),
    ],
    media_type: Annotated[
        str,
        typer.Option(
            "--media-type",
            "-m",
            help="Tipo de mídia ('cd', 'dvd', 'auto'). Padrão: 'auto'.",
        ),
    ] = "auto",
) -> None:
    """Converte imagens de disco para o formato CHD preservando integridade de setores.

    Args:
        source_dir: Diretório de origem das mídias.
        media_type: Tipo de mídia ('cd', 'dvd', 'auto').

    Returns:
        None.

    Raises:
        typer.Exit: Se a conversão falhar.
    """
    pwsh_args = [
        "-SourceDirectory",
        str(source_dir),
        "-MediaType",
        media_type,
    ]
    try:
        code = run_pwsh_script("convert_chd.ps1", pwsh_args)
        if code != 0:
            raise typer.Exit(code=code)
    except FileNotFoundError as err:
        console.print(f"[bold red]Erro:[/bold red] {err}")
        raise typer.Exit(code=1) from err


@app.command(name="setup-android")
def setup_android(
    device_id: Annotated[
        str,
        typer.Option(
            "--device-id",
            "-d",
            help="Identificador ADB do dispositivo móvel (opcional).",
        ),
    ] = "",
    target_path: Annotated[
        str,
        typer.Option(
            "--target-path",
            "-t",
            help="Caminho base no armazenamento Android. Padrão: /storage/emulated/0/RetroGames.",
        ),
    ] = "/storage/emulated/0/RetroGames",
    skip_download: Annotated[
        bool,
        typer.Option(
            "--skip-download",
            help="Pula o download de APKs mantendo o provisionamento de pastas e permissões.",
        ),
    ] = False,
) -> None:
    """Provisiona o ambiente de emulação e permissões no Android via ADB.

    Args:
        device_id: ID do dispositivo ADB.
        target_path: Caminho alvo no Android.
        skip_download: Pula download dos emuladores se True.

    Returns:
        None.

    Raises:
        typer.Exit: Se a automação ADB falhar.
    """
    pwsh_args = [
        "-TargetDevicePath",
        target_path,
    ]
    if device_id:
        pwsh_args.extend(["-DeviceId", device_id])
    if skip_download:
        pwsh_args.append("-SkipDownload")

    try:
        code = run_pwsh_script("setup_android_emulators.ps1", pwsh_args)
        if code != 0:
            raise typer.Exit(code=code)
    except FileNotFoundError as err:
        console.print(f"[bold red]Erro:[/bold red] {err}")
        raise typer.Exit(code=1) from err


def main() -> None:
    """Ponto de entrada para execução de script direto."""
    app()


if __name__ == "__main__":
    main()
