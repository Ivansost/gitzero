#!/usr/bin/env python3
"""Export labeled repository features for ML training."""

from __future__ import annotations

import argparse
from pathlib import Path

from gitzero.evaluation import (
    build_batch_row,
    discover_repo_dirs,
    label_for_repo,
    load_labels,
    write_rows,
)
from gitzero.scanner import scan_repository


def export_features(
    root: Path,
    output: Path,
    *,
    labels_path: Path | None = None,
    output_format: str = "jsonl",
    max_files: int = 2000,
    max_file_size: int = 400,
) -> int:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Corpus folder does not exist: {root}")
    labels = load_labels(labels_path)
    rows = []
    for repo_path in discover_repo_dirs(root, recursive=True):
        git_findings, static_result, score = scan_repository(
            repo_path, max_files=max_files, max_file_size=max_file_size
        )
        rows.append(
            build_batch_row(
                repo_path=repo_path,
                root_path=root,
                label=label_for_repo(
                    repo_path, root_path=root, labels=labels, label_from_parent=True
                ),
                score=score,
                static_result=static_result,
                git_findings=git_findings,
                git_history_enabled=True,
            )
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    write_rows(rows, output_format=output_format, output=output)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
    args = parser.parse_args()
    try:
        count = export_features(
            args.corpus, args.output, labels_path=args.labels, output_format=args.format
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"Wrote {count} repositories to {args.output}")


if __name__ == "__main__":
    main()
