from pydantic import JsonValue

from job_backend.scrape.pipeline.heuristics.constants import LOCATION_FIELDS
from job_backend.scrape.pipeline.heuristics.parsing import (
    location_values,
    object_value,
    read_record,
)
from job_backend.scrape.pipeline.heuristics.targeting import listing_is_candidate
from job_backend.scrape.pipeline.models import RawDocument


def document_is_candidate(document: RawDocument) -> bool:
    try:
        envelope = read_record(document)
    except ValueError:
        return True
    row = object_value(envelope.get("job")) or envelope
    metadata: dict[str, JsonValue] = dict(document.listing_data)
    metadata.update({key: value for key, value in row.items() if value is not None})
    categories = object_value(metadata.get("categories"))
    locations = location_values(
        metadata.get("locations")
        or metadata.get("location")
        or categories.get("location")
        or metadata.get("jobLocation"),
        postal_address=object_value(metadata.get("address")).get("postalAddress"),
    )
    locations += location_values(metadata.get("secondaryLocations"))
    locations += location_values(metadata.get("applicantLocationRequirements"))
    for key in LOCATION_FIELDS:
        metadata.pop(key, None)
    metadata["locations"] = list(locations)
    return listing_is_candidate(metadata, complete=True)
