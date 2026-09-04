-- index for the manual review queue
CREATE INDEX job_records_review_reason ON job_records (collection, (data -> 'review_reason'))
    WHERE data -> 'review_reason' IS NOT NULL;
