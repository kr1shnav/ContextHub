import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from context_hub.benchmark import BenchmarkDataset, load_dataset, verify_expected_evidence


def test_load_benchmark_dataset_is_offline_and_versioned():
    dataset = load_dataset()
    assert dataset.version == "1.0"
    assert len(dataset.tasks) >= 20
    assert any(task.ambiguous for task in dataset.tasks)


def test_dataset_expected_evidence_matches_repository():
    dataset = load_dataset()
    assert verify_expected_evidence(dataset, Path(__file__).parents[1]) == []


def test_duplicate_ids_are_rejected():
    data = {"version": "1.0", "name": "test", "tasks": [
        {"id": "rh-001", "query": "first question", "expected": [{"path": "a.py"}], "rationale": "enough rationale"},
        {"id": "rh-001", "query": "second question", "expected": [{"path": "b.py"}], "rationale": "enough rationale"},
    ]}
    with pytest.raises(ValidationError, match="unique"):
        BenchmarkDataset.model_validate(data)


def test_duplicate_ids_are_rejected_in_full_sized_dataset():
    task = {"id": "rh-001", "query": "valid question", "expected": [{"path": "a.py"}], "rationale": "enough rationale"}
    with pytest.raises(ValidationError, match="unique"):
        BenchmarkDataset.model_validate({"version": "1.0", "name": "test", "tasks": [task] * 20})


@pytest.mark.parametrize("change", [
    {"id": "bad", "query": "query", "expected": [{"path": "a.py"}], "rationale": "rationale"},
    {"id": "rh-001", "query": "query", "expected": [{"path": "../secret.py"}], "rationale": "rationale"},
    {"id": "rh-001", "query": "query", "expected": [{"path": "a.py", "relevance": 4}], "rationale": "rationale"},
])
def test_malformed_entries_are_rejected(change):
    data = {"version": "1.0", "name": "test", "tasks": [change] * 20}
    with pytest.raises(ValidationError):
        BenchmarkDataset.model_validate(data)


def test_custom_json_dataset_can_be_loaded(tmp_path: Path):
    source = {"version": "1.0", "name": "custom", "tasks": [{"id": f"rh-{index:03d}", "query": "a valid query", "expected": [{"path": "a.py"}], "rationale": "a valid rationale"} for index in range(1, 21)]}
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    assert load_dataset(path).name == "custom"
