import json

from pydantic import JsonValue, TypeAdapter

from job_backend.scrape.pipeline.models import (
    ExtractedJob,
    ExtractionResult,
    FetchResult,
    JobSource,
    Qualifications,
    RawDocument,
    ScrapedJob,
    ScrapeResult,
)


def listing(
    external_id: str = "example-1",
    *,
    active: bool = True,
    visible: bool = True,
    term: str = "Summer 2027",
    title: str = "Software Engineering Intern",
) -> dict[str, object]:
    return {
        "id": external_id,
        "company_name": "Example Company",
        "title": title,
        "url": "https://example.com/jobs/" + external_id,
        "company_url": "https://example.com",
        "locations": ["Toronto, ON, Canada"],
        "category": "Software Engineering",
        "terms": [term],
        "degrees": ["Bachelor's"],
        "sponsorship": "Other",
        "source": "Community",
        "active": active,
        "is_visible": visible,
        "date_posted": 1790000000,
        "date_updated": 1790000000,
    }


def payload(*rows: dict[str, object]) -> bytes:
    return json.dumps(rows).encode()


def qualifications(degree_levels: JsonValue = None) -> Qualifications:
    return Qualifications.model_validate(
        {
            "education": {
                "degree_levels": degree_levels if degree_levels is not None else [],
                "fields_of_study": [],
                "year_of_study_required": None,
                "eligible_years_of_study": [],
                "graduation_years": [],
                "currently_enrolled": None,
                "must_return_to_study": None,
                "minimum_gpa": None,
                "gpa_scale": None,
            },
            "required_skills": [],
            "preferred_skills": [],
            "tech_stack": [],
            "minimum_experience_years": None,
            "experience_requirements": [],
            "certifications": [],
            "languages": [],
            "work_authorization": None,
            "visa_sponsorship_available": None,
            "security_clearance": None,
            "other_requirements": [],
        }
    )


class StubNormalizer:
    def __init__(self, cache_key: str = "fictional-v1", limit: int = 100) -> None:
        self.cache_key = cache_key
        self.max_calls_per_scrape = limit
        self.calls = 0

    def extract(self, document: RawDocument) -> ExtractionResult:
        self.calls += 1
        row = TypeAdapter(dict[str, JsonValue]).validate_json(document.content)
        data = {
            key: value
            for key, value in row.items()
            if key not in {"id", "company_name", "url", "source"}
        }
        data.update(
            company=row["company_name"],
            application_url=row["url"],
            apply_url=row.get("apply_url"),
            upstream_source=row["source"],
            summary=row.get("summary"),
            qualifications=qualifications(row.get("degrees")).model_dump(mode="json"),
            source_job_id=row.get("source_job_id"),
            is_canada_internship=row.get("test_ai_canada_internship", True),
            is_toronto_area=row.get("test_ai_toronto_area", True),
        )
        fields = ExtractedJob.model_fields
        return ExtractionResult(
            jobs=[
                ExtractedJob.model_validate(
                    {key: value for key, value in data.items() if key in fields}
                )
            ]
        )


def normalized_listing() -> ScrapedJob:
    from job_backend.scrape.github.github_sources.simplify_internships import FEED_URL, SOURCE

    document = RawDocument(content=json.dumps(listing()), source_url=FEED_URL)
    extracted = StubNormalizer().extract(document).jobs[0]
    return ScrapedJob.model_validate(
        {
            **extracted.model_dump(),
            "source": SOURCE,
            "external_id": "example-1",
            "source_url": FEED_URL,
            "raw_payload": listing(),
        }
    )


def fixture_scrape(data: bytes) -> ScrapeResult:
    from job_backend.scrape.github.github_sources.simplify_internships import FEED_URL

    rows = TypeAdapter(list[dict[str, JsonValue]]).validate_json(data, strict=True)
    documents: list[RawDocument] = []
    for row in rows:
        terms = row.get("terms")
        if isinstance(terms, list) and "Summer 2027" not in terms:
            continue
        external_id = row.get("id")
        documents.append(
            RawDocument(
                content=json.dumps(row),
                source_url=FEED_URL,
                media_type="application/json",
                external_id=external_id if isinstance(external_id, str) else None,
            )
        )
    return ScrapeResult(fetched=len(rows), documents=documents)


ADAPTER = JobSource(
    name="simplify-summer2027",
    fetch=lambda _etag: FetchResult(None, None),
    scrape=fixture_scrape,
    terms=("Summer 2027",),
)
