from job_backend.common.text_matching import normalized_text
from job_backend.jobs.employer_ids import employer_job_id
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.github.utils.dates import parse_posted_date
from job_backend.scrape.pipeline.heuristics.classification import (
    classify_locations,
    internship_title,
    role_category,
)
from job_backend.scrape.pipeline.heuristics.constants import INTERNSHIP_EMPLOYMENT_TYPES
from job_backend.scrape.pipeline.heuristics.parsing import (
    location_values,
    object_value,
    read_record,
    record_posted_date,
    text_value,
)
from job_backend.scrape.pipeline.models import (
    EducationRequirements,
    ExtractedJob,
    ExtractionResult,
    Qualifications,
    RawDocument,
)


class HeuristicNormalizer:
    cache_key = "heuristics-v11-employer-identities"
    max_calls_per_scrape = 2**31 - 1

    def extract(self, document: RawDocument) -> ExtractionResult:
        envelope = read_record(document)
        row = object_value(envelope.get("job")) or envelope
        hints = document.listing_data
        categories = object_value(row.get("categories"))
        title = (
            text_value(row.get("title"))
            or text_value(row.get("text"))
            or text_value(hints.get("title"))
        )
        company = (
            text_value(envelope.get("company_name"))
            or text_value(row.get("company_name"))
            or text_value(row.get("company"))
            or text_value(object_value(row.get("hiringOrganization")).get("name"))
            or text_value(hints.get("company_name"))
            or text_value(hints.get("company"))
        )
        locations = location_values(
            row.get("locations")
            or row.get("location")
            or categories.get("location")
            or row.get("jobLocation"),
            postal_address=object_value(row.get("address")).get("postalAddress"),
        )
        locations += location_values(row.get("secondaryLocations"))
        locations += location_values(row.get("applicantLocationRequirements"))
        if not locations:
            locations = location_values(hints.get("locations") or hints.get("location"))
        if not title or not company:
            raise SourceDataError("Basic job facts unavailable; use AI enrichment for this source")
        canada, toronto = classify_locations(locations)
        employment_type = row.get("employmentType") or row.get("employment_type")
        employment_types = (
            employment_type if isinstance(employment_type, list) else [employment_type]
        )
        internship = internship_title(title) or any(
            isinstance(value, str) and normalized_text(value) in INTERNSHIP_EMPLOYMENT_TYPES
            for value in employment_types
        )
        education = EducationRequirements(
            degree_levels=[],
            fields_of_study=[],
            year_of_study_required=None,
            eligible_years_of_study=[],
            graduation_years=[],
            currently_enrolled=None,
            must_return_to_study=None,
            minimum_gpa=None,
            gpa_scale=None,
        )
        qualifications = Qualifications(
            education=education,
            required_skills=[],
            preferred_skills=[],
            tech_stack=[],
            minimum_experience_years=None,
            experience_requirements=[],
            certifications=[],
            languages=[],
            work_authorization=None,
            visa_sponsorship_available=None,
            security_clearance=None,
            other_requirements=[],
        )
        terms = row.get("terms", hints.get("terms"))
        active = row.get("active", hints.get("active"))
        visible = row.get("is_visible", hints.get("is_visible"))
        identifiers = (
            (row.get("requisition_id"), row.get("id"))
            if "job" in envelope
            else (object_value(row.get("identifier")).get("value"), row.get("identifier"))
        )
        source_job_id = next(
            (
                valid
                for identifier in (*identifiers, hints.get("source_job_id"))
                if isinstance(identifier, str | int) and not isinstance(identifier, bool)
                if (valid := employer_job_id(str(identifier))) is not None
            ),
            None,
        )
        return ExtractionResult(
            jobs=[
                ExtractedJob(
                    is_canada_internship=canada and internship,
                    is_toronto_area=toronto,
                    company=company,
                    title=title,
                    locations=locations,
                    application_url=document.application_url
                    or text_value(row.get("url"))
                    or document.source_url,
                    apply_url=document.apply_url or text_value(row.get("apply_url")),
                    company_url=None,
                    source_job_id=source_job_id,
                    category=text_value(row.get("category"))
                    or text_value(hints.get("category"))
                    or role_category(title),
                    terms=[term for term in terms if isinstance(term, str)]
                    if isinstance(terms, list)
                    else [],
                    qualifications=qualifications,
                    sponsorship=None,
                    upstream_source=None,
                    active=active if isinstance(active, bool) else None,
                    is_visible=visible if isinstance(visible, bool) else None,
                    date_posted=document.date_posted
                    if document.date_posted is not None
                    else record_posted_date(row),
                    date_updated=parse_posted_date(
                        row.get("date_updated") or row.get("updated_at")
                    ),
                    summary=None,
                )
            ]
        )
