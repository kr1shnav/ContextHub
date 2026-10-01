import json

SYSTEM_PROMPT = """You are the reasoning engine of Context Hub. Analyze developer tasks using only the supplied repository metadata. Do not invent repository facts. Distinguish explicit information, inference, and context that requires further retrieval. Return only valid JSON matching the requested schema."""


def analysis_prompt(task: str, results: list[object], max_chars: int) -> str:
    context = json.dumps([r.model_dump() for r in results], sort_keys=True)
    return (f"Developer task: {task}\n\nBounded repository retrieval metadata:\n{context[:max_chars]}\n\nReturn JSON with fields: task_type, domains, keywords, likely_files, likely_symbols, required_context, ambiguities, constraints, confidence, reasoning. Do not include a task field.")
