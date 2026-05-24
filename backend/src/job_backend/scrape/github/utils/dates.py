import re
import time
from datetime import UTC, datetime
from html import unescape


def parse_posted_date(value: object, *, now: int | None = None) -> int | None:
    reference = int(time.time()) if now is None else now
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        # some lists use unix milliseconds instead of seconds
        timestamp = value // 1000 if value >= 1_000_000_000_000 else value
        return timestamp if 0 <= timestamp <= reference else None
    if not isinstance(value, str):
        return None
    text = unescape(re.sub(r"<[^>]+>", " ", value)).strip().strip("*~`")
    if not text or text == "-":
        return None
    if re.fullmatch(r"\d{10}|\d{13}", text):
        return parse_posted_date(int(text), now=reference)
    if "first seen" in text.casefold():
        if not text.casefold().startswith("posted "):
            return None
        text = re.split(r"first seen", text, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    text = re.sub(r"^posted\s+", "", text, flags=re.IGNORECASE).strip()
    relative = re.fullmatch(
        r"(\d+)\s*(h|hr|hrs|hour|hours|d|day|days|w|week|weeks)(?:\s+(?:ago|old))?",
        text,
        flags=re.IGNORECASE,
    )
    if relative:
        unit = relative.group(2).lower()[0]
        seconds = {"h": 3600, "d": 86400, "w": 604800}[unit]
        precision = 3600 if unit == "h" else 86400
        timestamp = reference - (reference % precision) - int(relative.group(1)) * seconds
        return timestamp if timestamp >= 0 else None
    if text.casefold() in {"today", "just now", "new"}:
        return (
            (reference - reference % (3600 if text.casefold() == "just now" else 86400))
            if text.casefold() != "new"
            else None
        )
    if text.casefold() == "yesterday":
        return reference - reference % 86400 - 86400
    # an age shown after a real date is just extra info
    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:$|[T\s])", text)
    if match:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.fromisoformat(match.group(1))
            except ValueError:
                return None
        parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
        timestamp = int(parsed.timestamp())
        return timestamp if 0 <= timestamp <= reference else None
    month_date = re.match(r"^([A-Za-z]+\s+\d{1,2}(?:,?\s+\d{4})?)\b", text)
    if month_date is None:
        return None
    date_text = month_date.group(1).replace(",", "")
    current = datetime.fromtimestamp(reference, UTC)
    has_year = bool(re.search(r"\b\d{4}$", date_text))
    for pattern in ("%b %d %Y", "%B %d %Y"):
        try:
            parsed = datetime.strptime(
                date_text if has_year else f"{date_text} {current.year}", pattern
            ).replace(tzinfo=UTC)
        except ValueError:
            continue
        if parsed > current and not has_year:
            try:
                parsed = parsed.replace(year=current.year - 1)
            except ValueError:
                return None
        timestamp = int(parsed.timestamp())
        return timestamp if 0 <= timestamp <= reference else None
    return None
