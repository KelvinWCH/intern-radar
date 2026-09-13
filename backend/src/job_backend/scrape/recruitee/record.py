from datetime import datetime

from pydantic import JsonValue


def _text(value: JsonValue) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _published(value: JsonValue) -> str | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S UTC").isoformat() + "Z"
    except ValueError:
        return None


def page_record(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    fields: dict[str, JsonValue] = dict(record)
    sections = [text for key in ("description", "requirements") if (text := _text(record.get(key)))]
    if sections:
        fields["description"] = "\n".join(sections)
    places: list[JsonValue] = []
    locations = record.get("locations")
    for location in locations if isinstance(locations, list) else []:
        if isinstance(location, dict):
            parts = [
                part for key in ("city", "state", "country") if (part := _text(location.get(key)))
            ]
            label = ", ".join(dict.fromkeys(parts)) or _text(location.get("name"))
            if label:
                places.append(label)
    if not places and (location := _text(record.get("location"))):
        places.append(location)
    fields["locations"] = places
    if record.get("remote") is True:
        fields["remote"] = True
    employment = _text(record.get("employment_type_code"))
    if employment:
        fields["employmentType"] = employment.replace("_", " ")
    published = _published(record.get("published_at"))
    if published:
        fields["datePosted"] = published
    fields.pop("location", None)
    return fields
