from __future__ import annotations

from pathlib import Path

from typer.main import get_command
from typer.testing import CliRunner

from gitzero.cli import app

runner = CliRunner()


def test_public_commands_are_scan_and_help() -> None:
    assert set(get_command(app).commands) == {"scan", "help"}
    result = runner.invoke(app, ["help"])
    assert result.exit_code == 0
    assert "gitzero scan ." in result.output
    assert "--verbose" not in result.output
    assert "batch" not in result.output


def test_scan_local_source_folder(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def greet(name):\n    return 'Hello ' + name\n")
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Scan Summary" in result.output
    assert "Highest-Signal Files" in result.output
    assert "Signal Map" in result.output
    assert "does not prove" in " ".join(result.output.split())


def test_missing_repository_has_readable_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["scan", str(tmp_path / "missing")])
    assert result.exit_code == 1
    assert "Could not load repository" in result.output


def test_removed_scan_options_are_rejected() -> None:
    result = runner.invoke(app, ["scan", ".", "--verbose"])
    assert result.exit_code == 2
