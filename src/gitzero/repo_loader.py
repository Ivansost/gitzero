from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from .models import LoadedRepository


class RepositoryLoadError(RuntimeError):
    """Raised when GitZero cannot resolve the requested repository."""


def is_repo_url(target: str) -> bool:
    parsed = urlparse(target)
    return parsed.scheme in {"http", "https", "ssh"} or target.startswith("git@")


def is_git_repository(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


@contextmanager
def load_repository(target: str, *, clone_depth: int = 200) -> Iterator[LoadedRepository]:
    """Resolve a local path or clone a public git URL into a temporary directory."""

    if is_repo_url(target):
        temp_dir = Path(tempfile.mkdtemp(prefix="gitzero-"))
        try:
            repo_path = temp_dir / "repo"
            command = [
                "git",
                "clone",
                "--quiet",
                "--depth",
                str(clone_depth),
                target,
                str(repo_path),
            ]
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            if result.returncode != 0:
                stderr = result.stderr.strip() or "git clone failed"
                raise RepositoryLoadError(stderr)
            yield LoadedRepository(source=target, path=repo_path, is_temporary=True)
        except FileNotFoundError as exc:
            raise RepositoryLoadError("git is required to clone repository URLs") from exc
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return

    path = Path(target).expanduser().resolve()
    if not path.exists():
        raise RepositoryLoadError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise RepositoryLoadError(f"Expected a repository folder, got a file: {path}")

    yield LoadedRepository(source=target, path=path, is_temporary=False)
