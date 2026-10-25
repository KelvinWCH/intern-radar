from pydantic import JsonValue

from job_backend.scrape.pipeline.heuristics.classification import internship_title


def _text(value: JsonValue) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _places(listing: dict[str, JsonValue], detail: dict[str, JsonValue]) -> list[JsonValue]:
    places: list[JsonValue] = []
    work = detail.get("workLocation")
    if isinstance(work, list):
        for location in work:
            if isinstance(location, dict):
                country = _text(location.get("Country"))
                parts = [
                    _text(location.get("TownOrCity")),
                    _text(location.get("Region2")),
                    _text(location.get("Region1")),
                    "Canada" if country == "CA" else country,
                ]
                place = ", ".join(dict.fromkeys(part for part in parts if part))
                if place:
                    places.append(place)
    for record in (detail, listing):
        primary = _text(record.get("PrimaryLocation"))
        if primary:
            places.append(primary)
        secondary = record.get("secondaryLocations")
        if isinstance(secondary, list):
            places.extend(
                name
                for item in secondary
                if isinstance(item, dict) and (name := _text(item.get("Name")))
            )
    return list(dict.fromkeys(place for place in places if isinstance(place, str)))


def page_record(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    detail = record.get("detail")
    listing = record.get("listing")
    detail = detail if isinstance(detail, dict) else {}
    listing = listing if isinstance(listing, dict) else {}
    fields: dict[str, JsonValue] = {**listing, **detail}
    fields["title"] = _text(detail.get("Title")) or _text(listing.get("Title"))
    fields["locations"] = _places(listing, detail)
    fields["date_posted"] = detail.get("ExternalPostedStartDate") or listing.get("PostedDate")
    fields["requisition_id"] = _text(detail.get("Id")) or _text(listing.get("Id"))
    fields["description"] = "\n".join(
        text
        for key in (
            "ExternalDescriptionStr",
            "ExternalResponsibilitiesStr",
            "ExternalQualificationsStr",
        )
        if (text := _text(detail.get(key)))
    ) or _text(detail.get("ShortDescriptionStr"))
    labels: list[str] = [
        label
        for key in ("JobType", "RequisitionType", "JobFunction", "WorkerType")
        if (label := _text(detail.get(key)))
    ]
    flex = detail.get("requisitionFlexFields")
    if isinstance(flex, list):
        labels.extend(
            value
            for item in flex
            if isinstance(item, dict)
            and "level" in str(item.get("Prompt")).casefold()
            and (value := _text(item.get("Value")))
        )
    if any(internship_title(label) for label in labels):
        fields["employmentType"] = "internship"
    elif labels:
        fields["employmentType"] = labels[0]
    return fields
