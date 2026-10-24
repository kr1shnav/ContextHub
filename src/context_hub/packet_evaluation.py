"""Deterministic context-packet quality and token-efficiency evaluation."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from .benchmark import BenchmarkDataset, BenchmarkTask
from .evaluation import _relevant_units
from .orchestration.models import ContextBudget, ContextPacket


class PacketBuilder(Protocol):
    def build(self, task: str) -> ContextPacket: ...


class PacketQueryResult(BaseModel):
    id: str
    query: str
    ambiguous: bool = False
    status: str
    error: str | None = None
    file_precision: float | None = None
    file_recall: float | None = None
    symbol_precision: float | None = None
    symbol_recall: float | None = None
    relevant_evidence_coverage: float | None = None
    estimated_tokens: int | None = None
    selected_files: int | None = None
    requested_max_tokens: int
    requested_max_files: int
    budget_compliant: bool | None = None


class PacketEvaluationReport(BaseModel):
    dataset_version: str
    dataset_name: str
    query_count: int
    successful_query_count: int
    failed_query_count: int
    ambiguous_query_count: int
    budgets: ContextBudget
    aggregate: dict[str, float | int | None]
    token_usage: dict[str, float | int | None]
    queries: list[PacketQueryResult]
    index: dict[str, object] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


def _percentile(values: list[int], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, int((percentile / 100) * len(ordered) + 0.999999))
    return float(ordered[rank - 1])


def _file_metrics(task: BenchmarkTask, selected_paths: set[str]) -> tuple[float, float]:
    expected_paths = {item.path for item in task.expected}
    relevant = len(selected_paths & expected_paths)
    return (relevant / len(selected_paths) if selected_paths else 0.0,
            relevant / len(expected_paths) if expected_paths else 0.0)


def _symbol_metrics(task: BenchmarkTask, selected: set[tuple[str, str | None]]) -> tuple[float | None, float | None]:
    expected = {(item.path, symbol) for item in task.expected for symbol in item.symbols}
    if not expected:
        return None, None
    actual = {(path, symbol) for path, symbol in selected if symbol is not None}
    hits = len(actual & expected)
    return (hits / len(actual) if actual else 0.0, hits / len(expected))


def _coverage(task: BenchmarkTask, selected: set[tuple[str, str | None]]) -> float:
    expected = _relevant_units(task)
    covered = 0
    for path, symbol in expected:
        if (path, symbol) in selected or (symbol is None and any(p == path for p, _ in selected)):
            covered += 1
    return covered / len(expected) if expected else 0.0


def evaluate_packets(dataset: BenchmarkDataset, builder: PacketBuilder, budget: ContextBudget, *, index_metadata: dict[str, object] | None = None) -> PacketEvaluationReport:
    queries: list[PacketQueryResult] = []
    tokens: list[int] = []
    successful = 0
    for task in dataset.tasks:
        try:
            packet = builder.build(task.query)
            evidence = list(packet.files) + list(packet.symbols) + list(packet.dependencies) + list(packet.documentation) + list(packet.git_evidence)
            selected_paths = {item.path for item in evidence}
            selected_units = {(item.path, item.symbol) for item in evidence}
            file_precision, file_recall = _file_metrics(task, selected_paths)
            symbol_precision, symbol_recall = _symbol_metrics(task, selected_units)
            # Evaluate the material actually present in the packet. Some
            # builders retain a pre-selection estimate in statistics; using it
            # would mark a compliant packet as over budget.
            actual_tokens = packet.statistics.estimated_tokens
            actual_files = packet.statistics.files_selected
            budget_tokens = sum(max(0, item.estimated_tokens) for item in evidence) if evidence else actual_tokens
            budget_files = len(selected_paths) if evidence else actual_files
            compliant = budget_tokens <= budget.max_tokens and budget_files <= budget.max_files
            queries.append(PacketQueryResult(id=task.id, query=task.query, ambiguous=task.ambiguous, status="success",
                file_precision=file_precision, file_recall=file_recall, symbol_precision=symbol_precision,
                symbol_recall=symbol_recall, relevant_evidence_coverage=_coverage(task, selected_units),
                estimated_tokens=actual_tokens, selected_files=actual_files, requested_max_tokens=budget.max_tokens,
                requested_max_files=budget.max_files, budget_compliant=compliant))
            tokens.append(actual_tokens)
            successful += 1
        except Exception as exc:
            queries.append(PacketQueryResult(id=task.id, query=task.query, ambiguous=task.ambiguous, status="failed",
                error=f"{type(exc).__name__}: {exc}", requested_max_tokens=budget.max_tokens, requested_max_files=budget.max_files))
    completed = [item for item in queries if item.status == "success"]
    def avg(field: str) -> float | None:
        values = [getattr(item, field) for item in completed if getattr(item, field) is not None]
        return sum(values) / len(values) if values else None
    aggregate = {field: avg(field) for field in ("file_precision", "file_recall", "symbol_precision", "symbol_recall", "relevant_evidence_coverage")}
    aggregate.update({"budget_compliance_rate": sum(item.budget_compliant is True for item in completed) / len(completed) if completed else None,
                      "average_estimated_tokens": avg("estimated_tokens"), "average_selected_files": avg("selected_files")})
    token_usage = {"estimated": True, "average": avg("estimated_tokens"), "p50": _percentile(tokens, 50), "p95": _percentile(tokens, 95),
                   "requested_max_tokens": budget.max_tokens, "requested_max_files": budget.max_files}
    return PacketEvaluationReport(dataset_version=dataset.version, dataset_name=dataset.name, query_count=len(queries),
        successful_query_count=successful, failed_query_count=len(queries) - successful,
        ambiguous_query_count=sum(item.ambiguous for item in queries), budgets=budget, aggregate=aggregate,
        token_usage=token_usage, queries=queries, index=index_metadata or {})


def render_packet_summary(report: PacketEvaluationReport) -> str:
    aggregate = report.aggregate
    usage = report.token_usage
    return "\n".join([
        f"Packet evaluation — dataset {report.dataset_version} ({report.successful_query_count}/{report.query_count} succeeded)",
        f"File precision: {aggregate['file_precision'] if aggregate['file_precision'] is not None else 'n/a'} | File recall: {aggregate['file_recall'] if aggregate['file_recall'] is not None else 'n/a'}",
        f"Symbol precision: {aggregate['symbol_precision'] if aggregate['symbol_precision'] is not None else 'n/a'} | Symbol recall: {aggregate['symbol_recall'] if aggregate['symbol_recall'] is not None else 'n/a'}",
        f"Relevant coverage: {aggregate['relevant_evidence_coverage'] if aggregate['relevant_evidence_coverage'] is not None else 'n/a'}",
        f"Estimated tokens — average: {usage['average']}, p50: {usage['p50']}, p95: {usage['p95']} | Compliance: {aggregate['budget_compliance_rate']}",
    ])
