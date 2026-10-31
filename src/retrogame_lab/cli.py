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


def main() -> None:
    """Ponto de entrada para execução de script direto."""
    app()


if __name__ == "__main__":
    main()
