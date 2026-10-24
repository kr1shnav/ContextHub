from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class RetrievalConfig(BaseModel):
    max_results: int = 20
    max_graph_hops: int = 1
    minimum_score: float = 0.0
    context_budget: int | None = None
    exact_symbol_weight: float = 0.40
    token_weight: float = 0.20
    path_weight: float = 0.20
    graph_weight: float = 0.15
    structural_weight: float = 0.05


class RetrievalQuery(BaseModel):
    task: str
    repository: str | None = None
    path_hint: str | None = None
    symbol_hint: str | None = None
    language_hint: str | None = None
    max_results: int | None = None
    context_budget: int | None = None
    config: RetrievalConfig = Field(default_factory=RetrievalConfig)


class RetrievalResult(BaseModel):
    item_id: str
    item_type: str = "file"
    path: str
    symbol: str | None = None
    score: float
    reasons: list[str] = Field(default_factory=list)
    reason: str | None = None
    signals: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    estimated_characters: int = 0
    estimated_tokens: int = 0

    @model_validator(mode="after")
    def synchronize_reason_fields(self) -> "RetrievalResult":
        if self.reason and not self.reasons:
            self.reasons = [self.reason]
        elif self.reasons and not self.reason:
            self.reason = "; ".join(self.reasons)
        return self

