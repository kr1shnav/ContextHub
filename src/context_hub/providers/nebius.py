from __future__ import annotations

import json
import time
import httpx
from .base import LLMProvider, ProviderError
from .config import ProviderSettings
from .models import GenerationRequest, GenerationResponse


class NebiusProvider(LLMProvider):
    name = "Nebius"

    def __init__(self, settings: ProviderSettings | None = None, client: httpx.Client | None = None):
        self.settings = settings or ProviderSettings.from_env()
        self.client = client

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not self.settings.api_key:
            raise ProviderError("Nebius API key is not configured. Set NEBIUS_API_KEY before using the Nebius provider.")
        payload = {"model": request.model or self.settings.model, "messages": [{"role": "system", "content": request.system}, {"role": "user", "content": request.user}], "temperature": request.temperature, "max_tokens": request.max_tokens, "response_format": {"type": "json_object"}}
        headers = {"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json"}
        client = self.client or httpx.Client(timeout=self.settings.timeout)
        try:
            for attempt in range(self.settings.retries + 1):
                try:
                    response = client.post(self.settings.base_url.rstrip("/") + "/chat/completions", headers=headers, json=payload)
                    if response.status_code in (429, 500, 502, 503, 504) and attempt < self.settings.retries:
                        time.sleep(0.25 * (2 ** attempt)); continue
                    if response.status_code == 401: raise ProviderError("Nebius authentication failed. Check NEBIUS_API_KEY.")
                    if response.status_code == 404: raise ProviderError("Nebius model or endpoint was not found. Check NEBIUS_MODEL and NEBIUS_BASE_URL.")
                    response.raise_for_status()
                    data = response.json(); choice = data["choices"][0]
                    return GenerationResponse(text=choice["message"]["content"], model=data.get("model", payload["model"]), provider=self.name, usage=data.get("usage"), finish_reason=choice.get("finish_reason"))
                except httpx.TimeoutException as exc:
                    if attempt >= self.settings.retries: raise ProviderError("Nebius request timed out.") from exc
                except httpx.RequestError as exc:
                    if attempt >= self.settings.retries: raise ProviderError("Unable to reach Nebius.") from exc
        except ProviderError: raise
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError("Nebius returned an invalid response.") from exc
        finally:
            if self.client is None: client.close()
        raise ProviderError("Nebius request failed.")
