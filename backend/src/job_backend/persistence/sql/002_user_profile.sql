-- move the old resume record over to user_profile, keep the old one as a backup
INSERT INTO job_records (collection, key, data, updated_at)
SELECT 'user_profile', key, data, updated_at FROM job_records WHERE collection = 'user_resume'
ON CONFLICT (collection, key) DO NOTHING;
