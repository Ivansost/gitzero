from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evaluation import build_batch_row
from .models import ScoreSummary, SignalFinding, StaticAnalysisResult


@dataclass(frozen=True)
class MlPrediction:
    probability: float
    band: str
    model_path: str
    profile: str
    feature_count: int


def load_model_artifact(path: Path) -> dict[str, Any]:
    try:
        import joblib
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "ML model loading requires the optional ml dependencies. "
            "Run: python -m pip install 'gitzero[ml]'"
        ) from exc

    artifact = joblib.load(path)
    if not isinstance(artifact, dict):
        raise ValueError("ML model artifact must be a dictionary.")
    if "model" not in artifact or "feature_columns" not in artifact:
        raise ValueError("ML model artifact is missing model or feature_columns.")
    feature_columns = artifact["feature_columns"]
    if not isinstance(feature_columns, list) or not all(
        isinstance(column, str) for column in feature_columns
    ):
        raise ValueError("ML model artifact has invalid feature_columns.")
    return artifact


def predict_from_scan(
    *,
    artifact: dict[str, Any],
    artifact_path: Path,
    repo_path: Path,
    score: ScoreSummary,
    static_result: StaticAnalysisResult,
    git_findings: tuple[SignalFinding, ...],
    git_history_enabled: bool,
) -> MlPrediction:
    row = build_batch_row(
        repo_path=repo_path,
        root_path=repo_path.parent,
        label="unknown",
        score=score,
        static_result=static_result,
        git_findings=git_findings,
        git_history_enabled=git_history_enabled,
    )
    feature_columns = artifact["feature_columns"]
    vector = [[_numeric_value(row.get(column)) for column in feature_columns]]
    model = artifact["model"]
    probability = float(model.predict_proba(vector)[0][1])
    return MlPrediction(
        probability=round(probability, 4),
        band=_probability_band(probability),
        model_path=str(artifact_path),
        profile=str(artifact.get("profile", "unknown")),
        feature_count=len(feature_columns),
    )


def _numeric_value(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        if isinstance(value, float) and math.isnan(value):
            return 0.0
        return float(value)
    return 0.0


def _probability_band(probability: float) -> str:
    if probability >= 0.85:
        return "High"
    if probability >= 0.7:
        return "Medium"
    return "Low"
