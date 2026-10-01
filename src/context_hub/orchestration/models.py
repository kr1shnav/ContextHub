from __future__ import annotations

from pydantic import BaseModel, Field
from ..providers.models import TaskAnalysis


class ContextPlan(BaseModel):
    task: str
    task_type: str
    domains: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    candidate_paths: list[str] = Field(default_factory=list)
    required_symbols: list[str] = Field(default_factory=list)
    graph_hops: int = 1
    include_dependencies: bool = True
    include_dependents: bool = True
    include_documentation: bool = True
    include_recent_changes: bool = False
    constraints: list[str] = Field(default_factory=list)
    reasoning: str = ""


class ContextEvidence(BaseModel):
    id: str
    path: str
    symbol: str | None = None
    source: str
    score: float = Field(ge=0, le=1)
    reason: str
    distance: int = 0
    content: str | None = None
    estimated_tokens: int = 0
    metadata: dict[str, object] = Field(default_factory=dict)


class ContextBudget(BaseModel):
    max_files: int = 10
    max_tokens: int = 6000
    max_characters: int = 24000
    max_graph_hops: int = 2
    max_refinement_cycles: int = 1


class ContextStatistics(BaseModel):
    files_considered: int = 0
    files_selected: int = 0
    graph_nodes_considered: int = 0
    graph_nodes_selected: int = 0
    estimated_tokens: int = 0


class ContextPacket(BaseModel):
    task: str
    task_analysis: TaskAnalysis
    context_plan: ContextPlan
    files: list[ContextEvidence] = Field(default_factory=list)
    symbols: list[ContextEvidence] = Field(default_factory=list)
    dependencies: list[ContextEvidence] = Field(default_factory=list)
    graph_evidence: list[ContextEvidence] = Field(default_factory=list)
    documentation: list[ContextEvidence] = Field(default_factory=list)
    git_evidence: list[ContextEvidence] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assembled_context: str = ""
    statistics: ContextStatistics = Field(default_factory=ContextStatistics)
