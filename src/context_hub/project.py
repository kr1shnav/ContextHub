"""Project discovery and Phase 1 initialization."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .config import METADATA_FILE, metadata_dir


def git_root(path: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(result.stdout.strip()).resolve()


def init_project(root: Path) -> tuple[Path, bool]:
    root = root.resolve()
    directory = metadata_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    repository_root = git_root(root)
    data = {
        "schema_version": 1,
        "context_hub_version": __version__,
        "project_root": str(root),
        "git_root": str(repository_root) if repository_root else None,
        "initialized_at": datetime.now(timezone.utc).isoformat(),
    }
    (directory / METADATA_FILE).write_text(json.dumps(data,
                                                      indent=2) + "\n", encoding="utf-8")
    return directory, repository_root is not None


def project_status(root: Path) -> dict[str, object] | None:
    path = metadata_dir(root) / METADATA_FILE
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
