CREATE INDEX job_records_date_posted ON job_records (
    collection,
    (CASE WHEN jsonb_typeof(data -> 'date_posted') = 'number'
        THEN (data ->> 'date_posted')::numeric END) DESC,
    key DESC
) WHERE jsonb_typeof(data -> 'date_posted') = 'number';
