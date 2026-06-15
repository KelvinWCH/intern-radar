import re
import unicodedata
from difflib import SequenceMatcher


def normalized_text(value: str) -> str:
    ascii_text = "".join(
        char
        for char in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^\w]+", " ", ascii_text).split())


def close_spelling(value: str, candidate: str) -> bool:
    if value == candidate:
        return True
    if min(len(value), len(candidate)) < 5 or abs(len(value) - len(candidate)) > 2:
        return False
    if value[:1] != candidate[:1]:
        return False
    return SequenceMatcher(None, value, candidate, autojunk=False).ratio() >= 0.88


def matches_text(query: str, value: str) -> bool:
    original_query, original_value = query.strip().casefold(), value.casefold()
    query, value = normalized_text(query), normalized_text(value)
    if not query:
        return original_query in original_value
    if query in value and (len(query) > 3 or query in value.split()):
        return True
    tokens = value.split()
    return all(any(close_spelling(word, token) for token in tokens) for word in query.split())


def contains_text(query: str, value: str) -> bool:
    needle = normalized_text(query)
    return (
        needle in normalized_text(value) if needle else query.strip().casefold() in value.casefold()
    )
