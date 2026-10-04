_PLACEHOLDERS = {"one", "multi", "multiple", "none", "null", "unknown", "n/a", "na", "tbd"}


def employer_job_id(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value if value and value.casefold() not in _PLACEHOLDERS else None
