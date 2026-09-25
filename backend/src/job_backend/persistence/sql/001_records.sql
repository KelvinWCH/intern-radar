-- one jsonb table for every record type, only lookup fields get indexed
CREATE TABLE job_records (
    collection text COLLATE "C" NOT NULL,
    key text COLLATE "C" NOT NULL,
    data jsonb NOT NULL CHECK (jsonb_typeof(data) = 'object'),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (collection, key)
);

CREATE INDEX job_records_id ON job_records (collection, (data -> 'id'))
    WHERE data -> 'id' IS NOT NULL;
CREATE INDEX job_records_job_id ON job_records (collection, (data -> 'job_id'))
    WHERE data -> 'job_id' IS NOT NULL;
CREATE INDEX job_records_task_id ON job_records (collection, (data -> 'task_id'))
    WHERE data -> 'task_id' IS NOT NULL;
CREATE INDEX job_records_status ON job_records (collection, (data -> 'status'))
    WHERE data -> 'status' IS NOT NULL;
CREATE INDEX job_records_source ON job_records (collection, (data -> 'source'))
    WHERE data -> 'source' IS NOT NULL;
CREATE INDEX job_records_job_url_hash ON job_records (collection, (data -> 'job_url_hash'))
    WHERE data -> 'job_url_hash' IS NOT NULL;
CREATE INDEX job_records_extraction_fingerprint
    ON job_records (collection, (data -> 'extraction_fingerprint'))
    WHERE data -> 'extraction_fingerprint' IS NOT NULL;
CREATE INDEX job_records_deduplication_key ON job_records (collection, (data -> 'deduplication_key'))
    WHERE data -> 'deduplication_key' IS NOT NULL;

-- these have to match the query expressions exactly to use the index
CREATE INDEX job_records_created_at ON job_records (
    collection,
    (CASE WHEN jsonb_typeof(data -> 'created_at') = 'number'
        THEN (data ->> 'created_at')::numeric END) DESC,
    key DESC
) WHERE jsonb_typeof(data -> 'created_at') = 'number';
CREATE INDEX job_records_started_at ON job_records (
    collection,
    (CASE WHEN jsonb_typeof(data -> 'started_at') = 'number'
        THEN (data ->> 'started_at')::numeric END) DESC,
    key DESC
) WHERE jsonb_typeof(data -> 'started_at') = 'number';
CREATE INDEX job_records_finished_at ON job_records (
    collection,
    (CASE WHEN jsonb_typeof(data -> 'finished_at') = 'number'
        THEN (data ->> 'finished_at')::numeric END) DESC,
    key DESC
) WHERE jsonb_typeof(data -> 'finished_at') = 'number';
CREATE INDEX job_records_first_seen_at ON job_records (
    collection,
    (CASE WHEN jsonb_typeof(data -> 'first_seen_at') = 'number'
        THEN (data ->> 'first_seen_at')::numeric END) DESC,
    key DESC
) WHERE jsonb_typeof(data -> 'first_seen_at') = 'number';
CREATE INDEX job_records_occurred_at ON job_records (
    collection,
    (CASE WHEN jsonb_typeof(data -> 'occurred_at') = 'number'
        THEN (data ->> 'occurred_at')::numeric END) DESC,
    key DESC
) WHERE jsonb_typeof(data -> 'occurred_at') = 'number';

CREATE INDEX job_records_task_events ON job_records (
    collection, (data -> 'task_id'),
    (CASE WHEN jsonb_typeof(data -> 'created_at') = 'number'
        THEN (data ->> 'created_at')::numeric END) DESC,
    key DESC
) WHERE jsonb_typeof(data -> 'created_at') = 'number' AND data -> 'task_id' IS NOT NULL;
CREATE INDEX job_records_run_events ON job_records (
    collection, (data -> 'run_id'),
    (CASE WHEN jsonb_typeof(data -> 'created_at') = 'number'
        THEN (data ->> 'created_at')::numeric END) DESC,
    key DESC
) WHERE jsonb_typeof(data -> 'created_at') = 'number' AND data -> 'run_id' IS NOT NULL;
