from __future__ import annotations

import json
from pathlib import Path

from gitzero.evaluation import (
    build_batch_row,
    discover_repo_dirs,
    label_for_repo,
    load_labels,
    write_rows,
)
from gitzero.fixtures import create_fixture_corpus
from gitzero.models import ScoreSummary, SignalFinding, StaticAnalysisResult


def test_batch_row_exports_training_fields(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    signal = SignalFinding(
        id="static.example",
        title="Example",
        category="static",
        score=70,
        weight=1,
        detail="example detail",
    )
    static = StaticAnalysisResult(
        files=(),
        findings=(signal,),
        files_scanned=3,
        files_skipped=1,
        total_lines=120,
        files_indexed=4,
        skipped_by_reason={"large": 1},
    )
    score = ScoreSummary(
        overall_score=55,
        risk_band="Medium",
        risk_color="yellow",
        confidence_score=60,
        dampening_score=10,
        git_score=None,
        static_score=55,
        top_findings=(signal,),
    )

    row = build_batch_row(
        repo_path=repo,
        root_path=tmp_path,
        label="human",
        score=score,
        static_result=static,
        git_findings=(),
        git_history_enabled=False,
    )

    assert row["repo"] == "repo"
    assert row["label"] == "human"
    assert row["top_signals"] == ["static.example"]
    assert row["skipped_by_reason"] == {"large": 1}
    assert row["signal.static.example_present"] == 1
    assert row["signal.static.example_score"] == 70
    assert row["signal.static.example_weight"] == 1


def test_write_rows_supports_jsonl_and_csv(tmp_path: Path) -> None:
    rows = [
        {"repo": "a", "label": "human", "signal.static.alpha_score": 10},
        {"repo": "b", "label": "ai", "signal.git.beta_score": 90},
    ]

    jsonl = write_rows(rows, output_format="jsonl", output=None)
    csv_text = write_rows(rows, output_format="csv", output=None)

    assert json.loads(jsonl.splitlines()[0])["repo"] == "a"
    assert "signal.static.alpha_score" in csv_text
    assert "signal.git.beta_score" in csv_text


def test_fixture_corpus_creates_labels_and_discoverable_repos(tmp_path: Path) -> None:
    created = create_fixture_corpus(tmp_path / "fixtures")
    labels = load_labels(tmp_path / "fixtures" / "labels.csv")
    repos = discover_repo_dirs(tmp_path / "fixtures")

    assert len(created) == 8
    assert labels["ai_generated_app"] == "ai_generated"
    assert {repo.name for repo in repos} >= {"human_solo_project", "ai_generated_app"}


def test_recursive_discovery_supports_two_level_label_corpus(tmp_path: Path) -> None:
    ai_repo = tmp_path / "corpus" / "ai" / "repo-a"
    human_repo = tmp_path / "corpus" / "human" / "repo-b"
    review_repo = tmp_path / "corpus" / "_review" / "repo-c"
    ai_repo.mkdir(parents=True)
    human_repo.mkdir(parents=True)
    review_repo.mkdir(parents=True)
    (ai_repo / "README.md").write_text("# ai\n")
    (human_repo / "pyproject.toml").write_text("[project]\nname = 'human'\n")
    (review_repo / "README.md").write_text("# review\n")

    shallow = discover_repo_dirs(tmp_path / "corpus")
    recursive = discover_repo_dirs(tmp_path / "corpus", recursive=True)

    assert shallow == ()
    assert {repo.relative_to(tmp_path / "corpus").as_posix() for repo in recursive} == {
        "ai/repo-a",
        "human/repo-b",
    }
    assert (
        label_for_repo(
            ai_repo,
            root_path=tmp_path / "corpus",
            labels={},
            label_from_parent=True,
        )
        == "ai"
    )


def test_explicit_labels_override_parent_labels(tmp_path: Path) -> None:
    repo = tmp_path / "corpus" / "ai" / "repo-a"
    repo.mkdir(parents=True)

    label = label_for_repo(
        repo,
        root_path=tmp_path / "corpus",
        labels={"ai/repo-a": "ai_assisted"},
        label_from_parent=True,
    )

    assert label == "ai_assisted"
