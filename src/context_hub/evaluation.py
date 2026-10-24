"""Deterministic retrieval evaluation for the Phase 10 benchmark."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from .benchmark import BenchmarkDataset, BenchmarkTask
from .retrieval.models import RetrievalQuery, RetrievalResult


class Searcher(Protocol):
    def search(self, query: RetrievalQuery) -> list[RetrievalResult]: ...


class QueryMetrics(BaseModel):
    id: str
    query: str
    ambiguous: bool = False
    relevant_items: int
    retrieved_items: int
    by_k: dict[str, dict[str, float]]


class EvaluationReport(BaseModel):
    dataset_version: str
    dataset_name: str
    k_values: list[int]
    query_count: int
    ambiguous_query_count: int
    aggregate: dict[str, dict[str, float]]
    queries: list[QueryMetrics]
    index: dict[str, object] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


def validate_k_values(values: list[int]) -> list[int]:
    if not values or any(value <= 0 for value in values):
        raise ValueError("K values must be positive integers")
    return sorted(set(values))


def _relevant_units(task: BenchmarkTask) -> set[tuple[str, str | None]]:
    units: set[tuple[str, str | None]] = set()
    for expected in task.expected:
        if expected.symbols:
            units.update((expected.path, symbol) for symbol in expected.symbols)
        else:
            units.add((expected.path, None))
    return units


def _result_unit(result: RetrievalResult) -> tuple[str, str | None]:
    return result.path, result.symbol


def _is_match(result: RetrievalResult, relevant: set[tuple[str, str | None]]) -> tuple[str, str | None] | None:
    unit = _result_unit(result)
    if unit in relevant:
        return unit
    # A file-level expected item matches any result for that path. Symbol-level
    # expected items intentionally do not match a file-only result.
    file_unit = (result.path, None)
    return file_unit if file_unit in relevant else None


def _metrics_for_k(results: list[RetrievalResult], relevant: set[tuple[str, str | None]], k: int) -> dict[str, float]:
    seen_results: set[str] = set()
    seen_relevant: set[tuple[str, str | None]] = set()
    hits = 0
    reciprocal_rank = 0.0
    for rank, result in enumerate(results[:k], 1):
        identity = result.item_id or f"{result.item_type}:{result.path}:{result.symbol or ''}"
        if identity in seen_results:
            continue
        seen_results.add(identity)
        match = _is_match(result, relevant)
        if match is not None and match not in seen_relevant:
            seen_relevant.add(match)
            hits += 1
            if reciprocal_rank == 0.0:
                reciprocal_rank = 1.0 / rank
    return {
        "precision": hits / k,
        "recall": hits / len(relevant) if relevant else 0.0,
        "mrr": reciprocal_rank,
    }


def evaluate_dataset(dataset: BenchmarkDataset, engine: Searcher, k_values: list[int], *, index_metadata: dict[str, object] | None = None) -> EvaluationReport:
    ks = validate_k_values(k_values)
    per_query: list[QueryMetrics] = []
    aggregate = {str(k): {metric: 0.0 for metric in ("precision", "recall", "mrr")} for k in ks}
    for task in dataset.tasks:
        relevant = _relevant_units(task)
        results = engine.search(RetrievalQuery(task=task.query, max_results=max(ks)))
        metrics = {str(k): _metrics_for_k(results, relevant, k) for k in ks}
        for key, values in metrics.items():
            for metric, value in values.items():
                aggregate[key][metric] += value
        per_query.append(QueryMetrics(id=task.id, query=task.query, ambiguous=task.ambiguous,
                                      relevant_items=len(relevant), retrieved_items=len(results), by_k=metrics))
    count = len(per_query)
    if count:
        for values in aggregate.values():
            for metric in values:
                values[metric] /= count
    return EvaluationReport(dataset_version=dataset.version, dataset_name=dataset.name, k_values=ks,
                            query_count=count, ambiguous_query_count=sum(q.ambiguous for q in per_query),
                            aggregate=aggregate, queries=per_query, index=index_metadata or {})


def index_metadata(database_path: Path, repository: Path) -> dict[str, object]:
    from .storage import IndexDatabase

    database = IndexDatabase(database_path)
    try:
        database.open()
        status = database.status(repository.resolve())
    finally:
        database.close()
    if not status:
        return {"database": str(database_path), "repository": str(repository.resolve())}
    return {"database": str(database_path), "repository": str(repository.resolve()),
            "files": status["files"], "symbols": status["symbols"], "imports": status["imports"],
            "last_indexed": status["last_indexed"]}


def render_summary(report: EvaluationReport) -> str:
    lines = [f"Retrieval evaluation — dataset {report.dataset_version} ({report.query_count} queries)",
             f"Ambiguous queries: {report.ambiguous_query_count}"]
    for k in report.k_values:
        values = report.aggregate[str(k)]
        lines.append(f"P@{k}: {values['precision']:.3f}  R@{k}: {values['recall']:.3f}  MRR@{k}: {values['mrr']:.3f}")
    return "\n".join(lines)
