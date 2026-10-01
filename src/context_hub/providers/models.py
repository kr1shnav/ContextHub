from __future__ import annotations

from pydantic import BaseModel, Field


class GenerationRequest(BaseModel):
    system: str
    user: str
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int = 800


class GenerationResponse(BaseModel):
    text: str
    model: str
    provider: str
    usage: dict[str, int] | None = None
    finish_reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class TaskAnalysis(BaseModel):
    task: str
    task_type: str
    domains: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    likely_files: list[str] = Field(default_factory=list)
    likely_symbols: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    reasoning: str
