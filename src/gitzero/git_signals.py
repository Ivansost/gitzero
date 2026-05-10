from __future__ import annotations

import re
import statistics
import subprocess
from collections import Counter
from pathlib import Path

from .models import CommitMetric, SignalFinding
from .repo_loader import is_git_repository

FORMULAIC_COMMIT_VERBS = {
    "add",
    "build",
    "create",
    "fix",
    "implement",
    "improve",
    "init",
    "initial",
    "refactor",
    "remove",
    "setup",
    "update",
}
PROJECT_SKELETON_NAMES = {
    "api",
    "app",
    "components",
    "config",
    "controllers",
    "hooks",
    "lib",
    "middleware",
    "models",
    "pages",
    "routes",
    "schemas",
    "services",
    "store",
    "tests",
    "types",
    "utils",
    "views",
}
COMMON_COMMIT_TYPOS = {
    "adress",
    "alot",
    "behaviourr",
    "calcualte",
    "comit",
    "documetn",
    "feture",
    "fucntion",
    "implment",
    "occured",
    "recieve",
    "seperate",
    "teh",
    "udpate",
}
KNOWN_LIBRARY_FILENAMES = {
    "angular.js",
    "angular.min.js",
    "bootstrap.bundle.js",
    "bootstrap.js",
    "bootstrap.min.js",
    "bootstrap-colorpicker.js",
    "crypto-js.js",
    "crypto.js",
    "jquery.js",
    "jquery.min.js",
    "lodash.js",
    "lodash.min.js",
    "react.development.js",
    "react.production.min.js",
    "vue.js",
    "vue.min.js",
}
VENDORED_PATH_MARKERS = (
    "/assets/js/",
    "/bower_components/",
    "/html/js/",
    "/public/js/",
    "/static/js/",
    "/vendor/",
)


def analyze_git_history(repo_path: Path) -> tuple[SignalFinding, ...]:
    """Analyze commit history for behavioral signals consistent with AI-assisted dumps."""

    if not is_git_repository(repo_path):
        return (
            SignalFinding(
                id="git.no_history",
                title="No git history available",
                category="git",
                score=30,
                weight=0.5,
                detail=(
                    "GitZero could not inspect commit behavior, so the report relies "
                    "on static code signals."
                ),
            ),
        )

    metrics = _load_commit_metrics(repo_path)
    if not metrics:
        return (
            SignalFinding(
                id="git.empty_history",
                title="No commits found",
                category="git",
                score=20,
                weight=0.4,
                detail="The repository appears to have no commits to inspect.",
            ),
        )

    findings: list[SignalFinding] = []
    findings.extend(_large_commit_findings(metrics))
    findings.extend(_file_creation_findings(metrics))
    findings.extend(_timing_findings(metrics))
    findings.extend(_single_drop_findings(metrics))
    findings.extend(_commit_message_findings(metrics))
    findings.extend(_commit_typo_findings(metrics))
    findings.extend(_author_uniformity_findings(metrics))
    findings.extend(_merge_commit_findings(metrics))
    findings.extend(_commit_hour_findings(metrics))
    findings.extend(_diff_shape_findings(metrics))
    findings.extend(_organic_history_dampeners(metrics))
    findings.extend(_file_creation_symmetry_findings(repo_path, metrics))
    return tuple(findings)


def _load_commit_metrics(repo_path: Path) -> tuple[CommitMetric, ...]:
    pydriller_metrics = _load_with_pydriller(repo_path)
    if pydriller_metrics is not None:
        return pydriller_metrics
    return _load_with_git(repo_path)


def _load_with_pydriller(repo_path: Path) -> tuple[CommitMetric, ...] | None:
    try:
        from pydriller import Repository  # type: ignore
    except Exception:
        return None

    metrics: list[CommitMetric] = []
    try:
        commits = list(Repository(str(repo_path), order="reverse").traverse_commits())
        for commit in commits:
            files_created = 0
            files_changed = 0
            lines_added = 0
            lines_deleted = 0
            files_touched: list[str] = []
            files_created_paths: list[str] = []
            for modified in commit.modified_files:
                files_changed += 1
                lines_added += int(getattr(modified, "added_lines", 0) or 0)
                lines_deleted += int(getattr(modified, "deleted_lines", 0) or 0)
                change_type = str(getattr(modified, "change_type", "")).upper()
                new_path = getattr(modified, "new_path", None)
                old_path = getattr(modified, "old_path", None)
                path_text = (new_path or old_path or "").strip()
                if path_text:
                    files_touched.append(path_text)
                if "ADD" in change_type:
                    files_created += 1
                    if path_text:
                        files_created_paths.append(path_text)
            timestamp = int(commit.author_date.timestamp()) if commit.author_date else None
            author = getattr(commit, "author", None)
            metrics.append(
                CommitMetric(
                    sha=commit.hash,
                    timestamp=timestamp,
                    files_changed=files_changed,
                    lines_added=lines_added,
                    lines_deleted=lines_deleted,
                    files_created=files_created,
                    message=(getattr(commit, "msg", "") or "").strip(),
                    author_name=(getattr(author, "name", "") or "").strip(),
                    author_email=(getattr(author, "email", "") or "").strip(),
                    parent_count=len(getattr(commit, "parents", ()) or ()),
                    files_touched=tuple(files_touched),
                    files_created_paths=tuple(files_created_paths),
                )
            )
    except Exception:
        return None
    return tuple(metrics)


def _load_with_git(repo_path: Path) -> tuple[CommitMetric, ...]:
    revs = _git(repo_path, ["rev-list", "--reverse", "HEAD"])
    if not revs:
        return ()

    metrics: list[CommitMetric] = []
    for sha in revs.splitlines():
        metadata = _git(repo_path, ["show", "-s", "--format=%ct%x00%an%x00%ae%x00%s", sha])
        parts = metadata.split("\x00", 3)
        timestamp = int(parts[0]) if parts and parts[0].isdigit() else None
        author_name = parts[1].strip() if len(parts) > 1 else ""
        author_email = parts[2].strip() if len(parts) > 2 else ""
        message = parts[3].strip() if len(parts) > 3 else ""
        parents = _git(repo_path, ["show", "-s", "--format=%P", sha])
        parent_count = len(parents.split()) if parents else 0

        numstat = _git(repo_path, ["show", "--numstat", "--format=", "--find-renames", sha])
        files_changed = 0
        lines_added = 0
        lines_deleted = 0
        files_touched: list[str] = []
        for line in numstat.splitlines():
            parts = line.split("	")
            if len(parts) < 3:
                continue
            added, deleted = parts[0], parts[1]
            files_touched.append(_normalize_git_path(parts[2]))
            files_changed += 1
            if added.isdigit():
                lines_added += int(added)
            if deleted.isdigit():
                lines_deleted += int(deleted)

        name_status = _git(
            repo_path,
            ["diff-tree", "--root", "--no-commit-id", "--name-status", "-r", sha],
        )
        files_created_paths = [
            _normalize_git_path(line.split("	", 1)[1])
            for line in name_status.splitlines()
            if line.startswith("A	") and "	" in line
        ]
        files_created = len(files_created_paths)
        metrics.append(
            CommitMetric(
                sha=sha,
                timestamp=timestamp,
                files_changed=files_changed,
                lines_added=lines_added,
                lines_deleted=lines_deleted,
                files_created=files_created,
                message=message,
                author_name=author_name,
                author_email=author_email,
                parent_count=parent_count,
                files_touched=tuple(path for path in files_touched if path),
                files_created_paths=tuple(path for path in files_created_paths if path),
            )
        )
    return tuple(metrics)


def _git(repo_path: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _normalize_git_path(path: str) -> str:
    path = path.strip()
    if " => " in path:
        path = path.split(" => ", 1)[1]
    return path.strip("{}")


def _large_commit_findings(metrics: tuple[CommitMetric, ...]) -> list[SignalFinding]:
    changes = [metric.lines_changed for metric in metrics]
    max_change = max(changes)
    avg_change = statistics.mean(changes)
    large_commits = [change for change in changes if change >= 500]
    large_ratio = len(large_commits) / len(changes)
    findings: list[SignalFinding] = []

    if max_change >= 500 or avg_change >= 180:
        score = min(100.0, max(max_change / 15, avg_change / 4, large_ratio * 100))
        weight = 1.4
        detail_suffix = ""
        first_commit = metrics[0]
        subsequent_changes = [metric.lines_changed for metric in metrics[1:]]
        subsequent_avg = statistics.mean(subsequent_changes) if subsequent_changes else 0.0
        if first_commit.lines_changed == max_change:
            if len(metrics) <= 3:
                score = min(100.0, score * 1.2)
                detail_suffix = " The largest change is an initial one-or-two-drop import."
            elif len(metrics) > 5 and subsequent_avg < 150:
                score = min(score, 70.0)
                weight = 0.95
                detail_suffix = (
                    " The largest change is the initial import, followed by much smaller "
                    "commits; this is weaker than repeated large drops."
                )
        findings.append(
            SignalFinding(
                id="git.large_commits",
                title="Large commit bursts",
                category="git",
                score=score,
                weight=weight,
                detail=(
                    f"Max commit changed {max_change:,} lines; average commit changed "
                    f"{avg_change:,.0f} lines.{detail_suffix}"
                ),
            )
        )
    return findings


def _file_creation_findings(metrics: tuple[CommitMetric, ...]) -> list[SignalFinding]:
    max_created = max(metric.files_created for metric in metrics)
    avg_created = statistics.mean(metric.files_created for metric in metrics)
    total_files_created = sum(metric.files_created for metric in metrics)
    threshold = max(20, int(total_files_created * 0.15))
    if max_created < threshold:
        return []

    score = min(100.0, max_created * 5 + avg_created * 3)
    return [
        SignalFinding(
            id="git.file_creation_wave",
            title="Many files appeared at once",
            category="git",
            score=score,
            weight=1.2,
            detail=(
                f"One commit created {max_created} files; average created per commit "
                f"is {avg_created:.1f}; threshold for this repo was {threshold}."
            ),
        )
    ]


def _timing_findings(metrics: tuple[CommitMetric, ...]) -> list[SignalFinding]:
    timestamps = [metric.timestamp for metric in metrics if metric.timestamp is not None]
    if len(timestamps) < 2:
        return []

    gaps = [later - earlier for earlier, later in zip(timestamps, timestamps[1:], strict=False)]
    short_gaps = [gap for gap in gaps if 0 <= gap <= 20 * 60]
    total_changed_after_short_gap = sum(
        metric.lines_changed
        for metric, gap in zip(metrics[1:], gaps, strict=False)
        if 0 <= gap <= 20 * 60 and metric.lines_changed >= 200
    )
    findings: list[SignalFinding] = []
    if short_gaps and total_changed_after_short_gap >= 400:
        score = min(100.0, 45 + len(short_gaps) * 12 + total_changed_after_short_gap / 80)
        findings.append(
            SignalFinding(
                id="git.bursty_timing",
                title="Bursty commit timing",
                category="git",
                score=score,
                weight=1.0,
                detail=(
                    f"{len(short_gaps)} short commit gaps carried "
                    f"{total_changed_after_short_gap:,} changed lines."
                ),
            )
        )

    span = max(timestamps) - min(timestamps)
    total_changed = sum(metric.lines_changed for metric in metrics)
    if len(metrics) >= 2 and span <= 3 * 60 * 60 and total_changed >= 1500:
        findings.append(
            SignalFinding(
                id="git.short_project_span",
                title="Large project landed in a short time window",
                category="git",
                score=min(100.0, 55 + total_changed / 120),
                weight=1.1,
                detail=(
                    f"{total_changed:,} changed lines landed across {len(metrics)} "
                    "commits in under 3 hours."
                ),
            )
        )
    return findings


def _single_drop_findings(metrics: tuple[CommitMetric, ...]) -> list[SignalFinding]:
    total_added = sum(metric.lines_added for metric in metrics)
    total_files_created = sum(metric.files_created for metric in metrics)
    if len(metrics) <= 2 and (total_added >= 1000 or total_files_created >= 20):
        return [
            SignalFinding(
                id="git.single_drop_repo",
                title="Repository appears in one or two drops",
                category="git",
                score=min(100.0, 60 + total_added / 100 + total_files_created),
                weight=1.3,
                detail=(
                    f"{total_added:,} added lines and {total_files_created} created files "
                    f"across {len(metrics)} commits."
                ),
            )
        ]
    return []


def _commit_message_findings(metrics: tuple[CommitMetric, ...]) -> list[SignalFinding]:
    messages = [metric.message.strip() for metric in metrics if metric.message.strip()]
    if len(messages) < 4:
        return []

    first_words = [_first_word(message) for message in messages]
    first_word_counts = Counter(word for word in first_words if word)
    dominant_word, dominant_count = first_word_counts.most_common(1)[0]
    dominant_ratio = dominant_count / len(messages)
    formulaic_ratio = sum(word in FORMULAIC_COMMIT_VERBS for word in first_words) / len(messages)
    words = [
        word
        for message in messages
        for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]*", message.lower())
    ]
    vocabulary_diversity = len(set(words)) / max(len(words), 1)
    avg_length = statistics.mean(len(message.split()) for message in messages)

    findings: list[SignalFinding] = []
    if dominant_ratio >= 0.45 or formulaic_ratio >= 0.75 or vocabulary_diversity <= 0.45:
        score = min(
            100.0, dominant_ratio * 55 + formulaic_ratio * 45 + (0.5 - vocabulary_diversity) * 80
        )
        findings.append(
            SignalFinding(
                id="git.commit_message_uniformity",
                title="Commit messages look formulaic",
                category="git",
                score=score,
                weight=0.9,
                detail=(
                    f"{formulaic_ratio:.0%} start with common action verbs; "
                    f"'{dominant_word}' starts {dominant_ratio:.0%}; "
                    f"vocabulary diversity is {vocabulary_diversity:.0%}."
                ),
            )
        )

    if avg_length <= 3.2 and formulaic_ratio >= 0.5:
        findings.append(
            SignalFinding(
                id="git.short_generic_messages",
                title="Commit messages are short and generic",
                category="git",
                score=min(100.0, 35 + formulaic_ratio * 50),
                weight=0.5,
                detail=f"Average message length is {avg_length:.1f} words.",
            )
        )
    return findings


def _commit_typo_findings(metrics: tuple[CommitMetric, ...]) -> list[SignalFinding]:
    messages = [metric.message.strip().lower() for metric in metrics if metric.message.strip()]
    words = [
        word
        for message in messages
        for word in re.findall(r"[a-z][a-z']{2,}", message)
        if not re.search(r"\d|[_/.-]", word)
    ]
    if len(messages) < 10 or len(words) < 35:
        return []

    typos = sorted(set(words) & COMMON_COMMIT_TYPOS)
    if typos:
        return [
            SignalFinding(
                id="dampener.git.commit_typos_present",
                title="Commit messages contain human typos",
                category="dampener",
                score=min(55.0, 20 + len(typos) * 8),
                weight=0.25,
                detail=f"Found common typo patterns in commit messages: {', '.join(typos[:6])}.",
            )
        ]

    return [
        SignalFinding(
            id="git.no_commit_typos",
            title="No obvious typos in commit messages",
            category="git",
            score=min(45.0, 20 + len(messages) * 1.5),
            weight=0.2,
            detail=(
                f"No common typo patterns were found across {len(messages)} commit messages. "
                "This is a weak signal and can also reflect careful editing."
            ),
        )
    ]


def _author_uniformity_findings(metrics: tuple[CommitMetric, ...]) -> list[SignalFinding]:
    authors = {
        (metric.author_name.lower().strip(), metric.author_email.lower().strip())
        for metric in metrics
        if metric.author_name or metric.author_email
    }
    if len(metrics) < 5 or len(authors) != 1:
        return []

    total_changed = sum(metric.lines_changed for metric in metrics)
    score = min(70.0, 25 + len(metrics) * 2 + total_changed / 300)
    return [
        SignalFinding(
            id="git.single_author_history",
            title="Commit history has one author",
            category="git",
            score=score,
            weight=0.45,
            detail=(
                f"All {len(metrics)} commits have the same author. This is weak alone, "
                "but useful with other signals."
            ),
        )
    ]


def _merge_commit_findings(metrics: tuple[CommitMetric, ...]) -> list[SignalFinding]:
    merge_count = sum(metric.parent_count > 1 for metric in metrics)
    if merge_count > 0 and len(metrics) >= 5:
        merge_ratio = merge_count / len(metrics)
        return [
            SignalFinding(
                id="dampener.git.merge_commits_present",
                title="Merge commits suggest collaborative workflow",
                category="dampener",
                score=min(70.0, 25 + merge_ratio * 250),
                weight=0.5,
                detail=f"{merge_count} of {len(metrics)} commits are merge commits.",
                evidence_count=merge_count,
                risk_impact="lowers",
            )
        ]

    if len(metrics) < 20:
        return []

    if merge_count == 0:
        return [
            SignalFinding(
                id="git.no_merge_commits",
                title="No merge commits in a longer history",
                category="git",
                score=min(70.0, 35 + len(metrics) * 0.9),
                weight=0.45,
                detail=(
                    f"{len(metrics)} commits contain no merge commits. This can also be normal "
                    "for solo projects or repositories using linear history."
                ),
            )
        ]
    return []


def _commit_hour_findings(metrics: tuple[CommitMetric, ...]) -> list[SignalFinding]:
    timestamps = [metric.timestamp for metric in metrics if metric.timestamp is not None]
    hours = [
        int(metric.timestamp // 3600 % 24) for metric in metrics if metric.timestamp is not None
    ]
    if len(hours) < 6:
        return []

    findings: list[SignalFinding] = []
    if len(timestamps) >= 6 and max(timestamps) - min(timestamps) <= 2 * 60 * 60:
        findings.append(
            SignalFinding(
                id="git.two_hour_history_window",
                title="All commits land within a two-hour window",
                category="git",
                score=min(85.0, 45 + len(timestamps) * 3),
                weight=0.65,
                detail=f"{len(timestamps)} commits were authored within two hours.",
            )
        )

    hour_counts = Counter(hours)
    dominant_hour, dominant_count = hour_counts.most_common(1)[0]
    dominant_ratio = dominant_count / len(hours)
    night_ratio = sum(hour_counts[hour] for hour in [0, 1, 2, 3, 4, 5]) / len(hours)
    if dominant_ratio < 0.55 and night_ratio < 0.65:
        return findings

    score = min(75.0, dominant_ratio * 50 + night_ratio * 35)
    findings.append(
        SignalFinding(
            id="git.commit_time_distribution",
            title="Commit times are tightly clustered",
            category="git",
            score=score,
            weight=0.4,
            detail=(
                f"{dominant_ratio:.0%} of commits land in hour {dominant_hour:02d}:00; "
                f"{night_ratio:.0%} land between 00:00 and 05:59 UTC."
            ),
        )
    )
    return findings


def _diff_shape_findings(metrics: tuple[CommitMetric, ...]) -> list[SignalFinding]:
    findings: list[SignalFinding] = []
    broad_commits: list[tuple[CommitMetric, set[str], int]] = []
    complete_drop_commits: list[tuple[CommitMetric, int]] = []

    for metric in metrics:
        created_paths = tuple(
            path for path in metric.files_created_paths if not _looks_like_vendor_path(path)
        )
        category_paths = created_paths or tuple(
            path for path in metric.files_touched if not _looks_like_vendor_path(path)
        )
        source_created_count = len(created_paths)
        categories = _path_categories(category_paths)
        if source_created_count >= 15 and len(categories) >= 3:
            broad_commits.append((metric, categories, source_created_count))
        if source_created_count >= 6 and {"source", "tests", "docs"} <= categories:
            complete_drop_commits.append((metric, source_created_count))

    if broad_commits:
        metric, categories, source_created_count = max(broad_commits, key=lambda item: item[2])
        findings.append(
            SignalFinding(
                id="git.diff_shape_broad_file_drop",
                title="One commit added broad unrelated areas",
                category="git",
                score=min(85.0, 35 + source_created_count * 3 + len(categories) * 4),
                weight=0.8,
                detail=(
                    f"Commit {metric.sha[:8]} created {source_created_count} non-vendored "
                    "files across "
                    f"{', '.join(sorted(categories))}."
                ),
            )
        )

    if complete_drop_commits:
        metric, source_created_count = max(complete_drop_commits, key=lambda item: item[1])
        findings.append(
            SignalFinding(
                id="git.diff_shape_complete_stack_drop",
                title="Code, tests, and docs landed together",
                category="git",
                score=min(80.0, 32 + source_created_count * 3),
                weight=0.55,
                detail=(
                    f"Commit {metric.sha[:8]} created source, test, and documentation files "
                    f"in the same {source_created_count}-file change."
                ),
            )
        )

    created_paths = [
        path
        for metric in metrics
        for path in metric.files_created_paths
        if _source_like_path(path) and not _looks_like_vendor_path(path)
    ]
    if len(created_paths) >= 8:
        touch_counts = Counter(path for metric in metrics for path in metric.files_touched)
        touched_once = [path for path in created_paths if touch_counts.get(path, 0) <= 1]
        untouched_ratio = len(touched_once) / len(created_paths)
        if untouched_ratio >= 0.8:
            findings.append(
                SignalFinding(
                    id="git.diff_shape_files_rarely_reworked",
                    title="Created files were rarely reworked",
                    category="git",
                    score=min(85.0, 35 + untouched_ratio * 50 + len(created_paths) / 3),
                    weight=0.6,
                    detail=(
                        f"{len(touched_once)} of {len(created_paths)} created source files "
                        "were not modified again."
                    ),
                )
            )

    return findings


def _organic_history_dampeners(metrics: tuple[CommitMetric, ...]) -> list[SignalFinding]:
    findings: list[SignalFinding] = []
    timestamps = [metric.timestamp for metric in metrics if metric.timestamp is not None]
    if len(timestamps) >= 10:
        span_days = (max(timestamps) - min(timestamps)) / 86_400
        if span_days >= 30:
            findings.append(
                SignalFinding(
                    id="dampener.git.long_lived_history",
                    title="History spans many days",
                    category="dampener",
                    score=min(80.0, 30 + span_days / 6),
                    weight=0.55,
                    detail=f"{len(metrics)} commits span {span_days:.0f} days.",
                )
            )

    authors = {
        (metric.author_name.lower().strip(), metric.author_email.lower().strip())
        for metric in metrics
        if metric.author_name or metric.author_email
    }
    if len(authors) >= 3 and len(metrics) >= 10:
        findings.append(
            SignalFinding(
                id="dampener.git.multi_author_history",
                title="Multiple authors in commit history",
                category="dampener",
                score=min(75.0, 25 + len(authors) * 10),
                weight=0.45,
                detail=f"{len(authors)} distinct author identities appear in commit history.",
                evidence_count=len(authors),
                risk_impact="lowers",
            )
        )

    touch_counts = Counter(path for metric in metrics for path in metric.files_touched)
    reworked_paths = [path for path, count in touch_counts.items() if count >= 3]
    if len(metrics) >= 10 and len(touch_counts) >= 10:
        rework_ratio = len(reworked_paths) / len(touch_counts)
        if rework_ratio >= 0.25:
            findings.append(
                SignalFinding(
                    id="dampener.git.organic_churn",
                    title="Files show organic rework over time",
                    category="dampener",
                    score=min(75.0, 25 + rework_ratio * 120),
                    weight=0.5,
                    detail=(
                        f"{len(reworked_paths)} of {len(touch_counts)} touched files changed "
                        "in at least three commits."
                    ),
                )
            )
    return findings


def _file_creation_symmetry_findings(
    repo_path: Path,
    metrics: tuple[CommitMetric, ...],
) -> list[SignalFinding]:
    max_created = max(metric.files_created for metric in metrics)
    if max_created < 8:
        return []

    names = {path.stem.lower() for path in repo_path.rglob("*") if path.is_file()}
    skeleton_hits = sorted(names & PROJECT_SKELETON_NAMES)
    if len(skeleton_hits) < 5:
        return []

    score = min(80.0, 30 + len(skeleton_hits) * 6 + max_created)
    return [
        SignalFinding(
            id="git.project_skeleton_symmetry",
            title="Generated-looking project skeleton",
            category="git",
            score=score,
            weight=0.75,
            detail=(
                f"Repository contains scaffold-like file names ({', '.join(skeleton_hits[:8])}) "
                f"and one commit created {max_created} files."
            ),
        )
    ]


def _first_word(message: str) -> str:
    match = re.search(r"[a-zA-Z]+", message.lower())
    return match.group(0) if match else ""


def _path_categories(paths: tuple[str, ...]) -> set[str]:
    categories: set[str] = set()
    for path in paths:
        lower = path.lower()
        parts = lower.split("/")
        suffix = Path(lower).suffix
        if any(part in {"test", "tests", "__tests__", "spec", "specs"} for part in parts):
            categories.add("tests")
        elif Path(lower).name.startswith(("readme", "changelog")) or suffix in {".md", ".rst"}:
            categories.add("docs")
        elif Path(lower).name in {
            ".env.example",
            "dockerfile",
            "package.json",
            "pyproject.toml",
            "requirements.txt",
        } or suffix in {".json", ".toml", ".yaml", ".yml"}:
            categories.add("config")
        elif any(
            part in {"src", "lib", "app", "components", "pages", "services"} for part in parts
        ):
            categories.add("source")
        else:
            categories.add("other")
    return categories


def _source_like_path(path: str) -> bool:
    return Path(path.lower()).suffix in {".py", ".js", ".jsx", ".ts", ".tsx"}


def _looks_like_vendor_path(path: str) -> bool:
    lower = f"/{path.lower().strip('/')}"
    if Path(lower).name in KNOWN_LIBRARY_FILENAMES:
        return True
    return any(marker in lower for marker in VENDORED_PATH_MARKERS)
