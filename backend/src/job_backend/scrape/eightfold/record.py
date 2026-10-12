from pydantic import JsonValue


def page_record(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    detail = record.get("detail")
    posting = detail.get("data") if isinstance(detail, dict) else None
    if not isinstance(posting, dict):
        return record
    fields = dict(posting)
    fields["title"] = posting.get("name")
    identifier = posting.get("atsJobId") or posting.get("displayJobId") or posting.get("id")
    fields["requisition_id"] = (
        str(identifier)
        if isinstance(identifier, (str, int)) and not isinstance(identifier, bool)
        else None
    )
    fields["date_posted"] = posting.get("postedTs")
    fields["locations"] = posting.get("locations") or posting.get("location")
    fields["employmentType"] = posting.get("employmentType") or posting.get(
        "efcustomTextEmploymentType"
    )
    return fields
