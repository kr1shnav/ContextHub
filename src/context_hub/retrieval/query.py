import re

STOP_WORDS = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "when", "with", "fix", "add"}


def tokenize(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    return [token.lower() for token in re.split(r"[^A-Za-z0-9]+", value) if token and token.lower() not in STOP_WORDS]


def normalize_query(value: str) -> list[str]:
    return list(dict.fromkeys(tokenize(value.strip())))

