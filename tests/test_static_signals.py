from __future__ import annotations

from pathlib import Path

from gitzero.static_signals import AI_CONFIG_PHRASE, analyze_static_code


def test_static_analysis_flags_uniform_documented_python(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text(
        '''
"""Service helpers."""


def calculate_user_engagement_score(active_user_session_count, completed_action_total):
    """Calculate the user engagement score."""
    # Validate the incoming score inputs
    normalized_user_engagement_value = active_user_session_count + completed_action_total
    return normalized_user_engagement_value


def calculate_user_retention_score(active_user_session_count, completed_action_total):
    """Calculate the user retention score."""
    # Validate the incoming score inputs
    normalized_user_retention_value = active_user_session_count + completed_action_total
    return normalized_user_retention_value


def calculate_user_activation_score(active_user_session_count, completed_action_total):
    """Calculate the user activation score."""
    # Validate the incoming score inputs
    normalized_user_activation_value = active_user_session_count + completed_action_total
    return normalized_user_activation_value


def calculate_user_conversion_score(active_user_session_count, completed_action_total):
    """Calculate the user conversion score."""
    # Validate the incoming score inputs
    normalized_user_conversion_value = active_user_session_count + completed_action_total
    return normalized_user_conversion_value
'''.strip()
    )

    result = analyze_static_code(tmp_path)

    assert result.files_scanned == 1
    assert result.files[0].score >= 35
    assert result.findings


def test_static_analysis_skips_unsupported_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# hello")

    result = analyze_static_code(tmp_path)

    assert result.files_scanned == 0
    assert result.findings[0].id == "static.no_supported_files"


def test_static_analysis_respects_excludes(tmp_path: Path) -> None:
    ignored = tmp_path / "ignored"
    ignored.mkdir()
    (ignored / "main.py").write_text("def hello():\n    return 'world'\n")

    result = analyze_static_code(tmp_path, excludes=("ignored",))

    assert result.files_scanned == 0
    assert result.files_skipped == 0


def test_static_analysis_reports_docstrings_types_and_structure(tmp_path: Path) -> None:
    source = tmp_path / "typed_service.py"
    source.write_text(
        '''
def calculate_alpha_score(active_user_count: int, completed_action_total: int) -> int:
    """Calculate alpha score."""
    if active_user_count < 0:
        raise ValueError("active_user_count must be positive")
    normalized_alpha_value = active_user_count + completed_action_total
    return normalized_alpha_value


def calculate_beta_score(active_user_count: int, completed_action_total: int) -> int:
    """Calculate beta score."""
    if active_user_count < 0:
        raise ValueError("active_user_count must be positive")
    normalized_beta_value = active_user_count + completed_action_total
    return normalized_beta_value


def calculate_gamma_score(active_user_count: int, completed_action_total: int) -> int:
    """Calculate gamma score."""
    if active_user_count < 0:
        raise ValueError("active_user_count must be positive")
    normalized_gamma_value = active_user_count + completed_action_total
    return normalized_gamma_value


def calculate_delta_score(active_user_count: int, completed_action_total: int) -> int:
    """Calculate delta score."""
    if active_user_count < 0:
        raise ValueError("active_user_count must be positive")
    normalized_delta_value = active_user_count + completed_action_total
    return normalized_delta_value
'''
    )

    result = analyze_static_code(tmp_path)
    file = result.files[0]
    signal_ids = {finding.id for finding in file.verbose_findings}

    assert file.docstring_rate == 1.0
    assert file.type_annotation_density == 1.0
    assert file.structure_repetition_score >= 0.5
    assert "static.docstring_coverage" in signal_ids
    assert "static.type_annotation_density" in signal_ids
    assert "static.structural_repetition" in signal_ids


def test_static_analysis_flags_ai_config_files_and_vibe_code_phrase(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.MD").write_text("Use Codex for this repo.\n")
    (tmp_path / "claude.md").write_text("Claude Code notes.\n")
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "claude.yml").write_text("name: Claude\n")
    cursor_dir = tmp_path / ".continue"
    cursor_dir.mkdir()
    phrase = "vi" + "be coded"
    (tmp_path / "README.md").write_text(f"This was {phrase} during a demo.\n")

    result = analyze_static_code(tmp_path)
    findings = {finding.id: finding for finding in result.findings}

    assert "git.ai_config_files_present" in findings
    finding = findings["git.ai_config_files_present"]
    assert finding.score == 100
    assert "AGENTS.MD" in finding.detail
    assert "claude.md" in finding.detail
    assert ".github/workflows/claude.yml" in finding.detail
    assert ".continue" in finding.detail
    assert f"README.md contains '{AI_CONFIG_PHRASE}'" in finding.detail


def test_static_analysis_flags_absent_debug_artifacts_and_file_size_uniformity(
    tmp_path: Path,
) -> None:
    for index in range(6):
        module_lines = [
            item
            for line in range(25)
            for item in (
                f"value_{line} = {line}",
                f"normalized_{line} = value_{line} + {index}",
            )
        ]
        (tmp_path / f"module_{index}.py").write_text("\n".join(module_lines))

    result = analyze_static_code(tmp_path)
    finding_ids = {finding.id for finding in result.findings}

    assert "static.debug_artifact_absence" in finding_ids
    assert "static.file_size_uniformity" in finding_ids


def test_static_analysis_flags_generic_todos(tmp_path: Path) -> None:
    (tmp_path / "worker.py").write_text(
        """
def run_job():
    # TODO: add error handling
    # TODO: implement this
    # FIXME: optimize
    return "done"
"""
    )

    result = analyze_static_code(tmp_path)
    finding_ids = {finding.id for finding in result.findings}

    assert "static.generic_todo_patterns" in finding_ids


def test_static_analysis_dampens_personal_todos(tmp_path: Path) -> None:
    (tmp_path / "worker.py").write_text(
        """
def run_job():
    # TODO: check with Jake before shipping auth retry behavior
    # TODO: confirm PAY-431 webhook replay case with ops
    # FIXME: keep legacy importer until Acme migration finishes
    return "done"
"""
    )

    result = analyze_static_code(tmp_path)
    finding_ids = {finding.id for finding in result.findings}

    assert "dampener.static.personal_todo_patterns" in finding_ids


def test_static_analysis_dampens_debug_artifacts_present(tmp_path: Path) -> None:
    for index in range(5):
        lines = [f"value_{line} = {line}" for line in range(55)]
        if index == 0:
            lines.append("print('debug payload')")
        (tmp_path / f"module_{index}.py").write_text("\n".join(lines))

    result = analyze_static_code(tmp_path)
    finding_ids = {finding.id for finding in result.findings}

    assert "dampener.static.debug_artifacts_present" in finding_ids


def test_static_analysis_surfaces_complexity_uniformity(tmp_path: Path) -> None:
    (tmp_path / "branches.py").write_text(
        """
def alpha(value):
    if value:
        return 1
    return 0


def beta(value):
    if value:
        return 1
    return 0


def gamma(value):
    if value:
        return 1
    return 0


def delta(value):
    if value:
        return 1
    return 0
"""
    )

    result = analyze_static_code(tmp_path)
    signal_ids = {finding.id for finding in result.files[0].verbose_findings}

    assert result.files[0].complexity_average == 2
    assert result.files[0].complexity_stdev == 0
    assert "static.complexity_uniformity" in signal_ids


def test_static_analysis_counts_typescript_type_density(tmp_path: Path) -> None:
    (tmp_path / "service.ts").write_text(
        """
interface UserRecord {
  id: string
  email: string
}

type ScorePayload = {
  value: number
}

const threshold: number = 10

function buildScore(user: UserRecord, payload: ScorePayload): number {
  return payload.value + threshold
}

const formatScore = (score: number, label: string): string => {
  return `${label}:${score}`
}
"""
    )

    result = analyze_static_code(tmp_path)
    signal_ids = {finding.id for finding in result.files[0].verbose_findings}

    assert result.files[0].type_annotation_density >= 0.75
    assert "static.type_annotation_density" in signal_ids


def test_static_analysis_flags_shallow_test_quality(tmp_path: Path) -> None:
    for index in range(2):
        (tmp_path / f"test_service_{index}.py").write_text(
            """
def test_payload_shape():
    result = {"ok": True}
    assert result is not None
    assert isinstance(result, dict)
    assert result
"""
        )

    result = analyze_static_code(tmp_path)
    finding_ids = {finding.id for finding in result.findings}

    assert "static.shallow_test_quality" in finding_ids


def test_static_analysis_flags_readme_and_dependency_misalignment(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        """
# Example App

A modern, scalable, robust, production-ready platform with authentication,
payments, analytics, dashboard, notifications, and export workflows.
"""
    )
    (tmp_path / "package.json").write_text(
        """
{
  "dependencies": {
    "axios": "^1.0.0",
    "lodash": "^4.0.0",
    "moment": "^2.0.0",
    "react": "^18.0.0",
    "zod": "^3.0.0"
  }
}
"""
    )
    (tmp_path / "index.ts").write_text("export const value: number = 1\n")

    result = analyze_static_code(tmp_path)
    finding_ids = {finding.id for finding in result.findings}

    assert "static.readme_broad_claims" in finding_ids
    assert "static.readme_code_misalignment" in finding_ids
    assert "static.unused_dependencies" in finding_ids
    assert "static.heavy_dependencies_small_repo" in finding_ids


def test_static_analysis_caps_max_files_and_reports_skip_reason(tmp_path: Path) -> None:
    for index in range(5):
        (tmp_path / f"module_{index}.py").write_text(f"value = {index}\n")

    result = analyze_static_code(tmp_path, max_files=2)

    assert result.files_scanned == 2
    assert result.files_skipped == 3
    assert result.skipped_by_reason["max_files"] == 3
    assert result.files_indexed == 5


def test_static_analysis_dampens_known_starter_templates(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        """
{"scripts":{"dev":"vite"},"dependencies":{"@vitejs/plugin-react":"latest","react":"latest"}}
"""
    )
    (tmp_path / "vite.config.ts").write_text("export default {}\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.tsx").write_text("export const value: number = 1\n")

    result = analyze_static_code(tmp_path)
    finding_ids = {finding.id for finding in result.findings}

    assert "dampener.static.starter_template_detected" in finding_ids


def test_static_analysis_dampens_angular_nest_and_expo_templates(tmp_path: Path) -> None:
    cases = {
        "angular": (
            '{"scripts":{"build":"ng build"},"dependencies":{"@angular/core":"latest"}}',
            "angular.json",
        ),
        "nest": (
            '{"scripts":{"build":"nest build"},"dependencies":{"@nestjs/core":"latest"}}',
            "nest-cli.json",
        ),
        "expo": (
            '{"scripts":{"start":"expo start"},"dependencies":{"expo":"latest"}}',
            "app.json",
        ),
    }
    for name, (package_json, marker_file) in cases.items():
        repo_path = tmp_path / name
        repo_path.mkdir()
        (repo_path / "package.json").write_text(package_json)
        (repo_path / marker_file).write_text("{}\n")

        result = analyze_static_code(repo_path)
        finding_ids = {finding.id for finding in result.findings}

        assert "dampener.static.starter_template_detected" in finding_ids


def test_static_analysis_dampens_educational_repos(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        """
# Tutorial Materials

This repository contains source code for each course chapter and sample code
used throughout the workshop.
"""
    )

    result = analyze_static_code(tmp_path)
    finding_ids = {finding.id for finding in result.findings}

    assert "dampener.static.educational_or_example_repo" in finding_ids
