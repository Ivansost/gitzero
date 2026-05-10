from __future__ import annotations

from gitzero.ml import _probability_band
from gitzero.report import _probability_style


def test_ml_probability_bands_use_conservative_thresholds() -> None:
    assert _probability_band(0.69) == "Low"
    assert _probability_band(0.70) == "Medium"
    assert _probability_band(0.85) == "High"


def test_ml_probability_styles_match_probability_bands() -> None:
    assert _probability_style(0.69) == "green"
    assert _probability_style(0.70) == "yellow"
    assert _probability_style(0.85) == "red"
