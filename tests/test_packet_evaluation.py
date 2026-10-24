from pathlib import Path

import pytest

from context_hub.benchmark import BenchmarkDataset
from context_hub.orchestration.models import ContextBudget, ContextEvidence, ContextPacket, ContextPlan, ContextStatistics
from context_hub.packet_evaluation import evaluate_packets
from context_hub.providers.models import TaskAnalysis


def data(expected, *, ambiguous=False):
    return BenchmarkDataset.model_validate({"version": "1.0", "name": "test", "tasks": [{"id": f"rh-{i:03d}", "query": "test query", "expected": expected, "rationale": "test rationale", "ambiguous": ambiguous} for i in range(1, 21)]})


def packet(items, tokens=10, files=None):
    evidence = [ContextEvidence(id=f"i{i}", path=path, symbol=symbol, source="retrieval", score=1, reason="test", estimated_tokens=1) for i, (path, symbol) in enumerate(items)]
    return ContextPacket(task="test query", task_analysis=TaskAnalysis(task="test query", task_type="task", confidence=.5, reasoning="test"), context_plan=ContextPlan(task="test query", task_type="task"), files=evidence, statistics=ContextStatistics(estimated_tokens=tokens, files_selected=files if files is not None else len({p for p, _ in items})))


class Builder:
    def __init__(self, value=None, error=None): self.value, self.error = value, error
    def build(self, task):
        if self.error: raise self.error
        return self.value


def test_perfect_file_and_symbol_evidence():
    report = evaluate_packets(data([{"path": "a.py", "symbols": ["target"]}]), Builder(packet([("a.py", "target")])), ContextBudget(max_files=2, max_tokens=20))
    assert report.aggregate["file_precision"] == 1
    assert report.aggregate["file_recall"] == 1
    assert report.aggregate["symbol_precision"] == 1
    assert report.aggregate["symbol_recall"] == 1
    assert report.aggregate["relevant_evidence_coverage"] == 1


def test_missing_relevant_and_irrelevant_extra_files():
    report = evaluate_packets(data([{"path": "a.py"}]), Builder(packet([("b.py", None), ("a.py", None)])), ContextBudget(max_files=3, max_tokens=20))
    assert report.aggregate["file_precision"] == .5
    assert report.aggregate["file_recall"] == 1


def test_empty_packet_budget_violation_and_ambiguous_label():
    report = evaluate_packets(data([{"path": "a.py"}], ambiguous=True), Builder(packet([], tokens=30, files=3)), ContextBudget(max_files=2, max_tokens=20))
    assert report.aggregate["relevant_evidence_coverage"] == 0
    assert report.aggregate["budget_compliance_rate"] == 0
    assert report.ambiguous_query_count == 20


def test_missing_metadata_is_failure_not_zero_score():
    report = evaluate_packets(data([{"path": "a.py"}]), Builder(error=RuntimeError("provider failed")), ContextBudget())
    assert report.failed_query_count == 20
    assert report.aggregate["file_recall"] is None
    assert report.queries[0].status == "failed"
    assert "provider failed" in report.queries[0].error


def test_token_percentiles_and_budget_compliance():
    class VaryingBuilder:
        n = 0
        def build(self, task):
            self.n += 1
            return packet([("a.py", None)], tokens=self.n)
    report = evaluate_packets(data([{"path": "a.py"}]), VaryingBuilder(), ContextBudget(max_files=1, max_tokens=10))
    assert report.token_usage["p50"] == 10.0
    assert report.token_usage["p95"] == 19.0
    assert report.aggregate["budget_compliance_rate"] == 1
