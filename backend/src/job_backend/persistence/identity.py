import hashlib
import json
import re


def document_id(values: tuple[str | int, ...]) -> str:
    if len(values) == 1 and re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", str(values[0])):
        return str(values[0])
    return "key-" + hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()
