#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

LIVE_REPOS = (
    ("hard_evidence_ai", "https://github.com/jrkoop/vcf2csv"),
    ("hard_evidence_ai", "https://github.com/RaphaelKhoury/ProgramsGeneratedByChatGPT"),
    ("hard_evidence_ai", "https://github.com/viraptor/pomodoro"),
    ("likely_ai_assisted", "https://github.com/elenalape/chef-ai"),
    ("likely_ai_assisted", "https://github.com/mckaywrigley/ai-code-translator"),
    ("likely_ai_assisted", "https://github.com/Nutlope/roomGPT"),
    ("human_oss", "https://github.com/pallets/click"),
    ("human_oss", "https://github.com/psf/requests"),
    ("human_oss", "https://github.com/pytest-dev/pytest"),
    ("small_human", "https://github.com/pypa/sampleproject"),
    ("template", "https://github.com/sveltejs/template"),
)

POSITIVE_LABELS = {"ai_assisted", "ai_generated", "hard_evidence_ai", "likely_ai_assisted"}
NEGATIVE_LABELS = {"human", "human_oss", "small_human", "template"}


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    cli = args.cli
    report_lines = ["# GitZero Accuracy Audit", ""]
    scan_rows: list[dict[str, Any]] = []

    self_default = run_scan(cli, ".", args.ml_model, args)
    self_excluded = run_scan(cli, ".", args.ml_model, args, extra_args=["--exclude", "corpus"])
    write_json(output_dir / "self_scan_default.json", self_default)
    write_json(output_dir / "self_scan_exclude_corpus.json", self_excluded)
    report_lines.extend(
        [
            "## Self Scan",
            "",
            scan_line("default", self_default),
            scan_line("--exclude corpus", self_excluded),
            "",
        ]
    )

    if not args.skip_corpus:
        corpus_path = output_dir / "corpus_features.jsonl"
        if args.corpus_features is None:
            run_command(
                [
                    cli,
                    "batch",
                    "corpus",
                    "--recursive",
                    "--label-from-parent",
                    "--format",
                    "jsonl",
                    "--output",
                    str(corpus_path),
                    "--max-files",
                    str(args.max_files),
                    "--max-file-size",
                    str(args.max_file_size),
                ]
            )
        else:
            corpus_path = args.corpus_features
        corpus_rows = load_jsonl(corpus_path)
        report_lines.extend(["## Corpus Summary", ""])
        report_lines.extend(summarize_rows(corpus_rows, label_key="label", score_key="risk_score"))
        report_lines.append("")
        report_lines.extend(outlier_lines(corpus_rows))
        report_lines.append("")

    if not args.skip_live:
        live_path = output_dir / "live_scan.jsonl"
        with live_path.open("w", encoding="utf-8") as handle:
            for expected, url in LIVE_REPOS:
                row = run_scan(cli, url, args.ml_model, args)
                row["expected"] = expected
                row["url"] = url
                handle.write(json.dumps(compact_scan_row(row), sort_keys=True) + "\n")
                scan_rows.append(row)
        report_lines.extend(["## Live GitHub Summary", ""])
        report_lines.extend(
            summarize_rows(
                [compact_scan_row(row) for row in scan_rows],
                label_key="expected",
                score_key="risk_score",
            )
        )
        report_lines.append("")

    report_path = output_dir / "accuracy_audit.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"wrote {report_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repeatable GitZero accuracy diagnostics.")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/gitzero_accuracy_audit"))
    parser.add_argument("--cli", default=".venv/bin/gitzero")
    parser.add_argument("--ml-model", type=Path, default=None)
    parser.add_argument("--max-files", type=int, default=400)
    parser.add_argument("--max-file-size", type=int, default=400)
    parser.add_argument("--corpus-features", type=Path, default=None)
    parser.add_argument("--skip-corpus", action="store_true")
    parser.add_argument("--skip-live", action="store_true", help="Skip public GitHub scans.")
    return parser.parse_args()


def run_scan(
    cli: str,
    target: str,
    ml_model: Path | None,
    args: argparse.Namespace,
    *,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    command = [
        cli,
        "scan",
        target,
        "--json",
        "--max-files",
        str(args.max_files),
        "--max-file-size",
        str(args.max_file_size),
    ]
    if ml_model is not None:
        command.extend(["--ml-model", str(ml_model)])
    if extra_args:
        command.extend(extra_args)
    output = run_command(command)
    return json.loads(output)


def run_command(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(
            f"Command failed ({result.returncode}): {' '.join(command)}\n{result.stderr}"
        )
    return result.stdout


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def scan_line(label: str, row: dict[str, Any]) -> str:
    score = row["score"]
    return (
        f"- {label}: {score['overall_score']}/100 {score['risk_band']} "
        f"(static={score['static_score']}, git={score['git_score']}, "
        f"dampening={score['dampening_score']})"
    )


def summarize_rows(
    rows: list[dict[str, Any]],
    *,
    label_key: str,
    score_key: str,
) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(label_key, ""))].append(row)

    lines = [
        "| Label | Count | Low | Medium | High | Average |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, items in sorted(grouped.items()):
        scores = [float(row.get(score_key) or 0.0) for row in items]
        bands = Counter(band_for_score(score) for score in scores)
        average = sum(scores) / len(scores) if scores else 0.0
        lines.append(
            f"| {label} | {len(items)} | {bands['Low']} | {bands['Medium']} | "
            f"{bands['High']} | {average:.1f} |"
        )
    return lines


def outlier_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines = ["## Corpus Outliers", ""]
    humanish = [row for row in rows if row.get("label") in NEGATIVE_LABELS]
    aiish = [row for row in rows if row.get("label") in POSITIVE_LABELS]
    lines.append("### Human/template rows scoring Medium or High")
    lines.extend(
        format_outliers(row for row in humanish if float(row.get("risk_score") or 0) >= 40)
    )
    lines.append("")
    lines.append("### AI rows scoring Low or Medium")
    lines.extend(format_outliers(row for row in aiish if float(row.get("risk_score") or 0) < 70))
    return lines


def format_outliers(rows: Any) -> list[str]:
    materialized = sorted(rows, key=lambda row: float(row.get("risk_score") or 0), reverse=True)
    if not materialized:
        return ["- none"]
    lines = []
    for row in materialized[:20]:
        signals = ", ".join(str(signal) for signal in row.get("top_signals", [])[:4])
        lines.append(
            f"- {row.get('label')} {row.get('relative_path')}: "
            f"{float(row.get('risk_score') or 0):.1f} ({signals})"
        )
    return lines


def compact_scan_row(row: dict[str, Any]) -> dict[str, Any]:
    score = row.get("score", {})
    ml_prediction = row.get("ml_prediction") or {}
    return {
        "expected": row.get("expected"),
        "url": row.get("url"),
        "risk_score": score.get("overall_score"),
        "risk_band": score.get("risk_band"),
        "confidence_score": score.get("confidence_score"),
        "dampening_score": score.get("dampening_score"),
        "static_score": score.get("static_score"),
        "git_score": score.get("git_score"),
        "ml_probability": ml_prediction.get("probability"),
        "ml_band": ml_prediction.get("band"),
        "top_signals": [finding.get("id") for finding in score.get("top_findings", [])],
        "dampeners": [finding.get("id") for finding in score.get("dampening_findings", [])],
    }


def band_for_score(score: float) -> str:
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


if __name__ == "__main__":
    main()
