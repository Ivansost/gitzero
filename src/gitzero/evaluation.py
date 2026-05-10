from __future__ import annotations

import csv
import json
import subprocess
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import ScoreSummary, SignalFinding, StaticAnalysisResult


def discover_repo_dirs(root: Path, *, recursive: bool = False) -> tuple[Path, ...]:
    """Return child directories that look like repositories or source folders."""

    candidates = []
    if recursive:
        candidates.extend(_discover_repo_dirs_recursive(root))
    else:
        for path in sorted(root.iterdir()):
            if not path.is_dir() or _is_batch_admin_dir(path):
                continue
            if _looks_like_repo_or_source(path):
                candidates.append(path)
    return tuple(candidates)


def load_labels(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in data.items()}
    if path.suffix.lower() == ".jsonl":
        labels: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            labels[str(item.get("repo", item.get("name", "")))] = str(item.get("label", ""))
        return {key: value for key, value in labels.items() if key and value}

    labels = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = row.get("repo") or row.get("name") or row.get("repository")
            label = row.get("label")
            if name and label:
                labels[name] = label
    return labels


def build_batch_row(
    *,
    repo_path: Path,
    root_path: Path,
    label: str,
    score: ScoreSummary,
    static_result: StaticAnalysisResult,
    git_findings: tuple[SignalFinding, ...],
    git_history_enabled: bool,
) -> dict[str, Any]:
    top_signals = [finding.id for finding in score.top_findings]
    dampeners = [finding.id for finding in score.dampening_findings]
    row = {
        "repo": repo_path.name,
        "path": str(repo_path),
        "relative_path": repo_path.relative_to(root_path).as_posix(),
        "label": label,
        "risk_score": score.overall_score,
        "risk_band": score.risk_band,
        "confidence_score": score.confidence_score,
        "dampening_score": score.dampening_score,
        "static_score": score.static_score,
        "git_score": score.git_score,
        "files_indexed": static_result.files_indexed,
        "files_scanned": static_result.files_scanned,
        "files_skipped": static_result.files_skipped,
        "skipped_by_reason": static_result.skipped_by_reason,
        "lines_scanned": static_result.total_lines,
        "git_history_enabled": git_history_enabled,
        "git_commit_count": count_git_commits(repo_path),
        "top_signals": top_signals,
        "top_signal_details": [asdict(finding) for finding in score.top_findings],
        "dampeners": dampeners,
        "dampener_details": [asdict(finding) for finding in score.dampening_findings],
        "git_signal_count": len(git_findings),
        "static_signal_count": len(static_result.findings),
    }
    row.update(_signal_feature_columns([*git_findings, *static_result.findings]))
    return row


def write_rows(rows: Iterable[dict[str, Any]], *, output_format: str, output: Path | None) -> str:
    materialized = list(rows)
    if output_format == "jsonl":
        text = "\n".join(json.dumps(row, sort_keys=True) for row in materialized)
        if text:
            text += "\n"
    elif output_format == "csv":
        text = _rows_to_csv(materialized)
    else:
        raise ValueError(f"Unsupported batch format: {output_format}")

    if output is not None:
        output.write_text(text, encoding="utf-8")
    return text


def count_git_commits(repo_path: Path) -> int:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-list", "--count", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return 0
    if result.returncode != 0:
        return 0
    output = result.stdout.strip()
    return int(output) if output.isdigit() else 0


def label_for_repo(
    repo_path: Path,
    *,
    root_path: Path,
    labels: dict[str, str],
    label_from_parent: bool,
) -> str:
    if repo_path.name in labels:
        return labels[repo_path.name]
    relative = repo_path.relative_to(root_path).as_posix()
    if relative in labels:
        return labels[relative]
    if label_from_parent and repo_path.parent != root_path:
        return repo_path.parent.name
    return ""


def _rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    fieldnames = _union_fieldnames(rows)
    from io import StringIO

    handle = StringIO()
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            }
        )
    return handle.getvalue()


def _signal_feature_columns(findings: list[SignalFinding]) -> dict[str, float | int]:
    features: dict[str, float | int] = {}
    strongest_by_id: dict[str, SignalFinding] = {}
    for finding in findings:
        existing = strongest_by_id.get(finding.id)
        if existing is None or finding.score * finding.weight > existing.score * existing.weight:
            strongest_by_id[finding.id] = finding

    for signal_id, finding in strongest_by_id.items():
        prefix = f"signal.{signal_id}"
        features[f"{prefix}_present"] = 1
        features[f"{prefix}_score"] = round(float(finding.score), 4)
        features[f"{prefix}_weight"] = round(float(finding.weight), 4)
    return features


def _union_fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key in seen:
                continue
            seen.add(key)
            fieldnames.append(key)
    return fieldnames


def _looks_like_repo_or_source(path: Path) -> bool:
    if (path / ".git").exists():
        return True
    markers = (
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "README.md",
        "src",
        "app",
        "lib",
        "tests",
    )
    return any((path / marker).exists() for marker in markers)


def _discover_repo_dirs_recursive(root: Path) -> list[Path]:
    candidates: list[Path] = []

    def visit(path: Path) -> None:
        for child in sorted(path.iterdir()):
            if not child.is_dir() or _is_batch_admin_dir(child):
                continue
            if _looks_like_repo_or_source(child):
                candidates.append(child)
                continue
            visit(child)

    visit(root)
    return candidates


def _is_batch_admin_dir(path: Path) -> bool:
    return path.name.startswith((".", "_"))
