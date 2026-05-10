from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

FIXTURE_LABELS = {
    "ai_assisted_edited_app": "ai_assisted",
    "ai_generated_app": "ai_generated",
    "explicit_ai_config_repo": "hard_ai_evidence",
    "framework_starter": "template",
    "generated_vendor_heavy_repo": "generated_heavy",
    "human_solo_project": "human",
    "mature_oss_project": "human",
    "no_history_repo": "unknown_no_history",
}


def create_fixture_corpus(output_dir: Path, *, force: bool = False) -> tuple[Path, ...]:
    if output_dir.exists() and any(output_dir.iterdir()):
        if not force:
            raise ValueError(f"{output_dir} already exists and is not empty")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    created = [
        _human_solo_project(output_dir / "human_solo_project"),
        _mature_oss_project(output_dir / "mature_oss_project"),
        _framework_starter(output_dir / "framework_starter"),
        _ai_generated_app(output_dir / "ai_generated_app"),
        _ai_assisted_edited_app(output_dir / "ai_assisted_edited_app"),
        _no_history_repo(output_dir / "no_history_repo"),
        _explicit_ai_config_repo(output_dir / "explicit_ai_config_repo"),
        _generated_vendor_heavy_repo(output_dir / "generated_vendor_heavy_repo"),
    ]
    _write_labels(output_dir)
    return tuple(created)


def _human_solo_project(path: Path) -> Path:
    _write(path / "README.md", "# Human Solo Project\n\nSmall utility with uneven modules.\n")
    _write(
        path / "src" / "parser.py",
        "def parse_line(line):\n    return line.strip().split(',')\n",
    )
    _write(
        path / "src" / "debuggable.py",
        """
def normalize(items):
    print("checking input")
    result = []
    for item in items:
        if item:
            result.append(item.strip())
    return result
""".strip()
        + "\n",
    )
    _write(
        path / "tests" / "test_parser.py",
        "from src.parser import parse_line\n\n\n"
        "def test_parse_line():\n    assert parse_line('a,b') == ['a', 'b']\n",
    )
    _git_history(path, ["initial thing", "fix teh parser edge case", "add parser test"])
    return path


def _mature_oss_project(path: Path) -> Path:
    _write(path / "README.md", "# Mature OSS Project\n\nParser, cache, and API helpers.\n")
    modules = {
        "src/cache.py": "class Cache:\n    def __init__(self):\n        self.values = {}\n",
        "src/api.py": (
            "def fetch_user(client, user_id):\n"
            "    return client.get(f'/users/{user_id}')\n"
        ),
        "src/cli.py": "def main(argv):\n    return 0 if argv else 2\n",
        "tests/test_cache.py": "def test_cache_shape():\n    assert {'a': 1}['a'] == 1\n",
    }
    for relative, text in modules.items():
        _write(path / relative, text)
    _git_history(
        path,
        [
            "initial import",
            "add cache layer",
            "fix cache invalidation",
            "update cli handling",
            "document api helpers",
        ],
        authors=("Alice Example", "Bob Example", "Chris Example"),
    )
    return path


def _framework_starter(path: Path) -> Path:
    _write(
        path / "package.json",
        '{"scripts":{"dev":"vite --host 0.0.0.0","build":"vite build"},'
        '"dependencies":{"@vitejs/plugin-react":"latest","react":"latest",'
        '"react-dom":"latest"}}\n',
    )
    _write(path / "vite.config.ts", "import react from '@vitejs/plugin-react'\nexport default {}\n")
    _write(path / "src" / "main.tsx", "export function App(): string { return 'hello' }\n")
    _git_history(path, ["create vite starter"])
    return path


def _ai_generated_app(path: Path) -> Path:
    _write(
        path / "README.md",
        "# Modern Task Platform\n\n"
        "A robust, scalable, production-ready dashboard with analytics, authentication, "
        "payments, notifications, and export workflows.\n",
    )
    for name in ("auth", "billing", "dashboard", "notifications", "exports", "analytics"):
        _write(
            path / "src" / f"{name}.ts",
            f"""
export function calculate{name.title()}WorkflowScore(inputValue: number): number {{
  try {{
    if (inputValue < 0) {{
      throw new Error("inputValue must be positive")
    }}
    return inputValue + 1
  }} catch (error) {{
    return 0
  }}
}}
""".strip()
            + "\n",
        )
    _write(path / "tests" / "test_smoke.ts", "expect(App).toBeDefined()\n")
    _git_history(path, ["Initial complete project implementation"])
    return path


def _ai_assisted_edited_app(path: Path) -> Path:
    _ai_generated_app(path)
    _write(
        path / "src" / "debug_notes.py",
        "def inspect_payload(payload):\n    breakpoint()\n    return payload\n",
    )
    _commit(path, "debug auth payload handling", author_name="Human Editor")
    return path


def _no_history_repo(path: Path) -> Path:
    _write(path / "README.md", "# No History Repo\n")
    _write(path / "app.py", "def main():\n    return 'ok'\n")
    return path


def _explicit_ai_config_repo(path: Path) -> Path:
    _write(path / "AGENTS.md", "Use Codex here.\n")
    _write(path / "src" / "main.py", "def main() -> str:\n    return 'ok'\n")
    _git_history(path, ["initial"])
    return path


def _generated_vendor_heavy_repo(path: Path) -> Path:
    _write(path / "README.md", "# Generated Heavy Repo\n")
    _write(path / "src" / "main.py", "def main():\n    return 1\n")
    for index in range(6):
        _write(
            path / "generated" / f"schema_{index}.generated.py",
            f"VALUE_{index} = {index}\n",
        )
    _git_history(path, ["import generated schema files"])
    return path


def _write_labels(output_dir: Path) -> None:
    rows = ["repo,label", *[f"{repo},{label}" for repo, label in sorted(FIXTURE_LABELS.items())]]
    _write(output_dir / "labels.csv", "\n".join(rows) + "\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git_history(
    path: Path,
    messages: list[str],
    *,
    authors: tuple[str, ...] = ("Fixture Author",),
) -> None:
    if shutil.which("git") is None:
        return
    subprocess.run(["git", "init"], cwd=path, check=False, capture_output=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.com"], cwd=path, check=False)
    subprocess.run(["git", "config", "user.name", authors[0]], cwd=path, check=False)
    for index, message in enumerate(messages):
        _write(path / "history" / f"commit_{index}.txt", message + "\n")
        _commit(path, message, author_name=authors[index % len(authors)], index=index)


def _commit(
    path: Path,
    message: str,
    *,
    author_name: str = "Fixture Author",
    index: int = 0,
) -> None:
    if shutil.which("git") is None:
        return
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": f"2024-01-{index + 1:02d}T10:00:00",
        "GIT_COMMITTER_DATE": f"2024-01-{index + 1:02d}T10:00:00",
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": f"{author_name.lower().replace(' ', '.')}@example.com",
    }
    subprocess.run(["git", "add", "."], cwd=path, check=False, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=path,
        env=env,
        check=False,
        capture_output=True,
    )
