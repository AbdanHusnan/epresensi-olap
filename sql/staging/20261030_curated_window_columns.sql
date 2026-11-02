-- Add event snapshots before installing the revised curated batch function.
-- Existing rows remain NULL until their source events are reprocessed.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE curated.cur_event_attendance
  ADD COLUMN IF NOT EXISTS jam_masuk_awal_sumber time,
  ADD COLUMN IF NOT EXISTS jam_keluar_akhir_sumber time,
  ADD COLUMN IF NOT EXISTS shift_is_active_sumber boolean,
  ADD COLUMN IF NOT EXISTS checkin_window_status text,
  ADD COLUMN IF NOT EXISTS checkout_window_status text;
ALTER TABLE curated.cur_attendance_daily
  ADD COLUMN IF NOT EXISTS lateness_status text NOT NULL DEFAULT 'UNKNOWN',
  ADD COLUMN IF NOT EXISTS lateness_event_id integer,
  ADD COLUMN IF NOT EXISTS lateness_schedule_id integer,
  ADD COLUMN IF NOT EXISTS lateness_reason text;
COMMENT ON COLUMN curated.cur_event_attendance.jam_masuk_awal_sumber IS
  'Early check-in boundary copied from the source event; NULL means unavailable.';
COMMENT ON COLUMN curated.cur_event_attendance.jam_keluar_akhir_sumber IS
  'Last check-out boundary copied from the source event; NULL means unavailable.';
COMMIT;
