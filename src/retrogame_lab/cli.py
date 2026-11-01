"""Interface de Linha de Comando (CLI) para o RetroGame Lab.

Fornece comandos para auditoria de integridade da biblioteca de jogos,
inspeção de configurações do sistema e diagnóstico de salvamentos.
"""

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from retrogame_lab import __version__
from retrogame_lab.auditor import Severity, run_full_audit
from retrogame_lab.config import SUPPORTED_PLATFORMS, find_repo_root
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
            "-j",
            help="Retorna o relatório em formato JSON estruturado.",
        ),
    ] = False,
) -> None:
    """Audita a integridade de BIOS, ROMs e regras de salvamento no repositório.

    Args:
        repo_path: Caminho opcional para a raiz do repositório.
        json_output: Se True, formata a saída como documento JSON.

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


def main() -> None:
    """Ponto de entrada para execução de script direto."""
    app()


if __name__ == "__main__":
    main()
