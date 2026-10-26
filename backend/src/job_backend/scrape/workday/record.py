from pydantic import JsonValue

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.utils.page_text import page_text
from job_backend.scrape.workday.constants import LEGAL_EMPLOYER, REMOTE_ELIGIBILITY


def _roche_remote_location(
    record: dict[str, JsonValue], detail: dict[str, JsonValue], posting: dict[str, JsonValue]
) -> str | None:
    organization = detail.get("hiringOrganization")
    if not isinstance(organization, dict) or organization.get("name") != LEGAL_EMPLOYER:
        return None
    listing = record.get("listing")
    if isinstance(listing, dict):
        for key in ("location", "locationsText", "additionalLocations", "country"):
            if listing.get(key):
                return None
    if posting.get("country"):
        return None
    description = posting.get("jobDescription")
    if not isinstance(description, str):
        return None
    try:
        text = " ".join(page_text(description, include_structured=False).split())
    except SourceDataError:
        return None
    matched = REMOTE_ELIGIBILITY.search(text)
    return f"Remote, {matched.group('country')}" if matched else None


def page_record(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    detail = record.get("detail", record)
    posting = detail.get("jobPostingInfo") if isinstance(detail, dict) else None
    if not isinstance(detail, dict) or not isinstance(posting, dict):
        return record
    fields = dict(posting)
    locations: list[JsonValue] = []
    location = posting.get("location")
    country = posting.get("country")
    country_name = country.get("descriptor") if isinstance(country, dict) else None
    if isinstance(location, str) and location.strip():
        if isinstance(country_name, str) and country_name.strip() and country_name not in location:
            location = f"{location}, {country_name}"
        locations.append(location)
    additional_locations = posting.get("additionalLocations")
    if isinstance(additional_locations, list):
        locations.extend(location for location in additional_locations if isinstance(location, str))
    if not locations and (remote := _roche_remote_location(record, detail, posting)):
        locations.append(remote)
    fields["locations"] = locations
    fields["requisition_id"] = posting.get("jobReqId")
    student_facet = record.get("student_facet")
    if isinstance(student_facet, str) and student_facet:
        fields["student_facet"] = student_facet
        fields["employmentType"] = "internship"
    fields["date_posted"] = posting.get("startDate") or posting.get("postedOn")
    fields["active"] = posting.get("posted")
    fields["url"] = posting.get("externalUrl")
    return fields
