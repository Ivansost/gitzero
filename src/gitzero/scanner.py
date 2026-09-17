from __future__ import annotations

from pathlib import Path

from .git_signals import analyze_git_history
from .models import ScoreSummary, SignalFinding, StaticAnalysisResult
from .scoring import build_score_summary
from .static_signals import analyze_static_code


def scan_repository(
    repo_path: Path,
    *,
    excludes: tuple[str, ...] = (),
    max_file_size: int = 400,
    max_files: int = 2000,
) -> tuple[tuple[SignalFinding, ...], StaticAnalysisResult, ScoreSummary]:
    """Run the same detector for the CLI and research tools."""
    if max_file_size <= 0 or max_files <= 0:
        raise ValueError("Scan limits must be greater than zero.")
    git_findings = analyze_git_history(repo_path)
    static_result = analyze_static_code(
        repo_path,
        excludes=excludes,
        max_file_size_kb=max_file_size,
        max_files=max_files,
    )
    score = build_score_summary(git_findings, static_result, git_history_enabled=True)
    return git_findings, static_result, score
