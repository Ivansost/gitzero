from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gitzero.git_signals import analyze_git_history

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is required")


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "GitZero Test"], cwd=path, check=True)


def _commit_all(
    path: Path,
    message: str,
    *,
    author_name: str = "GitZero Test",
    author_email: str = "test@example.com",
) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
    }
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=path,
        env=env,
        check=True,
        capture_output=True,
    )


def test_git_history_flags_large_file_creation_wave(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    for index in range(24):
        file_path = tmp_path / f"module_{index}.py"
        file_path.write_text("\n".join(f"value_{line} = {line}" for line in range(70)))

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial drop"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    findings = analyze_git_history(tmp_path)
    finding_ids = {finding.id for finding in findings}

    assert "git.file_creation_wave" in finding_ids
    assert "git.large_commits" in finding_ids


def test_git_history_flags_formulaic_commit_messages(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    messages = [
        "Add user authentication",
        "Add payment processing",
        "Add dashboard widgets",
        "Add settings page",
        "Add notification service",
    ]
    for index, message in enumerate(messages):
        (tmp_path / f"feature_{index}.py").write_text(f"value = {index}\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    findings = analyze_git_history(tmp_path)
    finding_ids = {finding.id for finding in findings}

    assert "git.commit_message_uniformity" in finding_ids
    assert "git.single_author_history" in finding_ids


def test_git_history_flags_no_merges_and_no_obvious_typos(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    for index in range(20):
        (tmp_path / f"feature_{index}.py").write_text(f"value = {index}\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Add carefully scoped feature module {index}"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    findings = analyze_git_history(tmp_path)
    finding_ids = {finding.id for finding in findings}

    assert "git.no_merge_commits" in finding_ids
    assert "git.no_commit_typos" in finding_ids


def test_git_history_flags_broad_diff_shape_and_files_not_reworked(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    for directory in ("src", "tests", "docs", "config"):
        (tmp_path / directory).mkdir()
    for index in range(10):
        (tmp_path / "src" / f"module_{index}.py").write_text(f"value = {index}\n")
    for index in range(4):
        (tmp_path / "tests" / f"test_module_{index}.py").write_text(
            "def test_ok():\n    assert True\n"
        )
    (tmp_path / "docs" / "usage.md").write_text("# Usage\n")
    (tmp_path / "config" / "settings.json").write_text("{}\n")

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial complete project drop"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    findings = analyze_git_history(tmp_path)
    finding_ids = {finding.id for finding in findings}

    assert "git.diff_shape_broad_file_drop" in finding_ids
    assert "git.diff_shape_complete_stack_drop" in finding_ids
    assert "git.diff_shape_files_rarely_reworked" in finding_ids


def test_git_history_ignores_vendored_files_for_diff_shape(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    vendor_dir = tmp_path / "resources" / "demo" / "html" / "js"
    vendor_dir.mkdir(parents=True)
    for index, name in enumerate(
        [
            "jquery.js",
            "bootstrap.js",
            "lodash.js",
            "vue.js",
            "crypto.js",
            "angular.js",
            "react.development.js",
            "bootstrap-colorpicker.js",
        ]
    ):
        (vendor_dir / name).write_text(f"function vendor{index}() {{ return {index}; }}\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("value = 1\n")

    _commit_all(tmp_path, "Initial vendored assets")

    findings = analyze_git_history(tmp_path)
    finding_ids = {finding.id for finding in findings}

    assert "git.diff_shape_files_rarely_reworked" not in finding_ids
    assert "git.diff_shape_broad_file_drop" not in finding_ids


def test_git_history_dampens_merge_commits(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "base.py").write_text("value = 0\n")
    _commit_all(tmp_path, "Initial base")
    default_branch = subprocess.check_output(
        ["git", "branch", "--show-current"],
        cwd=tmp_path,
        text=True,
    ).strip()

    subprocess.run(["git", "checkout", "-b", "feature"], cwd=tmp_path, check=True)
    (tmp_path / "feature.py").write_text("feature = True\n")
    _commit_all(tmp_path, "Add feature branch work")

    subprocess.run(["git", "checkout", default_branch], cwd=tmp_path, check=True)
    for index in range(2):
        (tmp_path / f"main_{index}.py").write_text(f"value = {index}\n")
        _commit_all(tmp_path, f"Add mainline work {index}")

    subprocess.run(
        ["git", "merge", "--no-ff", "feature", "-m", "Merge feature branch"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    findings = analyze_git_history(tmp_path)
    finding_ids = {finding.id for finding in findings}

    assert "dampener.git.merge_commits_present" in finding_ids


def test_git_history_dampens_multi_author_history(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    authors = [
        ("Alice Example", "alice@example.com"),
        ("Bob Example", "bob@example.com"),
        ("Chris Example", "chris@example.com"),
    ]
    for index in range(10):
        (tmp_path / f"module_{index}.py").write_text(f"value = {index}\n")
        name, email = authors[index % len(authors)]
        _commit_all(tmp_path, f"Update module {index}", author_name=name, author_email=email)

    findings = analyze_git_history(tmp_path)
    finding_ids = {finding.id for finding in findings}

    assert "dampener.git.multi_author_history" in finding_ids
