from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class LoadedRepository:
    """A repository source resolved to a local path."""

    source: str
    path: Path
    is_temporary: bool = False


@dataclass(frozen=True)
class CommitMetric:
    sha: str
    timestamp: int | None
    files_changed: int
    lines_added: int
    lines_deleted: int
    files_created: int
    message: str = ""
    author_name: str = ""
    author_email: str = ""
    parent_count: int = 1
    files_touched: tuple[str, ...] = field(default_factory=tuple)
    files_created_paths: tuple[str, ...] = field(default_factory=tuple)

    @property
    def lines_changed(self) -> int:
        return self.lines_added + self.lines_deleted


@dataclass(frozen=True)
class SignalFinding:
    id: str
    title: str
    category: str
    score: float
    weight: float
    detail: str
    path: str | None = None
    why_flagged: str = ""
    benign_explanation: str = ""
    evidence_count: int = 0
    confidence_impact: str = ""
    risk_impact: str = ""

    def __post_init__(self) -> None:
        if not self.why_flagged:
            object.__setattr__(self, "why_flagged", self.detail)
        if not self.benign_explanation:
            object.__setattr__(self, "benign_explanation", _default_benign_explanation(self))
        if not self.confidence_impact:
            object.__setattr__(self, "confidence_impact", _default_confidence_impact(self))
        if not self.risk_impact:
            object.__setattr__(self, "risk_impact", _default_risk_impact(self))


@dataclass(frozen=True)
class FileFinding:
    path: str
    language: str
    score: float
    lines: int
    comment_density: float
    identifier_count: int
    docstring_rate: float = 0.0
    type_annotation_density: float = 0.0
    complexity_average: float | None = None
    complexity_stdev: float | None = None
    structure_repetition_score: float = 0.0
    debug_artifact_count: int = 0
    commented_code_block_count: int = 0
    todo_count: int = 0
    generic_todo_count: int = 0
    test_assertion_count: int = 0
    shallow_test_assertion_count: int = 0
    highlights: tuple[str, ...] = field(default_factory=tuple)
    verbose_findings: tuple[SignalFinding, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StaticAnalysisResult:
    files: tuple[FileFinding, ...]
    findings: tuple[SignalFinding, ...]
    files_scanned: int
    files_skipped: int
    total_lines: int
    files_indexed: int = 0
    skipped_by_reason: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreSummary:
    overall_score: float
    risk_band: str
    risk_color: str
    confidence_score: float
    dampening_score: float
    git_score: float | None
    static_score: float | None
    top_findings: tuple[SignalFinding, ...]
    dampening_findings: tuple[SignalFinding, ...] = field(default_factory=tuple)


def _default_benign_explanation(finding: SignalFinding) -> str:
    if finding.category == "dampener" or finding.id.startswith("dampener."):
        return "This is benign evidence that reduces the risk interpretation."
    if finding.category == "git":
        return (
            "This can also happen in solo projects, imported histories, squashed workflows, "
            "or carefully managed repositories."
        )
    if finding.category == "static":
        return (
            "This can also reflect framework conventions, templates, strict style guides, "
            "or mature engineering practices."
        )
    return "This signal should be interpreted with the rest of the report, not alone."


def _default_confidence_impact(finding: SignalFinding) -> str:
    if finding.weight >= 2.0 or finding.score >= 85:
        return "raises"
    if finding.category == "dampener" or finding.id.startswith("dampener."):
        return "contextual"
    return "small"


def _default_risk_impact(finding: SignalFinding) -> str:
    if finding.category == "dampener" or finding.id.startswith("dampener."):
        return "lowers"
    if finding.weight >= 1.0 and finding.score >= 60:
        return "raises"
    return "small"
