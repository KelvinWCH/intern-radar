from pydantic import JsonValue


def _text(value: JsonValue) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def page_record(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    detail = record.get("detail")
    detail = detail if isinstance(detail, dict) else {}
    listing = record.get("listing")
    listing = listing if isinstance(listing, dict) else {}
    fields: dict[str, JsonValue] = {**listing, **detail}
    sections_value = detail.get("jobAd")
    sections = sections_value.get("sections") if isinstance(sections_value, dict) else None
    parts: list[str] = []
    if isinstance(sections, dict):
        for section in sections.values():
            if isinstance(section, dict):
                title = _text(section.get("title"))
                body = _text(section.get("text"))
                if body:
                    parts.append(f"<h3>{title}</h3>\n{body}" if title else body)
    if parts:
        fields["description"] = "\n".join(parts)
    fields["title"] = _text(detail.get("name")) or _text(listing.get("name"))
    location = detail.get("location") if "location" in detail else listing.get("location")
    if isinstance(location, dict):
        place = ", ".join(
            part
            for part in (
                _text(location.get("city")),
                _text(location.get("region")),
                _text(location.get("country")),
            )
            if part
        )
        fields["locations"] = [place] if place else []
        if location.get("remote") is True:
            fields["remote"] = True
    for source, target in (
        ("typeOfEmployment", "employmentType"),
        ("releasedDate", "datePosted"),
        ("refNumber", "requisition_id"),
    ):
        value = fields.get(source)
        if isinstance(value, dict):
            value = value.get("label")
        if isinstance(value, str) and value.strip():
            fields[target] = value
    return fields
