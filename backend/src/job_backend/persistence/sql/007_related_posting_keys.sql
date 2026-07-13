-- keys for grouping copies of the same posting from different boards
CREATE OR REPLACE FUNCTION job_read_projection(collection text, source jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $fn$
    SELECT COALESCE(jsonb_object_agg(key,
        CASE WHEN key = 'summary' AND jsonb_typeof(value) = 'string'
            THEN to_jsonb(left(source ->> key, 800)) ELSE value END), '{}'::jsonb)
    FROM jsonb_each(source)
    WHERE key IN (SELECT jsonb_array_elements_text(('{"jobs": ["id", "details_version", "details_updated_at", "deleted_at", "source", "source_type", "review_reason", "external_id", "source_job_id", "company", "title", "application_url", "apply_url", "company_url", "locations", "category", "terms", "sponsorship", "upstream_source", "active", "is_visible", "date_posted", "date_updated", "summary", "source_url", "is_canada_internship", "is_toronto_area", "job_hash", "content_hash", "first_seen_at", "last_seen_at", "last_changed_at", "deduplication_key", "job_url_hash"], "job_user_data": ["job_id", "status", "notes", "applied_at", "follow_up_at", "updated_at", "version"], "job_documents": ["id", "job_id", "company", "title", "status", "created_at", "finished_at", "has_resume", "has_cover_letter", "error", "ai_usage"], "import_runs": ["id", "source", "trigger", "status", "started_at", "finished_at", "fetched", "matched", "created", "updated", "unchanged", "error", "task_id", "phase", "items_done", "items_total", "input_tokens", "output_tokens", "cost_usd"], "activity_events": ["id", "kind", "occurred_at"]}'::jsonb) -> collection))
$fn$;

UPDATE job_record_reads r
SET data = job_read_projection('jobs', s.data), revision = DEFAULT
FROM job_records s
WHERE r.collection = 'jobs' AND s.collection = 'jobs' AND s.key = r.key;

CREATE INDEX job_reads_deduplication_key ON job_record_reads(collection, (data -> 'deduplication_key'));
