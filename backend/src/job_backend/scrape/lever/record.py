from pydantic import JsonValue

from job_backend.scrape.github.utils.dates import parse_posted_date


def page_record(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    fields = dict(record)
    categories = record.get("categories")
    if isinstance(categories, dict):
        primary = categories.get("location")
        all_locations = categories.get("allLocations")
        locations = (
            [
                location
                for location in all_locations
                if isinstance(location, str) and location.strip()
            ]
            if isinstance(all_locations, list)
            else []
        )
        if isinstance(primary, str) and primary.strip() and primary not in locations:
            locations.insert(0, primary)
        country = record.get("country")
        country_name = "Canada" if country == "CA" else "United States" if country == "US" else None
        if isinstance(primary, str) and country_name:
            locations = [
                f"{location}, {country_name}"
                if location == primary and country_name.casefold() not in location.casefold()
                else location
                for location in locations
            ]
        if locations:
            fields["locations"] = list(dict.fromkeys(locations))
    published = parse_posted_date(record.get("createdAt"))
    if published is not None:
        fields["date_posted"] = published
    return fields
