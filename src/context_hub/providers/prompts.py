import json

SYSTEM_PROMPT = """You are the reasoning engine of Context Hub. Analyze developer tasks using only the supplied repository metadata. Do not invent repository facts. Distinguish explicit information, inference, and context that requires further retrieval. Return only valid JSON matching the requested schema."""


def analysis_prompt(task: str, results: list[object], max_chars: int, *, compact: bool = False) -> str:
    records = [r.model_dump() for r in results]
    if compact:
        records = [{key: record.get(key) for key in ("path", "symbol", "score", "signals", "reasons")} for record in records]
    context = json.dumps(records, sort_keys=True)
    instruction = " Keep the arrays concise and the reasoning under 100 words." if compact else ""
    return (f"Developer task: {task}\n\nBounded repository retrieval metadata:\n{context[:max_chars]}\n\nReturn JSON with fields: task_type, domains, keywords, likely_files, likely_symbols, required_context, ambiguities, constraints, confidence, reasoning. Do not include a task field.{instruction}")
