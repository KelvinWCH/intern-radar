import re
import unicodedata


def loose_text(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", folded).split())


def quoted_in(quote: str, source: str) -> bool:
    needle = loose_text(quote)
    return bool(needle) and f" {needle} " in f" {loose_text(source)} "
