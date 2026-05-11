from __future__ import annotations

import json
from dataclasses import asdict

from .ml import MlPrediction
from .models import LoadedRepository, ScoreSummary, SignalFinding, StaticAnalysisResult

GITZERO_BANNER = r""" ____ ___ _____ _____ _____ ____   ___
 / ___|_ _|_   _|__  /| ____|  _ \ / _ \
| |  _ | |  | |   / / |  _| | |_) | | | |
| |_| || |  | |  / /_ | |___|  _ <| |_| |
 \____|___| |_| /____||_____|_| \_\\___/"""


def render_help(console) -> None:
    from rich import box
    from rich.align import Align
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    header = Text(GITZERO_BANNER, style="bold cyan")
    header.append("\nCommand guide and signal legend", style="dim")
    console.print(Panel(Align.center(header), border_style="cyan", box=box.ROUNDED))

    commands = Table(
        title="Commands",
        box=box.ROUNDED,
        show_lines=True,
        border_style="cyan",
        expand=True,
    )
    commands.add_column("Command", style="bold cyan", ratio=1)
    commands.add_column("What it does", ratio=2)
    commands.add_row(
        "gitzero scan <repo-url-or-path>",
        "Scan a public GitHub/git URL or local repository folder.",
    )
    commands.add_row(
        "gitzero help",
        "Show this command guide, flag reference, score legend, and examples.",
    )
    commands.add_row(
        "gitzero batch <repos-folder>",
        "Scan many local repositories and export JSONL or CSV rows for evaluation.",
    )
    commands.add_row(
        "gitzero fixtures <output-dir>",
        "Create a labeled local fixture corpus for calibration and training exports.",
    )
    commands.add_row(
        "gitzero --help",
        "Show Typer's built-in command reference.",
    )
    console.print(commands)

    flags = Table(
        title="Scan Flags",
        box=box.ROUNDED,
        show_lines=True,
        border_style="magenta",
        expand=True,
    )
    flags.add_column("Flag", style="bold magenta", ratio=1)
    flags.add_column("Meaning", ratio=2)
    flags.add_row(
        "--no-git-history",
        "Skip commit-history analysis and score only the current source files.",
    )
    flags.add_row(
        "--exclude, -x <pattern>",
        "Skip a directory name or glob pattern. Can be used more than once.",
    )
    flags.add_row(
        "--max-file-size <kb>",
        "Skip supported source files larger than this size. Default: 400 KB.",
    )
    flags.add_row(
        "--max-files <count>",
        "Cap supported source files scanned for large repositories. Default: 2000.",
    )
    flags.add_row(
        "--json",
        "Print machine-readable JSON instead of the Rich terminal report.",
    )
    flags.add_row(
        "--ml-model <file>",
        "Load an experimental GitZero joblib model artifact and print ML probability.",
    )
    flags.add_row(
        "--verbose, -v",
        "Show every per-file static signal that contributed to the score.",
    )
    console.print(flags)

    batch_flags = Table(
        title="Batch / Fixture Flags",
        box=box.ROUNDED,
        show_lines=True,
        border_style="magenta",
        expand=True,
    )
    batch_flags.add_column("Flag", style="bold magenta", ratio=1)
    batch_flags.add_column("Meaning", ratio=2)
    batch_flags.add_row("--format jsonl|csv", "Choose batch export format. Default: jsonl.")
    batch_flags.add_row("--output, -o <file>", "Write batch rows to a file instead of stdout.")
    batch_flags.add_row("--labels <file>", "Load repo labels from CSV, JSON, or JSONL.")
    batch_flags.add_row("--recursive", "Find repositories inside nested label folders.")
    batch_flags.add_row("--label-from-parent", "Use each repo's immediate parent folder as label.")
    batch_flags.add_row("--force", "Replace an existing non-empty fixture output directory.")
    console.print(batch_flags)

    legend = Table(
        title="Score Legend",
        box=box.ROUNDED,
        show_lines=True,
        border_style="yellow",
        expand=True,
    )
    legend.add_column("Band", style="bold", width=12)
    legend.add_column("Range", width=12)
    legend.add_column("How to read it", ratio=2)
    legend.add_row("[green]Low[/]", "0-39", "Few signals consistent with AI-assisted code.")
    legend.add_row(
        "[yellow]Medium[/]",
        "40-69",
        "Several signals are elevated; review the top findings. This is not an AI claim.",
    )
    legend.add_row(
        "[red]High[/]",
        "70-100",
        "Many signals are elevated; inspect history and files closely.",
    )
    console.print(legend)

    signals = Table(
        title="Signal Groups",
        box=box.ROUNDED,
        show_lines=True,
        border_style="blue",
        expand=True,
    )
    signals.add_column("Group", style="bold blue", ratio=1)
    signals.add_column("Examples", ratio=2)
    signals.add_row(
        "Git behavior",
        "Large commits, file creation waves, merge absence, diff shape, time clustering.",
    )
    signals.add_row(
        "Static code",
        "Debug residue, file-size variance, docstrings, type density, complexity variance.",
    )
    signals.add_row(
        "Style patterns",
        "TODO quality, tests, README alignment, dependencies, repeated error handling.",
    )
    signals.add_row(
        "False-positive guards",
        "Confidence score plus dampening signals for organic history and specific residue.",
    )
    console.print(signals)

    examples = (
        "[bold]Examples[/]\n"
        "  [cyan]gitzero scan .[/]\n"
        "  [cyan]gitzero scan ./my-repo --no-git-history[/]\n"
        "  [cyan]gitzero scan https://github.com/user/project -x node_modules -x dist[/]\n"
        "  [cyan]gitzero scan . --json[/]\n\n"
        "  [cyan]gitzero fixtures ./fixtures/gitzero-corpus[/]\n"
        "  [cyan]gitzero batch ./fixtures/gitzero-corpus --labels "
        "./fixtures/gitzero-corpus/labels.csv --format jsonl[/]\n\n"
        "  [cyan]gitzero batch ./corpus --recursive --label-from-parent "
        "--format csv -o corpus.csv[/]\n\n"
        "[dim]GitZero reports signals consistent with AI-assisted code. "
        "It does not prove who or what wrote a repository.[/]"
    )
    console.print(Panel(examples, title="Usage", border_style="dim"))


def render_report(
    console,
    *,
    repository: LoadedRepository,
    score: ScoreSummary,
    static_result: StaticAnalysisResult,
    git_findings: tuple[SignalFinding, ...],
    git_history_enabled: bool,
    verbose: bool = False,
    ml_prediction: MlPrediction | None = None,
) -> None:
    from rich import box
    from rich.align import Align
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    header = Text(GITZERO_BANNER, style="bold cyan")
    header.append("\nAI code signal scanner", style="dim")
    console.print(Panel(Align.center(header), border_style="cyan", box=box.ROUNDED))

    summary = Table.grid(expand=True)
    summary.add_column(ratio=1)
    summary.add_column(ratio=1)
    summary.add_column(ratio=1)
    summary.add_row(
        _metric("Overall", f"{score.overall_score:.1f}/100", score.risk_color),
        _metric("Risk band", score.risk_band, score.risk_color),
        _metric("Files scanned", str(static_result.files_scanned), "cyan"),
    )
    git_text = "skipped" if not git_history_enabled else _format_optional_score(score.git_score)
    summary.add_row(
        _metric("Static score", _format_optional_score(score.static_score), "magenta"),
        _metric("Git score", git_text, "blue"),
        _metric("Lines scanned", f"{static_result.total_lines:,}", "cyan"),
    )
    summary.add_row(
        _metric("Confidence", f"{score.confidence_score:.1f}/100", "cyan"),
        _metric("Dampening", f"{score.dampening_score:.1f}/100", "green"),
        _metric("Skipped files", _skipped_summary(static_result), "cyan"),
    )
    console.print(Panel(summary, title="Scan Summary", border_style="cyan"))
    if ml_prediction is not None:
        console.print(_ml_prediction_panel(ml_prediction))
    hard_evidence = _hard_evidence_finding(git_findings, static_result.findings)
    if hard_evidence is not None:
        console.print(_hard_evidence_panel(hard_evidence))
    console.print(_signal_map(score, git_history_enabled=git_history_enabled))

    findings_table = Table(
        title="Top Signals",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
        expand=True,
    )
    findings_table.add_column("Signal", style="bold")
    findings_table.add_column("Category", width=10)
    findings_table.add_column("Score", justify="right", width=8)
    findings_table.add_column("Details", ratio=2)
    for finding in score.top_findings:
        location = f" ({finding.path})" if finding.path else ""
        findings_table.add_row(
            f"{finding.title}{location}",
            finding.category,
            f"{finding.score:.0f}",
            finding.detail,
        )
    if not score.top_findings:
        findings_table.add_row("No notable signals", "-", "0", "No elevated indicators were found.")
    console.print(findings_table)

    if score.dampening_findings:
        console.print(_dampening_findings_table(score))

    file_table = Table(
        title="Highest-Signal Files",
        box=box.HORIZONTALS,
        show_lines=True,
        expand=True,
    )
    file_table.add_column("File", ratio=2)
    file_table.add_column("Lang", width=11)
    file_table.add_column("Score", justify="right", width=8)
    file_table.add_column("Notes", ratio=2)
    top_files = sorted(static_result.files, key=lambda file: file.score, reverse=True)[:10]
    for file in top_files:
        style = _score_style(file.score)
        file_table.add_row(
            file.path,
            file.language,
            f"[{style}]{file.score:.0f}[/]",
            "; ".join(file.highlights[:2]) or "No strong per-file signals",
        )
    if not top_files:
        file_table.add_row("-", "-", "0", "No supported source files were scanned.")
    console.print(file_table)

    if verbose:
        console.print(_verbose_file_findings(static_result))

    source_lines = _source_lines(repository)
    footnote = (
        "GitZero reports signals consistent with AI-assisted code. "
        "It does not prove who or what wrote the repository."
    )
    console.print(
        Panel(
            (
                f"{source_lines}\n[dim]Skipped files:[/] "
                f"{_skipped_summary(static_result)}\n\n{footnote}"
            ),
            border_style="dim",
        )
    )


def _verbose_file_findings(static_result: StaticAnalysisResult):
    from rich import box
    from rich.table import Table

    table = Table(title="Verbose File Findings", box=box.HORIZONTALS, show_lines=True, expand=True)
    table.add_column("File", ratio=2)
    table.add_column("Signal", ratio=1)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Details", ratio=2)

    rows = 0
    for file in sorted(static_result.files, key=lambda item: item.score, reverse=True):
        findings = [finding for finding in file.verbose_findings if finding.score > 0]
        for finding in findings:
            rows += 1
            table.add_row(file.path, finding.title, f"{finding.score:.0f}", finding.detail)
    if rows == 0:
        table.add_row("-", "No per-file signals", "0", "No verbose findings were triggered.")
    return table


def _dampening_findings_table(score: ScoreSummary):
    from rich import box
    from rich.table import Table

    table = Table(
        title="Dampening Signals",
        box=box.SIMPLE,
        show_lines=False,
        expand=True,
    )
    table.add_column("Signal", style="bold green")
    table.add_column("Score", justify="right", width=8)
    table.add_column("Details", ratio=2)
    for finding in score.dampening_findings:
        location = f" ({finding.path})" if finding.path else ""
        table.add_row(f"{finding.title}{location}", f"{finding.score:.0f}", finding.detail)
    return table


def _hard_evidence_finding(
    git_findings: tuple[SignalFinding, ...],
    static_findings: tuple[SignalFinding, ...],
) -> SignalFinding | None:
    for finding in [*git_findings, *static_findings]:
        if finding.id == "git.ai_config_files_present":
            return finding
    return None


def _hard_evidence_panel(finding: SignalFinding):
    from rich.panel import Panel

    return Panel(
        f"[bold red]{finding.title}[/]\n{finding.detail}",
        title="Hard Evidence",
        border_style="red",
    )


def _ml_prediction_panel(prediction: MlPrediction):
    from rich.panel import Panel

    color = _probability_style(prediction.probability)
    text = (
        f"[bold {color}]ML probability: {prediction.probability:.2f} "
        f"({prediction.band})[/]\n"
        "[dim]Experimental:[/] use as a calibration aid alongside the heuristic score.\n"
        f"[dim]Model:[/] {prediction.model_path}\n"
        f"[dim]Profile:[/] {prediction.profile} "
        f"({prediction.feature_count} features)"
    )
    return Panel(text, title="ML Model", border_style=color)


def report_to_json(
    *,
    repository: LoadedRepository,
    score: ScoreSummary,
    static_result: StaticAnalysisResult,
    git_findings: tuple[SignalFinding, ...],
    git_history_enabled: bool,
    ml_prediction: MlPrediction | None = None,
) -> str:
    payload = {
        "repository": {
            "source": repository.source,
            "path": str(repository.path),
            "temporary": repository.is_temporary,
        },
        "git_history_enabled": git_history_enabled,
        "score": asdict(score),
        "git_findings": [asdict(finding) for finding in git_findings],
        "static": asdict(static_result),
        "ml_prediction": asdict(ml_prediction) if ml_prediction is not None else None,
        "disclaimer": (
            "GitZero reports signals consistent with AI-assisted code. "
            "It does not prove who or what wrote the repository."
        ),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _metric(label: str, value: str, color: str) -> str:
    return f"[dim]{label}[/]\n[{color} bold]{value}[/]"


def _format_optional_score(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}/100"


def _skipped_summary(static_result: StaticAnalysisResult) -> str:
    if not static_result.skipped_by_reason:
        return str(static_result.files_skipped)
    parts = [
        f"{reason}={count}"
        for reason, count in sorted(static_result.skipped_by_reason.items())
        if count
    ]
    return f"{static_result.files_skipped} ({', '.join(parts)})"


def _signal_map(score: ScoreSummary, *, git_history_enabled: bool):
    from rich import box
    from rich.table import Table

    table = Table(title="Signal Map", box=box.SIMPLE, expand=True)
    table.add_column("Group", style="bold", ratio=1)
    table.add_column("Signal strength", ratio=2)
    table.add_row("Overall", _bar(score.overall_score, score.risk_color))
    table.add_row("Confidence", _bar(score.confidence_score, "cyan"))
    if git_history_enabled:
        table.add_row("Git behavior", _bar(score.git_score or 0.0, "blue"))
    else:
        table.add_row("Git behavior", "[dim]skipped[/]")
    table.add_row("Static code", _bar(score.static_score or 0.0, "magenta"))
    if score.dampening_score > 0:
        table.add_row("Dampening", _bar(score.dampening_score, "green"))
    return table


def _bar(value: float, color: str) -> str:
    filled = max(0, min(10, round(value / 10)))
    empty = 10 - filled
    return f"[{color}]{'#' * filled}{'-' * empty}[/] {value:.1f}/100"


def _source_lines(repository: LoadedRepository) -> str:
    if repository.is_temporary:
        return (
            f"[dim]Source URL:[/] {repository.source}\n"
            f"[dim]Scan copy:[/] {repository.path} "
            "[dim](temporary clone, deleted after scan)[/]"
        )
    if repository.source != str(repository.path):
        return f"[dim]Input:[/] {repository.source}\n[dim]Resolved path:[/] {repository.path}"
    return f"[dim]Source:[/] {repository.path}"


def _score_style(score: float) -> str:
    if score >= 70:
        return "red"
    if score >= 40:
        return "yellow"
    return "green"


def _probability_style(probability: float) -> str:
    if probability >= 0.85:
        return "red"
    if probability >= 0.7:
        return "yellow"
    return "green"
