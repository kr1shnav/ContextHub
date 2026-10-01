from __future__ import annotations

import json
import subprocess
from pathlib import Path
from .models import ContextBudget, ContextEvidence, ContextPacket, ContextPlan, ContextStatistics
from ..analysis import analyze_task
from ..graph import CodeGraph, RelationshipType, build_code_graph
from ..providers import LLMProvider, ProviderError
from ..providers.config import ProviderSettings
from ..providers.models import GenerationRequest, TaskAnalysis
from ..providers.prompts import SYSTEM_PROMPT
from ..retrieval import RetrievalEngine, RetrievalQuery
from ..scanner import scan_repository


class ContextOrchestrator:
    """Coordinates existing repository intelligence into a bounded context packet."""

    def __init__(self, root: Path, provider: LLMProvider, *, budget: ContextBudget | None = None, settings: ProviderSettings | None = None):
        self.root = root.resolve(); self.provider = provider; self.budget = budget or ContextBudget(); self.settings = settings or ProviderSettings.from_env()

    def build(self, task: str, *, limit: int = 20) -> ContextPacket:
        analysis = analyze_task(task, self.provider, self.root, self.settings, limit=limit)
        repository = scan_repository(self.root)
        indexed_paths = {item.path for item in repository.files}
        graph = build_code_graph(repository)
        queries = _queries(task, analysis)
        results = _merge_results(self.root, queries, limit)
        plan = _make_plan(task, analysis, results, indexed_paths, self.budget)
        graph_items = _expand(graph, plan.candidate_paths, plan.graph_hops, plan.include_dependencies, plan.include_dependents)
        evidence = _evidence(results, graph_items, self.root, indexed_paths)
        reasoning = self._reason(evidence, analysis)
        if reasoning:
            evidence = _apply_reasoning(evidence, reasoning, indexed_paths)
        selected = _budget(evidence, self.budget)
        return _packet(task, analysis, plan, selected, len(repository.files), len(graph.node_data), self.root, graph_items)

    def _reason(self, evidence: list[ContextEvidence], analysis: TaskAnalysis) -> dict[str, object] | None:
        supplied = [e.model_dump(exclude={"content"}) for e in evidence[:20]]
        prompt = json.dumps({"task_analysis": analysis.model_dump(), "evidence": supplied}, sort_keys=True)
        try:
            response = self.provider.generate(GenerationRequest(system=SYSTEM_PROMPT + " Only reference supplied evidence paths. Return JSON with priority_paths, important_symbols, missing_context, constraints, reasoning.", user=prompt[:self.settings.max_context_chars], model=self.settings.model, temperature=self.settings.temperature, max_tokens=self.settings.max_tokens))
            data = json.loads(response.text)
            allowed = {e.path for e in evidence}
            data["priority_paths"] = [p for p in data.get("priority_paths", []) if p in allowed]
            data["important_symbols"] = [s for s in data.get("important_symbols", []) if any(e.symbol == s for e in evidence)]
            return data
        except (ProviderError, ValueError, TypeError, json.JSONDecodeError):
            return None


def _queries(task: str, analysis: TaskAnalysis) -> list[str]:
    values = [task, *analysis.domains, *analysis.keywords, *analysis.required_context]
    return list(dict.fromkeys(v.strip() for v in values if v.strip()))[:8]


def _merge_results(root: Path, queries: list[str], limit: int):
    db = root / ".context-hub" / "index.db"
    if not db.is_file(): return []
    merged = {}
    engine = RetrievalEngine(db)
    for query in queries:
        for result in engine.search(RetrievalQuery(task=query, max_results=limit)):
            old = merged.get(result.item_id)
            if old is None or result.score > old.score: merged[result.item_id] = result
    return sorted(merged.values(), key=lambda r: (-r.score, r.path, r.symbol or ""))


def _make_plan(task, analysis, results, paths, budget):
    candidates = [r.path for r in results if r.path in paths]
    candidates += [p for p in analysis.likely_files if p in paths and p not in candidates]
    return ContextPlan(task=task, task_type=analysis.task_type, domains=analysis.domains, queries=_queries(task, analysis), candidate_paths=candidates, required_symbols=analysis.likely_symbols, graph_hops=min(budget.max_graph_hops, 2), constraints=analysis.constraints, reasoning=analysis.reasoning)


def _expand(graph: CodeGraph, paths, hops, deps, dependents):
    found = []
    for path in sorted(set(paths)):
        node = f"file:{path}"
        frontier = {node}
        for distance in range(1, hops + 1):
            next_nodes = set()
            for current in sorted(frontier):
                for edge in sorted(graph.edges, key=lambda e: (e.source, e.target, e.kind)):
                    if (deps and edge.source == current and edge.kind in {RelationshipType.DEPENDS_ON, RelationshipType.IMPORTS}) or (dependents and edge.target == current and edge.kind in {RelationshipType.DEPENDS_ON, RelationshipType.IMPORTS}):
                        target = edge.target if edge.source == current else edge.source
                        next_nodes.add(target)
                        item = graph.get_node(target)
                        if item and item.path: found.append((item.path, edge.kind, distance, path))
            frontier = next_nodes
    return found


def _evidence(results, graph_items, root, paths):
    evidence = [ContextEvidence(id=r.item_id, path=r.path, symbol=r.symbol, source="retrieval", score=min(1, r.score), reason="; ".join(r.reasons) or "retrieval match", estimated_tokens=r.estimated_tokens, metadata=r.metadata) for r in results if r.path in paths]
    seen = {(e.path, e.symbol) for e in evidence}
    for path, edge, distance, source in graph_items:
        key = (path, None)
        if key not in seen:
            evidence.append(ContextEvidence(id=f"graph:{source}:{path}:{distance}", path=path, source="graph", score=max(0.1, 0.7 - distance * 0.15), reason=f"{edge} related to {source}", distance=distance, metadata={"edge": str(edge)})); seen.add(key)
    return sorted(evidence, key=lambda e: (-e.score, e.path, e.symbol or ""))


def _apply_reasoning(evidence, reasoning, paths):
    priorities = set(reasoning.get("priority_paths", []))
    for item in evidence:
        if item.path in priorities: item.score = min(1, item.score + 0.1); item.reason += "; Nemotron priority"
    return sorted(evidence, key=lambda e: (-e.score, e.path, e.symbol or ""))


def _budget(evidence, budget):
    selected=[]; files=set(); tokens=chars=0
    for item in evidence:
        content = None
        candidate = Path(item.path)
        full = None
        # Paths are repository-relative and are checked by the caller's root below in _packet.
        if item.path not in files and len(files) >= budget.max_files: continue
        if item.path not in files and tokens + item.estimated_tokens > budget.max_tokens and selected: continue
        if item.path not in files: files.add(item.path)
        selected.append(item); tokens += item.estimated_tokens; chars += item.estimated_tokens * 4
        if tokens >= budget.max_tokens or chars >= budget.max_characters: break
    return selected


def _packet(task, analysis, plan, evidence, considered, graph_count, root, graph_items):
    safe=[]; selected_paths=set()
    for item in evidence:
        if item.path in selected_paths: continue
        path = (root / item.path).resolve()
        if not path.is_relative_to(root) or path.name.startswith(".env") or path.name in {"credentials", "secrets"} or path.suffix.lower() in {".pem", ".key", ".p12"}: continue
        if path.is_file():
            item.content = path.read_text(encoding="utf-8", errors="replace")
            item.estimated_tokens = max(1, len(item.content) // 4)
            safe.append(item)
            selected_paths.add(item.path)
    sections = [f"# Task\n\n{task}", "# Relevant Files"]
    for item in safe: sections.append(f"## {item.path}\n\nReason: {item.reason}\n\n```\n{item.content}\n```")
    stats = ContextStatistics(files_considered=considered, files_selected=len({e.path for e in safe}), graph_nodes_considered=graph_count, graph_nodes_selected=len(graph_items), estimated_tokens=sum(e.estimated_tokens for e in safe))
    return ContextPacket(task=task, task_analysis=analysis, context_plan=plan, files=safe, graph_evidence=[e for e in safe if e.source == "graph"], constraints=analysis.constraints, assembled_context="\n\n".join(sections), statistics=stats)
