-- Existing facts are unknown until refreshed from curated evidence.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE mart_kehadiran.fact_kehadiran_daily
 ADD COLUMN IF NOT EXISTS lateness_status text NOT NULL DEFAULT 'UNKNOWN',
 ADD COLUMN IF NOT EXISTS lateness_event_id integer,
 ADD COLUMN IF NOT EXISTS lateness_schedule_id integer,
 ADD COLUMN IF NOT EXISTS lateness_reason text;
COMMIT;
