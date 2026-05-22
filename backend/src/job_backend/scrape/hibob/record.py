from pydantic import JsonValue


def page_record(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    fields = dict(record)
    parts = [record.get("site"), record.get("country")]
    location = ", ".join(
        dict.fromkeys(part.strip() for part in parts if isinstance(part, str) and part.strip())
    )
    fields["locations"] = [location] if location else []
    fields["requisition_id"] = record.get("id")
    return fields
