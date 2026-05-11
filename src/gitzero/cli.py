from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from sys import stdout
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

from .evaluation import (
    build_batch_row,
    discover_repo_dirs,
    label_for_repo,
    load_labels,
    write_rows,
)
from .fixtures import create_fixture_corpus
from .git_signals import analyze_git_history
from .ml import load_model_artifact, predict_from_scan
from .models import LoadedRepository
from .repo_loader import RepositoryLoadError, load_repository
from .report import render_help, render_report, report_to_json
from .scoring import build_score_summary
from .static_signals import analyze_static_code, collect_static_candidates

app = typer.Typer(
    name="gitzero",
    help="Scan repositories for signals consistent with AI-assisted code.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def root() -> None:
    """GitZero command group."""


@app.command()
def help() -> None:
    """Show GitZero commands, flags, scoring, and examples."""

    render_help(console)


@app.command()
def scan(
    target: Annotated[str, typer.Argument(help="GitHub repo URL or local repository folder.")],
    no_git_history: Annotated[
        bool,
        typer.Option("--no-git-history", help="Skip commit-history analysis."),
    ] = False,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", "-x", help="Glob or directory name to exclude."),
    ] = None,
    max_file_size: Annotated[
        int,
        typer.Option("--max-file-size", help="Maximum source file size to scan, in KB."),
    ] = 400,
    max_files: Annotated[
        int,
        typer.Option("--max-files", help="Maximum supported source files to scan."),
    ] = 2000,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable JSON instead of the Rich report."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose", "-v", help="Show every per-file signal that contributed to scores."
        ),
    ] = False,
    ml_model: Annotated[
        Path | None,
        typer.Option("--ml-model", help="Optional experimental GitZero joblib model artifact."),
    ] = None,
) -> None:
    """Scan a repository and print a GitZero report."""

    excludes = tuple(exclude or ())
    _validate_scan_limits(max_file_size=max_file_size, max_files=max_files)
    ml_artifact = _load_ml_model_or_exit(ml_model) if ml_model is not None else None

    try:
        with ExitStack() as stack:
            if json_output:
                repository = stack.enter_context(load_repository(target))
            else:
                with console.status("[bold cyan]Loading repository...[/]"):
                    repository = stack.enter_context(load_repository(target))

            if json_output:
                _run_scan(
                    repository=repository,
                    no_git_history=no_git_history,
                    excludes=excludes,
                    max_file_size=max_file_size,
                    max_files=max_files,
                    json_output=True,
                    ml_model=ml_model,
                    ml_artifact=ml_artifact,
                )
                return

            result = _collect_scan_with_progress(
                repo_path=repository.path,
                no_git_history=no_git_history,
                excludes=excludes,
                max_file_size=max_file_size,
                max_files=max_files,
            )
            git_findings, static_result, score = result
            ml_prediction = _predict_ml_or_exit(
                ml_model=ml_model,
                ml_artifact=ml_artifact,
                repo_path=repository.path,
                score=score,
                static_result=static_result,
                git_findings=git_findings,
                git_history_enabled=not no_git_history,
            )
            render_report(
                console,
                repository=repository,
                score=score,
                static_result=static_result,
                git_findings=git_findings,
                git_history_enabled=not no_git_history,
                verbose=verbose,
                ml_prediction=ml_prediction,
            )
    except RepositoryLoadError as exc:
        console.print(f"[red]Could not load repository:[/] {exc}")
        raise typer.Exit(1) from exc


@app.command()
def batch(
    repos_folder: Annotated[str, typer.Argument(help="Folder containing repositories to scan.")],
    output_format: Annotated[
        str,
        typer.Option("--format", help="Batch export format: jsonl or csv."),
    ] = "jsonl",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional output file. Defaults to stdout."),
    ] = None,
    label_file: Annotated[
        Path | None,
        typer.Option("--labels", help="Optional CSV/JSON/JSONL file mapping repo to label."),
    ] = None,
    label_from_parent: Annotated[
        bool,
        typer.Option("--label-from-parent", help="Use parent folder name as label."),
    ] = False,
    recursive: Annotated[
        bool,
        typer.Option("--recursive", help="Discover repositories below nested label folders."),
    ] = False,
    no_git_history: Annotated[
        bool,
        typer.Option("--no-git-history", help="Skip commit-history analysis."),
    ] = False,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", "-x", help="Glob or directory name to exclude."),
    ] = None,
    max_file_size: Annotated[
        int,
        typer.Option("--max-file-size", help="Maximum source file size to scan, in KB."),
    ] = 400,
    max_files: Annotated[
        int,
        typer.Option("--max-files", help="Maximum supported source files to scan per repo."),
    ] = 2000,
) -> None:
    """Scan a folder of repositories and export one training row per repo."""

    if output_format not in {"jsonl", "csv"}:
        console.print("[red]--format must be jsonl or csv.[/]")
        raise typer.Exit(2)
    _validate_scan_limits(max_file_size=max_file_size, max_files=max_files)

    root_path = Path(repos_folder).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        console.print(f"[red]Batch folder does not exist:[/] {root_path}")
        raise typer.Exit(1)

    labels = load_labels(label_file)
    rows = []
    repo_dirs = discover_repo_dirs(root_path, recursive=recursive)
    for repo_path in repo_dirs:
        git_findings, static_result, score = _collect_scan(
            repo_path=repo_path,
            no_git_history=no_git_history,
            excludes=tuple(exclude or ()),
            max_file_size=max_file_size,
            max_files=max_files,
        )
        rows.append(
            build_batch_row(
                repo_path=repo_path,
                root_path=root_path,
                label=label_for_repo(
                    repo_path,
                    root_path=root_path,
                    labels=labels,
                    label_from_parent=label_from_parent,
                ),
                score=score,
                static_result=static_result,
                git_findings=git_findings,
                git_history_enabled=not no_git_history,
            )
        )

    text = write_rows(rows, output_format=output_format, output=output)
    if output is None:
        stdout.write(text)
    else:
        console.print(f"[green]Wrote {len(rows)} rows to {output}[/]")


@app.command(name="fixtures")
def fixtures_command(
    output_dir: Annotated[str, typer.Argument(help="Directory to create the fixture corpus in.")],
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace the output directory if it already has files."),
    ] = False,
) -> None:
    """Create a labeled local fixture corpus for calibration and training exports."""

    target = Path(output_dir).expanduser().resolve()
    try:
        created = create_fixture_corpus(target, force=force)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc
    console.print(f"[green]Created {len(created)} fixture repos in {target}[/]")


def _run_scan(
    *,
    repository: LoadedRepository,
    no_git_history: bool,
    excludes: tuple[str, ...],
    max_file_size: int,
    max_files: int,
    json_output: bool,
    ml_model: Path | None,
    ml_artifact: dict | None,
) -> None:
    git_findings, static_result, score = _collect_scan(
        repo_path=repository.path,
        no_git_history=no_git_history,
        excludes=excludes,
        max_file_size=max_file_size,
        max_files=max_files,
    )
    ml_prediction = _predict_ml_or_exit(
        ml_model=ml_model,
        ml_artifact=ml_artifact,
        repo_path=repository.path,
        score=score,
        static_result=static_result,
        git_findings=git_findings,
        git_history_enabled=not no_git_history,
    )
    if json_output:
        stdout.write(
            report_to_json(
                repository=repository,
                score=score,
                static_result=static_result,
                git_findings=git_findings,
                git_history_enabled=not no_git_history,
                ml_prediction=ml_prediction,
            )
        )
        stdout.write("\n")


def _load_ml_model_or_exit(path: Path) -> dict:
    model_path = path.expanduser().resolve()
    if not model_path.exists():
        console.print(f"[red]ML model does not exist:[/] {model_path}")
        raise typer.Exit(1)
    try:
        return load_model_artifact(model_path)
    except (RuntimeError, ValueError, OSError) as exc:
        console.print(f"[red]Could not load ML model:[/] {exc}")
        raise typer.Exit(1) from exc


def _predict_ml_or_exit(
    *,
    ml_model: Path | None,
    ml_artifact: dict | None,
    repo_path: Path,
    score,
    static_result,
    git_findings,
    git_history_enabled: bool,
):
    if ml_model is None or ml_artifact is None:
        return None
    model_path = ml_model.expanduser().resolve()
    try:
        return predict_from_scan(
            artifact=ml_artifact,
            artifact_path=model_path,
            repo_path=repo_path,
            score=score,
            static_result=static_result,
            git_findings=git_findings,
            git_history_enabled=git_history_enabled,
        )
    except (RuntimeError, ValueError, OSError, AttributeError) as exc:
        console.print(f"[red]Could not run ML model:[/] {exc}")
        raise typer.Exit(1) from exc


def _collect_scan(
    *,
    repo_path: Path,
    no_git_history: bool,
    excludes: tuple[str, ...],
    max_file_size: int,
    max_files: int,
):
    git_findings = () if no_git_history else analyze_git_history(repo_path)
    static_result = analyze_static_code(
        repo_path,
        excludes=excludes,
        max_file_size_kb=max_file_size,
        max_files=max_files,
    )
    score = build_score_summary(
        git_findings,
        static_result,
        git_history_enabled=not no_git_history,
    )
    return git_findings, static_result, score


def _collect_scan_with_progress(
    *,
    repo_path: Path,
    no_git_history: bool,
    excludes: tuple[str, ...],
    max_file_size: int,
    max_files: int,
):
    if no_git_history:
        git_findings = ()
    else:
        with console.status("[bold cyan]Reading git history...[/]"):
            git_findings = analyze_git_history(repo_path)

    with console.status("[bold cyan]Preparing source file index...[/]"):
        source_candidates = collect_static_candidates(repo_path, excludes=excludes)

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
            excludes=excludes,
            max_file_size_kb=max_file_size,
            max_files=max_files,
            source_candidates=source_candidates,
            progress_callback=advance,
        )
        if not source_candidates:
            progress.update(task_id, completed=progress_total)

    with console.status("[bold cyan]Scoring signals...[/]"):
        score = build_score_summary(
            git_findings,
            static_result,
            git_history_enabled=not no_git_history,
        )
    return git_findings, static_result, score


def _validate_scan_limits(*, max_file_size: int, max_files: int) -> None:
    if max_file_size <= 0:
        console.print("[red]--max-file-size must be greater than zero.[/]")
        raise typer.Exit(2)
    if max_files <= 0:
        console.print("[red]--max-files must be greater than zero.[/]")
        raise typer.Exit(2)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
