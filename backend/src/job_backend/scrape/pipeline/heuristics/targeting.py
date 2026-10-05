from pydantic import JsonValue

from job_backend.common.text_matching import normalized_text
from job_backend.scrape.pipeline.heuristics.classification import (
    classify_locations,
    internship_title,
)
from job_backend.scrape.pipeline.heuristics.constants import (
    EMPLOYMENT_FIELDS,
    FOREIGN_LOCATION,
    LOCATION_FIELDS,
    NON_STUDENT_TITLE,
    TITLE_FIELDS,
)


def _labels(value: JsonValue) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [label for item in value for label in _labels(item)]
    if isinstance(value, dict):
        return [
            label
            for key in (
                "name",
                "descriptor",
                "label",
                "location",
                "address",
                "postalAddress",
                "addressLocality",
                "addressRegion",
                "addressCountry",
                "nameCode",
                "shortName",
            )
            for label in _labels(value.get(key))
        ]
    return []


def listing_is_candidate(record: dict[str, JsonValue], *, complete: bool = False) -> bool:
    title = next(
        (
            value.strip()
            for key in TITLE_FIELDS
            if isinstance(value := record.get(key), str) and value.strip()
        ),
        None,
    )
    categories = record.get("categories")
    if title is None and not complete:
        listing_text = record.get("listing_text")
        if isinstance(listing_text, str) and listing_text.strip():
            title = listing_text
    category_fields = categories if isinstance(categories, dict) else {}
    employment = [
        label
        for fields in (record, category_fields)
        for key in EMPLOYMENT_FIELDS
        for label in _labels(fields.get(key))
    ]
    student_role = (
        (title is not None and internship_title(title))
        or any(internship_title(label) for label in employment)
        or record.get("is_intern") in (True, 1, "1")
    )
    if (
        title
        and not student_role
        and (complete or NON_STUDENT_TITLE.search(normalized_text(title)))
    ):
        return False
    locations = [
        label
        for fields in (record, category_fields)
        for key in LOCATION_FIELDS
        for label in _labels(fields.get(key))
    ]
    if not locations or classify_locations(locations)[0]:
        return True
    return not all(FOREIGN_LOCATION.search(location) for location in locations)
