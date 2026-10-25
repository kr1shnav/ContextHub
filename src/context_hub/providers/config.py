from __future__ import annotations

import os
from urllib.parse import urlparse
from typing import Literal
from pydantic import BaseModel, Field, field_validator


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
    reasoning_effort: Literal["none", "low", "high"] = "none"

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("base_url must not contain embedded credentials")
        return value.rstrip("/")


    @classmethod
    def from_env(cls) -> "ProviderSettings":
        values: dict[str, object] = {}
        provider = os.getenv("CONTEXT_HUB_PROVIDER", "nebius").strip().lower()
        values["provider"] = provider
        defaults = {
            "nebius": ("nvidia/nemotron-3-super-120b-a12b", "https://api.tokenfactory.nebius.com/v1", "NEBIUS"),
            "nvidia": ("nvidia/nemotron-3.5-super-vl-120b-a12b", "https://integrate.api.nvidia.com/v1", "NVIDIA"),
        }
        default_model, default_url, prefix = defaults.get(
            provider, (cls.model_fields["model"].default, cls.model_fields["base_url"].default, provider.upper()))
        values["model"] = os.getenv(f"{prefix}_MODEL", default_model)
        values["base_url"] = os.getenv(f"{prefix}_BASE_URL", default_url)
        if provider == "nvidia":
            values["reasoning_effort"] = os.getenv("NVIDIA_REASONING_EFFORT", "none")
        if os.getenv(f"{prefix}_API_KEY"):
            values["api_key"] = os.environ[f"{prefix}_API_KEY"]
        for env, field in (("CONTEXT_HUB_TIMEOUT", "timeout"), ("CONTEXT_HUB_TEMPERATURE", "temperature"), ("CONTEXT_HUB_MAX_TOKENS", "max_tokens"), ("CONTEXT_HUB_MAX_CONTEXT_CHARS", "max_context_chars"), ("CONTEXT_HUB_RETRIES", "retries")):
            if os.getenv(env):
                values[field] = os.environ[env]
        return cls(**values)
