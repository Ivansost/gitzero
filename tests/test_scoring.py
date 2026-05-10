from __future__ import annotations

from gitzero.models import SignalFinding, StaticAnalysisResult
from gitzero.scoring import build_score_summary, risk_for_score


def test_risk_bands() -> None:
    assert risk_for_score(10)[0] == "Low"
    assert risk_for_score(50)[0] == "Medium"
    assert risk_for_score(85)[0] == "High"


def test_score_summary_combines_git_and_static() -> None:
    git_findings = (
        SignalFinding(
            id="git.large_commits",
            title="Large commits",
            category="git",
            score=80,
            weight=1,
            detail="large",
        ),
    )
    static = StaticAnalysisResult(
        files=(),
        findings=(
            SignalFinding(
                id="static.cluster",
                title="Static cluster",
                category="static",
                score=60,
                weight=1,
                detail="cluster",
            ),
        ),
        files_scanned=1,
        files_skipped=0,
        total_lines=10,
    )

    summary = build_score_summary(git_findings, static, git_history_enabled=True)

    assert summary.overall_score == 69.0
    assert summary.risk_band == "Medium"
    assert summary.top_findings[0].id == "git.large_commits"


def test_ai_config_hard_signal_forces_high_overall() -> None:
    static = StaticAnalysisResult(
        files=(),
        findings=(
            SignalFinding(
                id="git.ai_config_files_present",
                title="AI assistant config files present",
                category="git",
                score=100,
                weight=8,
                detail="Found AGENTS.md",
            ),
        ),
        files_scanned=0,
        files_skipped=0,
        total_lines=0,
    )

    summary = build_score_summary((), static, git_history_enabled=False)

    assert summary.overall_score >= 92
    assert summary.risk_band == "High"
    assert summary.top_findings[0].id == "git.ai_config_files_present"


def test_score_summary_tracks_confidence_and_dampening_separately() -> None:
    git_findings = (
        SignalFinding(
            id="git.large_commits",
            title="Large commits",
            category="git",
            score=80,
            weight=1,
            detail="large",
        ),
        SignalFinding(
            id="dampener.git.long_lived_history",
            title="Long lived history",
            category="dampener",
            score=70,
            weight=1,
            detail="history spans months",
        ),
    )
    static = StaticAnalysisResult(
        files=(),
        findings=(
            SignalFinding(
                id="static.cluster",
                title="Static cluster",
                category="static",
                score=60,
                weight=1,
                detail="cluster",
            ),
        ),
        files_scanned=10,
        files_skipped=0,
        total_lines=1000,
    )

    summary = build_score_summary(git_findings, static, git_history_enabled=True)

    assert summary.overall_score < 69.0
    assert summary.confidence_score > 0
    assert summary.dampening_score == 70
    assert summary.top_findings[0].id == "git.large_commits"
    assert summary.dampening_findings[0].id == "dampener.git.long_lived_history"


def test_starter_template_dampener_caps_high_risk_without_hard_evidence() -> None:
    git_findings = (
        SignalFinding(
            id="git.large_commits",
            title="Large commits",
            category="git",
            score=95,
            weight=2,
            detail="large",
        ),
        SignalFinding(
            id="git.single_drop_repo",
            title="Single drop",
            category="git",
            score=95,
            weight=2,
            detail="drop",
        ),
    )
    static = StaticAnalysisResult(
        files=(),
        findings=(
            SignalFinding(
                id="static.files_with_ai_like_shape",
                title="AI-like files",
                category="static",
                score=90,
                weight=1,
                detail="shape",
            ),
            SignalFinding(
                id="dampener.static.starter_template_detected",
                title="Starter template",
                category="dampener",
                score=70,
                weight=1,
                detail="vite starter",
            ),
        ),
        files_scanned=3,
        files_skipped=0,
        total_lines=120,
    )

    summary = build_score_summary(git_findings, static, git_history_enabled=True)

    assert summary.overall_score <= 54
    assert summary.risk_band == "Medium"


def test_organic_history_dampeners_cap_large_initial_import_without_hard_evidence() -> None:
    git_findings = (
        SignalFinding(
            id="git.large_commits",
            title="Large commits",
            category="git",
            score=95,
            weight=2,
            detail="large",
        ),
        SignalFinding(
            id="git.file_creation_wave",
            title="File creation wave",
            category="git",
            score=92,
            weight=2,
            detail="wave",
        ),
        SignalFinding(
            id="dampener.git.long_lived_history",
            title="Long lived",
            category="dampener",
            score=80,
            weight=1,
            detail="years",
        ),
        SignalFinding(
            id="dampener.git.multi_author_history",
            title="Multiple authors",
            category="dampener",
            score=75,
            weight=1,
            detail="authors",
        ),
        SignalFinding(
            id="dampener.git.merge_commits_present",
            title="Merge commits",
            category="dampener",
            score=70,
            weight=1,
            detail="merges",
        ),
    )
    static = StaticAnalysisResult(
        files=(),
        findings=(
            SignalFinding(
                id="static.files_with_ai_like_shape",
                title="AI-like files",
                category="static",
                score=90,
                weight=1,
                detail="shape",
            ),
        ),
        files_scanned=20,
        files_skipped=0,
        total_lines=5000,
    )

    summary = build_score_summary(git_findings, static, git_history_enabled=True)

    assert summary.overall_score <= 59
    assert summary.risk_band == "Medium"
