from __future__ import annotations

import json
from pathlib import Path
from pydantic import ValidationError
from .providers import LLMProvider, ProviderError, TaskAnalysis
from .providers.config import ProviderSettings
from .providers.models import GenerationRequest
from .providers.prompts import SYSTEM_PROMPT, analysis_prompt
from .retrieval import RetrievalEngine, RetrievalQuery


def analyze_task(task: str, provider: LLMProvider, root: Path, settings: ProviderSettings | None = None, limit: int = 10) -> TaskAnalysis:
    settings = settings or ProviderSettings.from_env()
    database = root / ".context-hub" / "index.db"
    results = RetrievalEngine(database).search(RetrievalQuery(task=task, max_results=limit)) if database.is_file() else []
    response = provider.generate(GenerationRequest(system=SYSTEM_PROMPT, user=analysis_prompt(task, results, settings.max_context_chars), model=settings.model, temperature=settings.temperature, max_tokens=settings.max_tokens))
    try:
        data = json.loads(response.text)
        data["task"] = task
        return TaskAnalysis.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise ProviderError("The model returned malformed task analysis JSON.") from exc
