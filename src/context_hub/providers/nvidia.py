from __future__ import annotations

import json
import time

import httpx

from .base import LLMProvider, ProviderError
from .config import ProviderSettings
from .models import GenerationRequest, GenerationResponse


class NVIDIAProvider(LLMProvider):
    """NVIDIA API Catalog's OpenAI-compatible hosted inference provider."""

    name = "NVIDIA"

    def __init__(self, settings: ProviderSettings | None = None, client: httpx.Client | None = None):
        self.settings = settings or ProviderSettings.from_env()
        self.client = client

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not self.settings.api_key:
            raise ProviderError("NVIDIA API key is not configured. Set NVIDIA_API_KEY before using the NVIDIA provider.")
        payload = {
            "model": request.model or self.settings.model,
            "messages": [{"role": "system", "content": request.system}, {"role": "user", "content": request.user}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.settings.api_key}", "Accept": "application/json", "Content-Type": "application/json"}
        client = self.client or httpx.Client(timeout=self.settings.timeout)
        try:
            for attempt in range(self.settings.retries + 1):
                try:
                    response = client.post(self.settings.base_url.rstrip("/") + "/chat/completions", headers=headers, json=payload)
                    if response.status_code in (429, 500, 502, 503, 504) and attempt < self.settings.retries:
                        time.sleep(0.25 * (2 ** attempt))
                        continue
                    if response.status_code == 401:
                        raise ProviderError(self._error_message(response, "authentication failed. Check NVIDIA_API_KEY."))
                    if response.status_code == 403:
                        raise ProviderError(self._error_message(response, "access denied for this NVIDIA API Catalog account or model."))
                    if response.status_code == 404:
                        raise ProviderError(self._error_message(response, "model or endpoint was not found. Check NVIDIA_MODEL and NVIDIA_BASE_URL."))
                    if response.status_code == 429:
                        raise ProviderError(self._error_message(response, "rate limit or quota reached. Try again later."))
                    if 500 <= response.status_code <= 599:
                        if attempt >= self.settings.retries:
                            raise ProviderError(self._error_message(response, "NVIDIA API Catalog returned an upstream server error."))
                        continue
                    response.raise_for_status()
                    data = response.json()
                    choice = data["choices"][0]
                    content = choice["message"]["content"]
                    if not isinstance(content, str):
                        raise ValueError("response content is not text")
                    return GenerationResponse(text=content, model=data.get("model", payload["model"]), provider=self.name, usage=data.get("usage"), finish_reason=choice.get("finish_reason"))
                except httpx.TimeoutException as exc:
                    if attempt >= self.settings.retries:
                        raise ProviderError("NVIDIA request timed out.") from exc
                except httpx.RequestError as exc:
                    if attempt >= self.settings.retries:
                        raise ProviderError("Unable to reach NVIDIA API Catalog.") from exc
        except ProviderError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError("NVIDIA returned an invalid response.") from exc
        finally:
            if self.client is None:
                client.close()
        raise ProviderError("NVIDIA request failed.")

    @staticmethod
    def _error_message(response: httpx.Response, fallback: str) -> str:
        """Preserve status and a safe, bounded provider error without headers or credentials."""
        detail = ""
        try:
            data = response.json()
            error = data.get("error", data) if isinstance(data, dict) else data
            if isinstance(error, dict):
                detail = str(error.get("message") or error.get("detail") or error.get("type") or "")
            elif isinstance(error, str):
                detail = error
        except (ValueError, TypeError):
            detail = response.text
        detail = " ".join(detail.split())[:300]
        suffix = f" {detail}" if detail else ""
        return f"NVIDIA HTTP {response.status_code}: {fallback}{suffix}"
