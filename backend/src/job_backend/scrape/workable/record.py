from pydantic import JsonValue


def _location_text(location: dict[str, JsonValue]) -> str:
    country = location.get("country") or location.get("countryCode")
    if isinstance(country, str) and country in {"CA", "CAN"}:
        country = "Canada"
    elif isinstance(country, str) and country in {"US", "USA"}:
        country = "United States"
    parts = [location.get("city"), location.get("region") or location.get("state"), country]
    return ", ".join(
        dict.fromkeys(part.strip() for part in parts if isinstance(part, str) and part.strip())
    )


def page_record(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    fields = dict(record)
    locations: list[JsonValue] = []
    reported_locations = record.get("locations")
    if isinstance(reported_locations, list):
        for location in reported_locations:
            if isinstance(location, dict) and (label := _location_text(location)):
                locations.append(label)
    if not locations and (label := _location_text(record)):
        locations.append(label)
    fields["locations"] = locations
    fields["requisition_id"] = record.get("code") or record.get("shortcode")
    fields["date_posted"] = record.get("published_on")
    return fields
