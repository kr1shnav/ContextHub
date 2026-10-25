from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


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
    usage: dict[str, object] | None = None
    finish_reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("usage")
    @classmethod
    def validate_usage(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        if value is None:
            return None
        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if field in value and (isinstance(value[field], bool) or not isinstance(value[field], int)):
                raise ValueError(f"usage.{field} must be an integer")
        for field in ("prompt_tokens_details", "completion_tokens_details"):
            if field in value and value[field] is not None and not isinstance(value[field], dict):
                raise ValueError(f"usage.{field} must be an object")
        return value


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
