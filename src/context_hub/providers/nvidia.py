from __future__ import annotations

import json
import time

import httpx
import re

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
                    response = client.post(self._completion_url(), headers=headers, json=payload)
                    if response.status_code in (429, 500, 502, 503, 504) and attempt < self.settings.retries:
                        time.sleep(0.25 * (2 ** attempt))
                        continue
                    if response.status_code == 401:
                        raise ProviderError(self._error_message(response, "authentication failed. Check NVIDIA_API_KEY."))
                    if response.status_code == 403:
                        raise ProviderError(self._error_message(response, "access denied for this NVIDIA API Catalog account or model."))
                    if response.status_code == 404:
                        detail = self._safe_detail(response)
                        if "not found for account" in detail.lower():
                            raise ProviderError(
                                self._error_message(
                                    response,
                                    f"NVIDIA returned an account-scoped 404 for model '{payload['model']}'. "
                                    "This may indicate model availability, account entitlement, or an invalid "
                                    "endpoint/model combination. Verify NVIDIA_MODEL and NVIDIA_BASE_URL, "
                                    "and check the model is enabled for the account.",
                                )
                            )
                        raise ProviderError(self._error_message(response, f"model '{payload['model']}' or endpoint was not found at '{self._completion_url()}'. Check NVIDIA_MODEL and NVIDIA_BASE_URL. NVIDIA hosted model IDs must match the catalog exactly, including any provider namespace such as 'nvidia/'."))
                    if response.status_code == 429:
                        raise ProviderError(self._error_message(response, "rate limit or quota reached. Try again later."))
                    if 500 <= response.status_code <= 599:
                        if attempt >= self.settings.retries:
                            raise ProviderError(self._error_message(response, "NVIDIA API Catalog returned an upstream server error."))
                        continue
                    response.raise_for_status()
                    data = self._decode_success(response)
                    content, finish_reason = self._extract_content(data)
                    return GenerationResponse(text=content, model=data.get("model", payload["model"]), provider=self.name, usage=data.get("usage"), finish_reason=finish_reason)
                except httpx.TimeoutException as exc:
                    if attempt >= self.settings.retries:
                        raise ProviderError("NVIDIA request timed out.") from exc
                except httpx.RequestError as exc:
                    if attempt >= self.settings.retries:
                        raise ProviderError("Unable to reach NVIDIA API Catalog.") from exc
        except ProviderError:
            raise
        finally:
            if self.client is None:
                client.close()
        raise ProviderError("NVIDIA request failed.")

    @classmethod
    def _decode_success(cls, response: httpx.Response) -> dict[str, object]:
        """Decode an OpenAI-compatible success body with actionable diagnostics."""
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            content_type = response.headers.get("content-type", "unknown")
            raise ProviderError(
                f"NVIDIA returned invalid JSON for a successful response "
                f"(content-type: {content_type}). Check the configured endpoint '{response.url}'."
            ) from exc
        if not isinstance(data, dict):
            raise ProviderError(f"NVIDIA returned JSON of type {type(data).__name__}; expected an object with 'choices'.")
        return data

    @staticmethod
    def _extract_content(data: dict[str, object]) -> tuple[str, str | None]:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError("NVIDIA response is missing a non-empty 'choices' array.")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ProviderError("NVIDIA response 'choices[0]' is not an object.")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ProviderError("NVIDIA response is missing 'choices[0].message'.")
        finish_reason = choice.get("finish_reason")
        finish_reason = finish_reason if isinstance(finish_reason, str) else None
        if "content" not in message:
            raise NVIDIAProvider._content_diagnostic(message, finish_reason, "missing")
        content = message["content"]
        if isinstance(content, str):
            if content.strip():
                return content, finish_reason
        elif isinstance(content, list):
            text_parts: list[str] = []
            unsupported_parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                    text_parts.append(part["text"])
                elif isinstance(part, dict):
                    unsupported_parts.append(str(part.get("type", "unknown")))
                else:
                    unsupported_parts.append(type(part).__name__)
            combined = "".join(text_parts)
            if combined.strip() and not unsupported_parts:
                return combined, finish_reason
            if unsupported_parts:
                raise ProviderError(f"NVIDIA response contains unsupported message content parts: {', '.join(unsupported_parts[:5])}.")
        raise NVIDIAProvider._content_diagnostic(message, finish_reason, "empty or invalid")

    @staticmethod
    def _content_diagnostic(message: dict[str, object], finish_reason: str | None, state: str) -> ProviderError:
        if message.get("tool_calls"):
            return ProviderError("NVIDIA response contains tool_calls, but ContextHub does not support tool-call execution for task analysis.")
        if message.get("refusal"):
            return ProviderError("NVIDIA refused the task-analysis request; no user-facing analysis content was returned.")
        if message.get("reasoning_content"):
            return ProviderError("NVIDIA returned reasoning_content without user-facing content; ContextHub will not substitute private reasoning for the answer.")
        if finish_reason == "length":
            return ProviderError("NVIDIA returned no user-facing content because the response ended with finish_reason='length'; increase the output token limit or simplify the task.")
        return ProviderError(f"NVIDIA response 'choices[0].message.content' is {state}; finish_reason={finish_reason or 'unknown'}.")

    def _completion_url(self) -> str:
        """Return the OpenAI-compatible completion URL exactly once."""
        base = self.settings.base_url.rstrip("/")
        suffix = "/chat/completions"
        return base if base.endswith(suffix) else base + suffix

    @staticmethod
    def _error_message(response: httpx.Response, fallback: str) -> str:
        """Preserve status and a safe, bounded provider error without headers or credentials."""
        detail = NVIDIAProvider._safe_detail(response)
        suffix = f" {detail}" if detail else ""
        return f"NVIDIA HTTP {response.status_code}: {fallback}{suffix}"

    @staticmethod
    def _safe_detail(response: httpx.Response) -> str:
        """Extract bounded response detail without returning credentials."""
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
        detail = " ".join(detail.split())
        detail = re.sub(r"(?i)(\b(?:api[_-]?key|access[_-]?key|secret|password|token)\b\s*[:=]\s*)([^\s]+)", r"\1<redacted>", detail)
        detail = re.sub(r"(?i)(\bBearer\s+)[^\s]+", r"\1<redacted>", detail)
        detail = re.sub(r"(?i)(\baccount\b\s*)(['\"]?)[^\s,'\"]+\2", r"\1<redacted>", detail)
        detail = re.sub(r"(?i)(\bfunction\b\s*)(['\"])[^'\"]+\2", r"\1<redacted>", detail)
        return detail[:300]
