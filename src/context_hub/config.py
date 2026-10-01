"""Project configuration and metadata paths."""

from pathlib import Path

METADATA_DIR = ".context-hub"
METADATA_FILE = "project.json"


def metadata_dir(root: Path) -> Path:
    return root / METADATA_DIR
