"""Reproducible retrieval benchmark dataset and validation helpers."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

DATASET_VERSION = "1.0"
DEFAULT_DATASET = Path(__file__).with_name("data") / "retrieval_benchmark_v1.json"


class ExpectedEvidence(BaseModel):
    path: str = Field(min_length=1)
    symbols: list[str] = Field(default_factory=list)
    relevance: int = Field(default=3, ge=1, le=3)

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("expected paths must be repository-relative POSIX paths")
        return value


class BenchmarkTask(BaseModel):
    id: str = Field(pattern=r"^rh-[0-9]{3}$")
    query: str = Field(min_length=5)
    expected: list[ExpectedEvidence] = Field(min_length=1)
    rationale: str = Field(min_length=10)
    ambiguous: bool = False

    @field_validator("expected")
    @classmethod
    def unique_expected_paths(cls, value: list[ExpectedEvidence]) -> list[ExpectedEvidence]:
        if len({item.path for item in value}) != len(value):
            raise ValueError("expected paths must be unique within a task")
        return value


class BenchmarkDataset(BaseModel):
    version: str = Field(pattern=r"^1\.0$")
    name: str = Field(min_length=1)
    tasks: list[BenchmarkTask] = Field(min_length=20)

    @field_validator("tasks")
    @classmethod
    def unique_ids(cls, value: list[BenchmarkTask]) -> list[BenchmarkTask]:
        ids = [task.id for task in value]
        if len(set(ids)) != len(ids):
            raise ValueError("task IDs must be unique")
        return value


def load_dataset(path: Path | None = None) -> BenchmarkDataset:
    """Load the checked-in dataset without network or provider access."""
    source = path or DEFAULT_DATASET
    return BenchmarkDataset.model_validate_json(source.read_text(encoding="utf-8"))


def verify_expected_evidence(dataset: BenchmarkDataset, root: Path) -> list[str]:
    """Return deterministic errors for paths/symbols absent from the repository."""
    from .scanner import scan_repository

    files = {item.path: item for item in scan_repository(root)}
    errors: list[str] = []
    for task in dataset.tasks:
        for expected in task.expected:
            item = files.get(expected.path)
            if item is None:
                errors.append(f"{task.id}: missing file {expected.path}")
                continue
            symbols = {symbol.name for symbol in (item.parsed.symbols if item.parsed else [])}
            for symbol in expected.symbols:
                if symbol not in symbols:
                    errors.append(f"{task.id}: missing symbol {symbol} in {expected.path}")
    return errors


def summarize(dataset: BenchmarkDataset) -> dict[str, int | str]:
    return {"name": dataset.name, "version": dataset.version, "tasks": len(dataset.tasks), "ambiguous": sum(task.ambiguous for task in dataset.tasks)}
