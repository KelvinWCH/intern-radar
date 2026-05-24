from typing import TypeVar

from job_backend.jobs.models import DocumentDetail, DocumentSummary, JobDocument
from job_backend.persistence.models import Filter, Junction, Order, ReadQuery
from job_backend.persistence.session import Session

DocumentResponse = TypeVar("DocumentResponse", bound=DocumentSummary)


def document_response(
    session: Session, row: JobDocument, model: type[DocumentResponse]
) -> DocumentResponse:
    response = model.model_validate(row)
    if isinstance(response, DocumentDetail):
        response.mode = (
            "one_shot" if (row.request_snapshot or {}).get("mode") == "one_shot" else "staged"
        )
        response.reports = []
        response.profile_snapshot = None
    dates = session.select(
        ReadQuery("jobs", Filter("id", value=row.job_id), fields=("date_posted",)),
        limit=1,
        count=False,
    ).items
    posted = dates[0].get("date_posted") if dates else None
    response.date_posted = posted if isinstance(posted, int) else None
    return response


def document_summaries(session: Session, job_ids: set[str]) -> dict[str, list[DocumentSummary]]:
    rows: dict[str, DocumentSummary] = {}
    position = 0
    query = ReadQuery(
        "job_documents",
        Junction(tuple(Filter("job_id", value=identity) for identity in sorted(job_ids)), "or"),
        (Order("created_at", descending=True, numeric=True), Order("@key", descending=True)),
    )
    if job_ids:
        while True:
            page = session.select(query, limit=1000, offset=position, count=False).items
            rows.update((str(row["id"]), DocumentSummary.model_validate(row)) for row in page)
            if len(page) < 1000:
                break
            position += len(page)
    for key, record in session.records.items():
        if isinstance(record, JobDocument) and record.job_id in job_ids:
            if key in session.deleted:
                rows.pop(record.id, None)
            else:
                rows[record.id] = DocumentSummary.model_validate(record)
    grouped: dict[str, list[DocumentSummary]] = {}
    for summary in sorted(rows.values(), key=lambda row: (row.created_at, row.id), reverse=True):
        grouped.setdefault(summary.job_id, []).append(summary)
    return grouped
