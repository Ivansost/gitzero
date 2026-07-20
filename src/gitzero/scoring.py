from __future__ import annotations

from .models import ScoreSummary, SignalFinding, StaticAnalysisResult


def build_score_summary(
    git_findings: tuple[SignalFinding, ...],
    static_result: StaticAnalysisResult,
    *,
    git_history_enabled: bool,
) -> ScoreSummary:
    static_risk_findings = _risk_findings(static_result.findings)
    git_risk_findings = _risk_findings(git_findings)
    dampening_findings = tuple(
        sorted(
            [
                *[finding for finding in git_findings if _is_dampener(finding)],
                *[finding for finding in static_result.findings if _is_dampener(finding)],
            ],
            key=lambda finding: finding.score * finding.weight,
            reverse=True,
        )
    )

    static_score = _weighted_average(static_risk_findings)
    git_score = _weighted_average(git_risk_findings) if git_history_enabled else None
    dampening_score = _weighted_average(dampening_findings, empty_default=0.0) or 0.0

    if git_score is None:
        overall = static_score if static_score is not None else 0.0
    elif static_score is None:
        overall = git_score
    else:
        overall = git_score * 0.45 + static_score * 0.55

    all_findings = sorted(
        [*git_risk_findings, *static_risk_findings],
        key=lambda finding: finding.score * finding.weight,
        reverse=True,
    )
    if dampening_score >= 60:
        dampening_factor = 0.30
    elif dampening_score >= 40:
        dampening_factor = 0.22
    else:
        dampening_factor = 0.18
    overall = max(0.0, overall - dampening_score * dampening_factor)
    hard_evidence_present = any(
        finding.id == "git.ai_config_files_present" for finding in all_findings
    )
    if not hard_evidence_present:
        compact_project_dump = _has_compact_project_dump(tuple(all_findings))
        small_ui_dump = _has_small_ui_dump_shape(tuple(all_findings))
        strong_family_count = _strong_risk_family_count(tuple(all_findings))
        pristine_template = _has_pristine_starter_template(dampening_findings)
        if pristine_template or (
            _has_starter_template(dampening_findings) and not compact_project_dump
        ):
            overall = min(overall, 39.0)
        if _has_educational_context(dampening_findings):
            overall = min(overall, 39.0)
        organic_strength = _organic_history_strength(dampening_findings)
        if organic_strength >= 3 and not (compact_project_dump or small_ui_dump):
            overall = min(overall, 39.0)
        elif organic_strength >= 2 and not (compact_project_dump or small_ui_dump):
            overall = min(overall, 39.0 if dampening_score >= 60 else 44.0)
        elif dampening_score >= 60 and not (compact_project_dump or small_ui_dump):
            overall = min(overall, 39.0 if strong_family_count < 3 else 54.0)
        if overall >= 70.0 and strong_family_count < 3 and not (
            compact_project_dump or small_ui_dump
        ):
            overall = 64.0
        if not pristine_template and organic_strength < 2 and (
            compact_project_dump or small_ui_dump
        ):
            overall = max(overall, 70.0)
    if hard_evidence_present:
        overall = max(overall, 92.0)
    risk_band, risk_color = risk_for_score(overall)
    confidence_score = _confidence_score(
        git_findings=git_findings,
        static_result=static_result,
        git_history_enabled=git_history_enabled,
        risk_findings=tuple(all_findings),
        dampening_findings=dampening_findings,
    )
    return ScoreSummary(
        overall_score=round(overall, 1),
        risk_band=risk_band,
        risk_color=risk_color,
        confidence_score=round(confidence_score, 1),
        dampening_score=round(dampening_score, 1),
        git_score=round(git_score, 1) if git_score is not None else None,
        static_score=round(static_score, 1) if static_score is not None else None,
        top_findings=tuple(all_findings[:6]),
        dampening_findings=dampening_findings[:5],
    )


def risk_for_score(score: float) -> tuple[str, str]:
    if score >= 70:
        return "High", "red"
    if score >= 40:
        return "Medium", "yellow"
    return "Low", "green"


def _weighted_average(
    findings: tuple[SignalFinding, ...],
    *,
    empty_default: float | None = 8.0,
) -> float | None:
    weighted = [(finding.score, finding.weight) for finding in findings if finding.weight > 0]
    if not weighted:
        return empty_default
    total_weight = sum(weight for _, weight in weighted)
    return sum(score * weight for score, weight in weighted) / total_weight


def _is_dampener(finding: SignalFinding) -> bool:
    return finding.category == "dampener" or finding.id.startswith("dampener.")


def _has_starter_template(findings: tuple[SignalFinding, ...]) -> bool:
    return any(finding.id == "dampener.static.starter_template_detected" for finding in findings)


def _has_pristine_starter_template(findings: tuple[SignalFinding, ...]) -> bool:
    return any(
        finding.id == "dampener.static.pristine_starter_template" for finding in findings
    )


def _has_educational_context(findings: tuple[SignalFinding, ...]) -> bool:
    return any(finding.id == "dampener.static.educational_or_example_repo" for finding in findings)


def _organic_history_strength(findings: tuple[SignalFinding, ...]) -> int:
    organic_ids = {
        "dampener.git.long_lived_history",
        "dampener.git.merge_commits_present",
        "dampener.git.multi_author_history",
        "dampener.git.organic_churn",
    }
    return len({finding.id for finding in findings if finding.id in organic_ids})


def _has_small_ui_dump_shape(findings: tuple[SignalFinding, ...]) -> bool:
    has_large_commit = any(
        finding.id == "git.large_commits" and finding.score >= 90 for finding in findings
    )
    has_monolithic_ui = any(
        finding.id == "static.monolithic_ui_file" and finding.score >= 75 for finding in findings
    )
    return has_large_commit and has_monolithic_ui


def _has_compact_project_dump(findings: tuple[SignalFinding, ...]) -> bool:
    has_single_drop = any(
        finding.id == "git.single_drop_repo" and finding.score >= 70 for finding in findings
    )
    has_short_span = any(
        finding.id == "git.short_project_span" and finding.score >= 70 for finding in findings
    )
    has_large_commit = any(
        finding.id == "git.large_commits" and finding.score >= 90 for finding in findings
    )
    has_broad_drop = any(
        finding.id == "git.diff_shape_broad_file_drop" and finding.score >= 70
        for finding in findings
    )
    return has_single_drop and (has_short_span or (has_large_commit and has_broad_drop))


def _strong_risk_family_count(findings: tuple[SignalFinding, ...]) -> int:
    families: set[str] = set()
    for finding in findings:
        if finding.score < 55:
            continue
        family = _risk_family(finding.id)
        if family:
            families.add(family)
    return len(families)


def _risk_family(signal_id: str) -> str | None:
    if signal_id in {
        "git.large_commits",
        "git.file_creation_wave",
        "git.single_drop_repo",
        "git.short_project_span",
        "git.diff_shape_broad_file_drop",
        "git.diff_shape_complete_stack_drop",
        "git.diff_shape_files_rarely_reworked",
        "git.project_skeleton_symmetry",
    }:
        return "git_dump_shape"
    if signal_id in {
        "git.bursty_timing",
        "git.commit_hour_clustering",
        "git.commit_time_distribution",
        "git.two_hour_history_window",
    }:
        return "git_timing"
    if signal_id in {
        "git.commit_message_uniformity",
        "git.short_generic_messages",
        "git.no_commit_typos",
    }:
        return "git_messages"
    if signal_id in {
        "static.files_with_ai_like_shape",
        "static.repo_structural_repetition",
        "static.monolithic_ui_file",
        "static.file_size_uniformity",
        "static.debug_artifact_absence",
    }:
        return "static_shape"
    if signal_id.startswith("static.") and signal_id not in {
        "static.no_supported_files",
        "static.top_file",
    }:
        return "static_style"
    return None


def _risk_findings(findings: tuple[SignalFinding, ...]) -> tuple[SignalFinding, ...]:
    return tuple(finding for finding in findings if not _is_dampener(finding))


def _confidence_score(
    *,
    git_findings: tuple[SignalFinding, ...],
    static_result: StaticAnalysisResult,
    git_history_enabled: bool,
    risk_findings: tuple[SignalFinding, ...],
    dampening_findings: tuple[SignalFinding, ...],
) -> float:
    static_coverage = min(45.0, static_result.files_scanned * 2.2 + static_result.total_lines / 220)
    if static_result.files_scanned <= 2:
        static_coverage *= 0.45
    elif static_result.files_scanned <= 5:
        static_coverage *= 0.7

    total_considered = static_result.files_scanned + static_result.files_skipped
    if total_considered:
        skip_ratio = static_result.files_skipped / total_considered
        static_coverage *= max(0.55, 1 - skip_ratio * 0.45)
    if static_result.skipped_by_reason.get("max_files"):
        static_coverage *= 0.85

    if git_history_enabled:
        git_unavailable = any(
            finding.id in {"git.no_history", "git.empty_history"} for finding in git_findings
        )
        git_coverage = 4.0 if git_unavailable else 28.0
    else:
        git_coverage = 0.0

    hard_evidence_bonus = (
        15.0
        if any(finding.id == "git.ai_config_files_present" for finding in risk_findings)
        else 0.0
    )
    signal_coverage = min(25.0, len(risk_findings) * 3.0 + len(dampening_findings) * 2.0)
    confidence = static_coverage + git_coverage + signal_coverage + hard_evidence_bonus
    if static_result.files_scanned <= 2 and git_coverage <= 4.0:
        confidence = min(confidence, 35.0)
    return min(100.0, confidence)
