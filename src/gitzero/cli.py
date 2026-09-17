from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from .git_signals import analyze_git_history
from .repo_loader import RepositoryLoadError, load_repository
from .report import render_help, render_report
from .scoring import build_score_summary
from .static_signals import analyze_static_code, collect_static_candidates

app = typer.Typer(
    name="gitzero",
    help="Scan repositories for signals consistent with AI-assisted code.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.callback()
def root() -> None:
    """GitZero command group."""


@app.command()
def help() -> None:
    """Show GitZero commands, scoring, and examples."""
    render_help(console)


@app.command()
def scan(
    target: Annotated[str, typer.Argument(help="GitHub repo URL or local repository folder.")],
) -> None:
    """Scan a repository and print a GitZero report."""
    try:
        with ExitStack() as stack:
            with console.status("[bold cyan]Loading repository...[/]"):
                repository = stack.enter_context(load_repository(target))
            git_findings, static_result, score = _collect_scan_with_progress(
                repo_path=repository.path,
            )
            render_report(
                console,
                repository=repository,
                score=score,
                static_result=static_result,
                git_findings=git_findings,
                git_history_enabled=True,
            )
    except RepositoryLoadError as exc:
        console.print(f"[red]Could not load repository:[/] {exc}")
        raise typer.Exit(1) from exc


def _collect_scan_with_progress(
    *,
    repo_path: Path,
):
    with console.status("[bold cyan]Reading git history...[/]"):
        git_findings = analyze_git_history(repo_path)

    with console.status("[bold cyan]Preparing source file index...[/]"):
        source_candidates = collect_static_candidates(repo_path)

    progress_total = max(1, len(source_candidates))
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold cyan]Scanning source files[/]"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("source-scan", total=progress_total)

        def advance(_path: Path) -> None:
            progress.advance(task_id)

        static_result = analyze_static_code(
            repo_path,
            max_file_size_kb=400,
            max_files=2000,
            source_candidates=source_candidates,
            progress_callback=advance,
        )
        if not source_candidates:
            progress.update(task_id, completed=progress_total)

    with console.status("[bold cyan]Scoring signals...[/]"):
        score = build_score_summary(
            git_findings,
            static_result,
            git_history_enabled=True,
        )
    return git_findings, static_result, score


def main() -> None:
    app()


if __name__ == "__main__":
    main()
