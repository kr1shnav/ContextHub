from __future__ import annotations

import json
import re
from pathlib import Path
from pydantic import ValidationError
from .providers import LLMProvider, ProviderError, TaskAnalysis
from .providers.config import ProviderSettings
from .providers.models import GenerationRequest
from .providers.prompts import SYSTEM_PROMPT, analysis_prompt
from .retrieval import RetrievalEngine, RetrievalQuery


def analyze_task(task: str, provider: LLMProvider, root: Path, settings: ProviderSettings | None = None, limit: int = 10, *, compact_prompt: bool = False) -> TaskAnalysis:
    settings = settings or ProviderSettings.from_env()
    database = root / ".context-hub" / "index.db"
    results = RetrievalEngine(database).search(RetrievalQuery(task=task, max_results=limit)) if database.is_file() else []
    user_prompt = analysis_prompt(task, results, settings.max_context_chars, compact=compact_prompt)
    request = GenerationRequest(system=SYSTEM_PROMPT, user=user_prompt, model=settings.model, temperature=settings.temperature, max_tokens=settings.max_tokens)
    last_error: Exception | None = None
    for attempt in range(2):
        if attempt:
            request = request.model_copy(update={"system": SYSTEM_PROMPT + " Return exactly one complete JSON object. Do not use Markdown fences or explanatory text."})
        try:
            response = provider.generate(request)
            data = _parse_task_analysis_json(response.text)
            _normalize_optional_fields(data)
            data["task"] = task
            return TaskAnalysis.model_validate(data)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            last_error = exc
    if isinstance(last_error, ValidationError):
        fields = ", ".join(".".join(str(part) for part in error["loc"]) for error in last_error.errors())
        raise ProviderError(f"The model returned malformed task analysis JSON (invalid fields: {fields}).") from last_error
    raise ProviderError("The model returned malformed task analysis JSON.") from last_error


def _normalize_optional_fields(data: dict[str, object]) -> None:
    """Accept null for optional list fields without inventing missing required data."""
    for field in ("domains", "keywords", "likely_files", "likely_symbols", "required_context", "ambiguities", "constraints"):
        if data.get(field) is None:
            data[field] = []


def _parse_task_analysis_json(text: str) -> dict[str, object]:
    """Extract one complete JSON object while retaining strict schema validation."""
    candidate = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.IGNORECASE | re.DOTALL)
    if fence:
        candidate = fence.group(1)
    else:
        start = candidate.find("{")
        if start < 0:
            raise json.JSONDecodeError("No JSON object found", candidate, 0)
        depth = 0
        in_string = False
        escaped = False
        end = None
        for index in range(start, len(candidate)):
            char = candidate[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            raise json.JSONDecodeError("Incomplete JSON object", candidate, start)
        candidate = candidate[start:end]
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise TypeError("Task analysis must be a JSON object")
    return data
