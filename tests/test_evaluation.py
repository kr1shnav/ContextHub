from pathlib import Path

import pytest

from context_hub.benchmark import BenchmarkDataset
from context_hub.evaluation import evaluate_dataset, validate_k_values
from context_hub.retrieval.models import RetrievalResult


def dataset(expected, *, ambiguous=False):
    return BenchmarkDataset.model_validate({"version": "1.0", "name": "test", "tasks": [{"id": f"rh-{index:03d}", "query": "test query", "expected": expected, "rationale": "test rationale", "ambiguous": ambiguous} for index in range(1, 21)]})


class FakeEngine:
    def __init__(self, results): self.results = results
    def search(self, query): return self.results


def result(item_id, path, symbol=None):
    return RetrievalResult(item_id=item_id, path=path, symbol=symbol, score=1)


def test_perfect_file_ranking_and_aggregation():
    report = evaluate_dataset(dataset([{"path": "a.py"}]), FakeEngine([result("a", "a.py"), result("b", "b.py")]), [1, 3])
    assert report.aggregate["1"] == {"precision": 1.0, "recall": 1.0, "mrr": 1.0}
    assert report.aggregate["3"]["precision"] == pytest.approx(1 / 3)


def test_missing_relevant_result_has_zero_recall_and_mrr():
    report = evaluate_dataset(dataset([{"path": "a.py"}]), FakeEngine([result("b", "b.py")]), [1])
    assert report.aggregate["1"] == {"precision": 0.0, "recall": 0.0, "mrr": 0.0}


def test_duplicate_results_do_not_count_twice():
    report = evaluate_dataset(dataset([{"path": "a.py"}]), FakeEngine([result("a", "a.py"), result("a", "a.py")]), [2])
    assert report.aggregate["2"]["recall"] == 1.0
    assert report.queries[0].retrieved_items == 2


def test_empty_results_and_k_larger_than_results():
    report = evaluate_dataset(dataset([{"path": "a.py"}]), FakeEngine([]), [5])
    assert report.aggregate["5"] == {"precision": 0.0, "recall": 0.0, "mrr": 0.0}


def test_symbol_matching_does_not_accept_file_only_result_and_ambiguous_is_reported():
    data = dataset([{"path": "a.py", "symbols": ["target"]}], ambiguous=True)
    report = evaluate_dataset(data, FakeEngine([result("file", "a.py")]), [1])
    assert report.aggregate["1"]["recall"] == 0.0
    assert report.ambiguous_query_count == 20


def test_symbol_ranking_and_k_validation():
    data = dataset([{"path": "a.py", "symbols": ["target"]}])
    report = evaluate_dataset(data, FakeEngine([result("wrong", "b.py"), result("right", "a.py", "target")]), [2])
    assert report.aggregate["2"]["mrr"] == pytest.approx(0.5)
    assert validate_k_values([5, 1, 5]) == [1, 5]
    with pytest.raises(ValueError): validate_k_values([0])
