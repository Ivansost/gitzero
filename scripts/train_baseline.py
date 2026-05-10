#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

POSITIVE_LABELS = {"ai_assisted", "ai_generated"}
NEGATIVE_LABELS = {"human", "template"}
METADATA_FEATURES = (
    "files_indexed",
    "files_scanned",
    "files_skipped",
    "lines_scanned",
    "git_commit_count",
    "git_signal_count",
    "static_signal_count",
)
HARD_EVIDENCE_TOKEN = "git.ai_config_files_present"
THRESHOLDS = (0.5, 0.7, 0.85)


@dataclass(frozen=True)
class Dataset:
    rows: list[dict[str, Any]]
    labels: list[int]
    groups: list[str]


@dataclass(frozen=True)
class EvaluationResult:
    name: str
    feature_columns: list[str]
    probabilities: list[float]
    fold_metrics: list[dict[str, float]]
    top_positive_features: list[tuple[str, float]]
    top_negative_features: list[tuple[str, float]]
    model: Any


def main() -> None:
    args = parse_args()
    rows = load_jsonl(args.input)
    dataset = build_dataset(rows)

    report_lines: list[str] = []
    add = report_lines.append
    add(f"input: {args.input}")
    add(f"rows: {len(dataset.rows)}")
    add("")
    add("Labels")
    for label, count in sorted(Counter(row["label"] for row in dataset.rows).items()):
        binary = "positive" if label in POSITIVE_LABELS else "negative"
        add(f"  {label}: {count} ({binary})")
    add("")
    add("Groups")
    group_counts = Counter(dataset.groups)
    repeated_groups = sum(1 for count in group_counts.values() if count > 1)
    add(f"  unique groups: {len(group_counts)}")
    add(f"  repeated groups: {repeated_groups}")
    add(f"  folds: {args.folds}")
    add("")
    add("Hard Evidence Prevalence")
    add_hard_evidence_prevalence(dataset.rows, add)
    add("")
    add("Positive Hard Evidence Details")
    add_hard_evidence_details(dataset.rows, add)

    full_features = select_feature_columns(dataset.rows, include_hard_evidence=True)
    ablation_features = select_feature_columns(dataset.rows, include_hard_evidence=False)
    raw_signal_features = select_feature_columns(
        dataset.rows,
        include_hard_evidence=False,
        include_dampener_signals=False,
    )
    risk_signal_only_features = select_feature_columns(
        dataset.rows,
        include_hard_evidence=False,
        include_dampener_signals=False,
        include_metadata=False,
    )

    results = [
        evaluate_model(
            "full_model",
            dataset,
            feature_columns=full_features,
            folds=args.folds,
            random_state=args.random_state,
        ),
        evaluate_model(
            "ablation_no_hard_evidence",
            dataset,
            feature_columns=ablation_features,
            folds=args.folds,
            random_state=args.random_state,
        ),
        evaluate_model(
            "ablation_no_hard_or_dampeners",
            dataset,
            feature_columns=raw_signal_features,
            folds=args.folds,
            random_state=args.random_state,
        ),
        evaluate_model(
            "risk_signals_only_no_hard_no_dampeners",
            dataset,
            feature_columns=risk_signal_only_features,
            folds=args.folds,
            random_state=args.random_state,
        ),
    ]

    for result in results:
        add("")
        add(f"=== {result.name} ===")
        add(f"features: {len(result.feature_columns)}")
        add_model_report(result, dataset, add)

    if args.save_model is not None:
        selected_result = result_by_name(results, args.save_profile)
        save_model_artifact(
            args.save_model,
            result=selected_result,
            dataset=dataset,
            input_path=args.input,
            random_state=args.random_state,
        )
        add("")
        add(f"Saved model: {args.save_model}")
        add(f"Saved profile: {selected_result.name}")

    report = "\n".join(report_lines) + "\n"
    print(report, end="")
    if args.report_output is not None:
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text(report, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a grouped-CV baseline model from GitZero batch JSONL features."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("corpus/_prep/corpus_features_cleaned_v4.jsonl"),
        help="GitZero batch JSONL feature file.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=Path("corpus/_prep/baseline_report_v4.txt"),
        help="Optional text report path.",
    )
    parser.add_argument("--folds", type=int, default=5, help="Grouped CV fold count.")
    parser.add_argument("--random-state", type=int, default=42, help="Model/CV random seed.")
    parser.add_argument(
        "--save-model",
        type=Path,
        default=None,
        help="Optional joblib path for a trained model artifact.",
    )
    parser.add_argument(
        "--save-profile",
        choices=(
            "full_model",
            "ablation_no_hard_evidence",
            "ablation_no_hard_or_dampeners",
            "risk_signals_only_no_hard_no_dampeners",
        ),
        default="ablation_no_hard_evidence",
        help="Which evaluated profile to save when --save-model is set.",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Input file does not exist: {path}")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows:
        raise SystemExit(f"Input file has no rows: {path}")
    return rows


def build_dataset(rows: list[dict[str, Any]]) -> Dataset:
    labels: list[int] = []
    groups: list[str] = []
    for row in rows:
        label = str(row.get("label", ""))
        if label in POSITIVE_LABELS:
            labels.append(1)
        elif label in NEGATIVE_LABELS:
            labels.append(0)
        else:
            raise SystemExit(f"Unsupported label {label!r} for repo {row.get('relative_path')}")
        groups.append(group_for_row(row))
    return Dataset(rows=rows, labels=labels, groups=groups)


def group_for_row(row: dict[str, Any]) -> str:
    label = str(row.get("label", "unknown"))
    relative_path = str(row.get("relative_path") or "")
    repo = str(row.get("repo") or relative_path.rsplit("/", maxsplit=1)[-1])
    folder_name = relative_path.split("/", maxsplit=1)[-1] if "/" in relative_path else repo
    if "__" in folder_name:
        owner, _ = folder_name.split("__", maxsplit=1)
        return f"github:{owner.lower()}"
    if label == "template":
        if folder_name.startswith("vite-"):
            return "template:vite"
        if folder_name.startswith("next-"):
            return "template:next"
        return f"template:{folder_name.split('-', maxsplit=1)[0].lower()}"
    return f"{label}:{folder_name.lower()}"


def add_hard_evidence_prevalence(rows: list[dict[str, Any]], add: Any) -> None:
    hard_present_col = f"signal.{HARD_EVIDENCE_TOKEN}_present"
    buckets = {
        "positive": [row for row in rows if row["label"] in POSITIVE_LABELS],
        "negative": [row for row in rows if row["label"] in NEGATIVE_LABELS],
    }
    for name, bucket in buckets.items():
        present = sum(1 for row in bucket if numeric_value(row.get(hard_present_col)) > 0)
        add(f"  {name}: {present}/{len(bucket)}")


def add_hard_evidence_details(rows: list[dict[str, Any]], add: Any) -> None:
    hard_present_col = f"signal.{HARD_EVIDENCE_TOKEN}_present"
    for row in rows:
        if row["label"] not in POSITIVE_LABELS:
            continue
        if numeric_value(row.get(hard_present_col)) <= 0:
            continue
        add(f"  {row['label']} {row['relative_path']}: {hard_evidence_detail(row)}")


def hard_evidence_detail(row: dict[str, Any]) -> str:
    for finding in row.get("top_signal_details", []):
        if finding.get("id") == HARD_EVIDENCE_TOKEN:
            detail = str(finding.get("detail") or "").removeprefix(
                "Found explicit AI-assistant project evidence: "
            )
            if len(detail) > 220:
                return detail[:217] + "..."
            return detail
    return "present"


def select_feature_columns(
    rows: list[dict[str, Any]],
    *,
    include_hard_evidence: bool,
    include_dampener_signals: bool = True,
    include_metadata: bool = True,
) -> list[str]:
    columns = sorted({key for row in rows for key in row if key.startswith("signal.")})
    if include_metadata:
        columns.extend(
            feature for feature in METADATA_FEATURES if any(feature in row for row in rows)
        )
    columns = sorted(dict.fromkeys(columns))
    if not include_hard_evidence:
        columns = [column for column in columns if HARD_EVIDENCE_TOKEN not in column]
    if not include_dampener_signals:
        columns = [column for column in columns if not column.startswith("signal.dampener.")]
    return columns


def evaluate_model(
    name: str,
    dataset: Dataset,
    *,
    feature_columns: list[str],
    folds: int,
    random_state: int,
) -> EvaluationResult:
    try:
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import GroupKFold, StratifiedGroupKFold
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing ML dependencies. Run: .venv/bin/python -m pip install -e '.[ml]'"
        ) from exc

    x = matrix_for_rows(dataset.rows, feature_columns)
    y = dataset.labels
    groups = dataset.groups
    split_count = safe_fold_count(folds, y, groups)
    try:
        splitter = StratifiedGroupKFold(
            n_splits=split_count,
            shuffle=True,
            random_state=random_state,
        )
        splits = list(splitter.split(x, y, groups))
    except ValueError:
        splitter = GroupKFold(n_splits=split_count)
        splits = list(splitter.split(x, y, groups))

    probabilities = [0.0 for _ in y]
    fold_metrics: list[dict[str, float]] = []
    for fold_index, (train_idx, test_idx) in enumerate(splits, start=1):
        train_x = [x[index] for index in train_idx]
        train_y = [y[index] for index in train_idx]
        test_x = [x[index] for index in test_idx]
        test_y = [y[index] for index in test_idx]
        classifier = RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=random_state + fold_index,
        )
        model = CalibratedClassifierCV(classifier, cv=3, method="sigmoid")
        model.fit(train_x, train_y)
        fold_probabilities = [float(pair[1]) for pair in model.predict_proba(test_x)]
        for index, probability in zip(test_idx, fold_probabilities, strict=True):
            probabilities[index] = probability
        fold_metrics.append(metric_summary(test_y, fold_probabilities))

    final_model = RandomForestClassifier(
        n_estimators=500,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=random_state,
    )
    final_model.fit(x, y)
    importances = list(final_model.feature_importances_)
    top_positive = top_features(feature_columns, importances, reverse=True)
    saved_classifier = RandomForestClassifier(
        n_estimators=500,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=random_state + 10_000,
    )
    saved_model = CalibratedClassifierCV(saved_classifier, cv=3, method="sigmoid")
    saved_model.fit(x, y)

    return EvaluationResult(
        name=name,
        feature_columns=feature_columns,
        probabilities=probabilities,
        fold_metrics=fold_metrics,
        top_positive_features=top_positive,
        top_negative_features=[],
        model=saved_model,
    )


def result_by_name(results: list[EvaluationResult], name: str) -> EvaluationResult:
    for result in results:
        if result.name == name:
            return result
    available = ", ".join(result.name for result in results)
    raise SystemExit(f"Unknown save profile {name!r}. Available profiles: {available}")


def save_model_artifact(
    path: Path,
    *,
    result: EvaluationResult,
    dataset: Dataset,
    input_path: Path,
    random_state: int,
) -> None:
    try:
        import joblib
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing joblib. Run: .venv/bin/python -m pip install -e '.[ml]'"
        ) from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    label_counts = dict(sorted(Counter(row["label"] for row in dataset.rows).items()))
    artifact = {
        "schema_version": 1,
        "tool": "gitzero",
        "profile": result.name,
        "model_type": type(result.model).__name__,
        "model": result.model,
        "feature_columns": result.feature_columns,
        "positive_labels": sorted(POSITIVE_LABELS),
        "negative_labels": sorted(NEGATIVE_LABELS),
        "trained_at_utc": datetime.now(UTC).isoformat(),
        "training_input": str(input_path),
        "training_rows": len(dataset.rows),
        "label_counts": label_counts,
        "random_state": random_state,
        "warning": (
            "This model predicts signals consistent with AI-assisted code. "
            "It does not prove authorship."
        ),
    }
    joblib.dump(artifact, path)


def matrix_for_rows(rows: list[dict[str, Any]], feature_columns: list[str]) -> list[list[float]]:
    return [[numeric_value(row.get(column)) for column in feature_columns] for row in rows]


def numeric_value(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        if isinstance(value, float) and math.isnan(value):
            return 0.0
        return float(value)
    return 0.0


def safe_fold_count(requested_folds: int, labels: list[int], groups: list[str]) -> int:
    if requested_folds < 2:
        raise SystemExit("--folds must be at least 2")
    label_counts = Counter(labels)
    group_count = len(set(groups))
    fold_count = min(requested_folds, group_count, min(label_counts.values()))
    if fold_count < 2:
        raise SystemExit("Not enough rows/groups per class for grouped cross-validation.")
    return fold_count


def metric_summary(y_true: list[int], probabilities: list[float]) -> dict[str, float]:
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    metrics: dict[str, float] = {
        "brier": float(brier_score_loss(y_true, probabilities)),
    }
    if len(set(y_true)) == 2:
        metrics["roc_auc"] = float(roc_auc_score(y_true, probabilities))
        metrics["pr_auc"] = float(average_precision_score(y_true, probabilities))
    else:
        metrics["roc_auc"] = float("nan")
        metrics["pr_auc"] = float("nan")
    return metrics


def add_model_report(result: EvaluationResult, dataset: Dataset, add: Any) -> None:
    overall = metric_summary(dataset.labels, result.probabilities)
    add("Overall grouped out-of-fold metrics")
    add(f"  ROC-AUC: {format_metric(overall['roc_auc'])}")
    add(f"  PR-AUC:  {format_metric(overall['pr_auc'])}")
    add(f"  Brier:   {format_metric(overall['brier'])}")
    add("")
    add("Fold metrics")
    for index, metrics in enumerate(result.fold_metrics, start=1):
        add(
            f"  fold {index}: "
            f"ROC-AUC={format_metric(metrics['roc_auc'])} "
            f"PR-AUC={format_metric(metrics['pr_auc'])} "
            f"Brier={format_metric(metrics['brier'])}"
        )
    add("")
    add("Threshold confusion matrices")
    for threshold in THRESHOLDS:
        add_threshold_report(dataset.labels, result.probabilities, threshold, add)
    add("")
    add("Misclassified repos at threshold 0.50")
    add_misclassification_report(dataset, result.probabilities, 0.5, add)
    add("")
    add("Top feature importances")
    for column, value in result.top_positive_features[:15]:
        add(f"  {value:.4f}  {column}")


def add_threshold_report(
    labels: list[int],
    probabilities: list[float],
    threshold: float,
    add: Any,
) -> None:
    predictions = [1 if probability >= threshold else 0 for probability in probabilities]
    tp = sum(1 for truth, pred in zip(labels, predictions, strict=True) if truth == 1 and pred == 1)
    fp = sum(1 for truth, pred in zip(labels, predictions, strict=True) if truth == 0 and pred == 1)
    tn = sum(1 for truth, pred in zip(labels, predictions, strict=True) if truth == 0 and pred == 0)
    fn = sum(1 for truth, pred in zip(labels, predictions, strict=True) if truth == 1 and pred == 0)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    accuracy = (tp + tn) / len(labels) if labels else 0.0
    add(
        f"  threshold {threshold:.2f}: "
        f"TP={tp} FP={fp} TN={tn} FN={fn} "
        f"precision={precision:.3f} recall={recall:.3f} accuracy={accuracy:.3f}"
    )


def add_misclassification_report(
    dataset: Dataset,
    probabilities: list[float],
    threshold: float,
    add: Any,
) -> None:
    false_positives: list[tuple[float, dict[str, Any]]] = []
    false_negatives: list[tuple[float, dict[str, Any]]] = []
    for row, truth, probability in zip(dataset.rows, dataset.labels, probabilities, strict=True):
        prediction = 1 if probability >= threshold else 0
        if truth == 0 and prediction == 1:
            false_positives.append((probability, row))
        elif truth == 1 and prediction == 0:
            false_negatives.append((probability, row))

    if not false_positives and not false_negatives:
        add("  none")
        return

    if false_positives:
        add("  false positives")
        for probability, row in sorted(false_positives, reverse=True):
            add_error_row(probability, row, add)
    if false_negatives:
        add("  false negatives")
        for probability, row in sorted(false_negatives):
            add_error_row(probability, row, add)


def add_error_row(probability: float, row: dict[str, Any], add: Any) -> None:
    top_signals = ", ".join(row.get("top_signals", [])[:4])
    add(
        f"    p={probability:.3f} {row['label']} {row['relative_path']} "
        f"top=[{top_signals}]"
    )


def top_features(
    feature_columns: list[str],
    values: list[float],
    *,
    reverse: bool,
) -> list[tuple[str, float]]:
    pairs = [(column, float(value)) for column, value in zip(feature_columns, values, strict=True)]
    return sorted(pairs, key=lambda pair: pair[1], reverse=reverse)


def format_metric(value: float) -> str:
    if math.isnan(value):
        return "n/a"
    return f"{value:.3f}"


if __name__ == "__main__":
    main()
