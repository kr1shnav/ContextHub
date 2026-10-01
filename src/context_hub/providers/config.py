from __future__ import annotations

import os
from pydantic import BaseModel, Field


class ProviderSettings(BaseModel):
    provider: str = "nebius"
    model: str = "nvidia/nemotron-3-super-120b-a12b"
    api_key: str | None = None
    base_url: str = "https://api.tokenfactory.nebius.com/v1"
    timeout: float = Field(default=60.0, gt=0)
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_tokens: int = Field(default=800, gt=0)
    max_context_chars: int = Field(default=12000, gt=0)
    retries: int = Field(default=2, ge=0, le=5)

    @classmethod
    def from_env(cls) -> "ProviderSettings":
        values: dict[str, object] = {}
        mapping = {"NEBIUS_MODEL": "model", "NEBIUS_API_KEY": "api_key", "NEBIUS_BASE_URL": "base_url"}
        for env, field in mapping.items():
            if os.getenv(env): values[field] = os.environ[env]
        for env, field in (("CONTEXT_HUB_TIMEOUT", "timeout"), ("CONTEXT_HUB_TEMPERATURE", "temperature"), ("CONTEXT_HUB_MAX_TOKENS", "max_tokens"), ("CONTEXT_HUB_MAX_CONTEXT_CHARS", "max_context_chars"), ("CONTEXT_HUB_RETRIES", "retries")):
            if os.getenv(env): values[field] = os.environ[env]
        return cls(**values)
