-- Run once, only on staging_bkd. No source/raw mutations or data reload.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(hashtext('staging_bkd:curated_population_v2'));
DO $$
BEGIN
  IF current_database() <> 'staging_bkd' THEN
    RAISE EXCEPTION 'Expected staging_bkd, got %', current_database();
  END IF;
  IF to_regnamespace('curated_legacy_20261028') IS NOT NULL THEN
    RAISE EXCEPTION 'Archive already exists; migration must not be rerun';
  END IF;
  IF to_regclass('curated.cur_employee_workday') IS NULL THEN
    RAISE EXCEPTION 'Expected legacy curated structure';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_stat_activity
             WHERE datname=current_database() AND pid<>pg_backend_pid()
               AND state IS DISTINCT FROM 'idle') THEN
    RAISE EXCEPTION 'Another database session is active; inspect before migrating';
  END IF;
  IF EXISTS (SELECT 1 FROM etl_control.backfill_batch WHERE status='RUNNING') THEN
    RAISE EXCEPTION 'Legacy backfill marked RUNNING';
  END IF;
END $$;

-- Transactional rename retains old records and their OIDs without copying data.
ALTER SCHEMA curated RENAME TO curated_legacy_20261028;
COMMENT ON SCHEMA curated_legacy_20261028 IS
  'Legacy regular/workday design, archived 2026-10-28; not current KPI data.';
CREATE SCHEMA curated;
COMMENT ON SCHEMA curated IS
  'Population KPI v2: all active employees, all shifts, employee x reporting date. Empty pending date/population policy and ETL implementation.';

CREATE TABLE curated.cur_employee_population_daily (
  pegawai_id integer NOT NULL,
  tanggal date NOT NULL,
  departemen_id integer,
  status_sumber integer,
  is_employee_active boolean,
  population_basis text NOT NULL CHECK (population_basis IN
    ('AS_OF_DATE_SNAPSHOT','EXTRACTION_SNAPSHOT')),
  source_snapshot_at timestamptz NOT NULL,
  source_updated_at timestamp,
  perlu_review boolean NOT NULL DEFAULT false,
  alasan_review text,
  PRIMARY KEY (pegawai_id,tanggal)
);
CREATE INDEX population_date_department_idx
  ON curated.cur_employee_population_daily(tanggal,departemen_id);
COMMENT ON COLUMN curated.cur_employee_population_daily.population_basis IS
  'EXTRACTION_SNAPSHOT does not establish historical active status or department.';

CREATE TABLE curated.cur_event_attendance (
  checkinout_id_sumber integer PRIMARY KEY,
  pegawai_id integer,
  tanggal_event date,
  waktu_event timestamp,
  checktype integer,
  departemen_id_event integer,
  jadwal_id_sumber integer,
  work_code_sumber integer,
  jam_masuk_sumber time,
  jam_keluar_sumber time,
  is_manual boolean,
  is_wfh_sumber smallint,
  event_updated_at timestamp,
  shift_id_sumber integer,
  nama_shift_snapshot varchar(255),
  event_type text GENERATED ALWAYS AS
    (CASE checktype WHEN 1 THEN 'MASUK' WHEN 2 THEN 'PULANG' ELSE 'LAIN' END) STORED,
  is_valid_event_type boolean GENERATED ALWAYS AS
    (COALESCE(checktype IN (1,2),false)) STORED,
  tanggal date,
  date_assignment_status text NOT NULL DEFAULT 'UNRESOLVED'
    CHECK (date_assignment_status IN ('UNRESOLVED','PROVISIONAL','RESOLVED')),
  date_assignment_reason text NOT NULL,
  date_assignment_policy text,
  paired_checkin_id_sumber integer,
  perlu_review boolean NOT NULL DEFAULT false,
  alasan_review text,
  source_snapshot_at timestamptz NOT NULL,
  CHECK ((date_assignment_status='UNRESOLVED' AND tanggal IS NULL)
      OR (date_assignment_status IN ('PROVISIONAL','RESOLVED')
          AND tanggal IS NOT NULL AND pegawai_id IS NOT NULL
          AND date_assignment_policy IS NOT NULL))
);
CREATE INDEX event_reporting_date_employee_idx
  ON curated.cur_event_attendance(tanggal,pegawai_id);
CREATE INDEX event_calendar_date_idx
  ON curated.cur_event_attendance(tanggal_event);
CREATE INDEX event_employee_time_idx
  ON curated.cur_event_attendance(pegawai_id,waktu_event);
COMMENT ON TABLE curated.cur_event_attendance IS
  'All source events; no regular keyword filter. Calendar date is distinct from reporting date. Overnight assignment policy remains pending.';

CREATE TABLE curated.cur_attendance_event_daily (
  pegawai_id integer NOT NULL,
  tanggal date NOT NULL,
  checkin_event_count integer NOT NULL CHECK (checkin_event_count>=0),
  checkout_event_count integer NOT NULL CHECK (checkout_event_count>=0),
  has_masuk boolean GENERATED ALWAYS AS (checkin_event_count>0) STORED,
  has_pulang boolean GENERATED ALWAYS AS (checkout_event_count>0) STORED,
  first_checkin_at timestamp,
  last_checkout_at timestamp,
  has_manual_event boolean NOT NULL DEFAULT false,
  schedule_count integer NOT NULL CHECK (schedule_count>=0),
  shift_count integer NOT NULL CHECK (shift_count>=0),
  perlu_review boolean NOT NULL DEFAULT false,
  alasan_review text,
  is_date_final boolean NOT NULL DEFAULT false,
  date_assignment_policy text NOT NULL,
  source_snapshot_at timestamptz NOT NULL,
  PRIMARY KEY (pegawai_id,tanggal),
  CHECK ((checkin_event_count>0)=(first_checkin_at IS NOT NULL)),
  CHECK ((checkout_event_count>0)=(last_checkout_at IS NOT NULL)),
  CHECK (checkin_event_count+checkout_event_count>0)
);
CREATE INDEX event_daily_date_idx ON curated.cur_attendance_event_daily(tanggal);
COMMENT ON TABLE curated.cur_attendance_event_daily IS
  'One employee x reporting date, all shifts: MIN actual check-in and MAX actual check-out; not a session or duration calculation. Source lineage via event employee/reporting date.';

CREATE TABLE curated.cur_leave_daily (
  perizinan_id_sumber integer NOT NULL,
  pegawai_id integer NOT NULL,
  tanggal_izin date NOT NULL,
  departemen_id_izin integer,
  jenis_izin_id_sumber integer,
  nama_jenis_izin varchar(255),
  tipe_izin_id_sumber integer,
  nama_tipe_izin varchar(255),
  approval boolean,
  approval_at timestamp,
  is_full_day_leave boolean,
  is_partial_day_leave boolean,
  is_valid_leave boolean NOT NULL DEFAULT false,
  perlu_review boolean NOT NULL DEFAULT false,
  alasan_review text,
  source_updated_at timestamp,
  source_snapshot_at timestamptz NOT NULL,
  PRIMARY KEY (perizinan_id_sumber,pegawai_id,tanggal_izin),
  CHECK (NOT is_valid_leave OR approval IS TRUE),
  CHECK (NOT (is_full_day_leave IS TRUE AND is_partial_day_leave IS TRUE))
);
CREATE INDEX leave_date_employee_idx ON curated.cur_leave_daily(tanggal_izin,pegawai_id);

CREATE TABLE curated.cur_attendance_daily (
  pegawai_id integer NOT NULL,
  tanggal date NOT NULL,
  departemen_id integer,
  is_employee_active boolean,
  population_basis text CHECK (population_basis IN
    ('AS_OF_DATE_SNAPSHOT','EXTRACTION_SNAPSHOT')),
  has_masuk boolean GENERATED ALWAYS AS (checkin_event_count>0) STORED,
  has_pulang boolean GENERATED ALWAYS AS (checkout_event_count>0) STORED,
  checkin_event_count integer NOT NULL DEFAULT 0 CHECK (checkin_event_count>=0),
  checkout_event_count integer NOT NULL DEFAULT 0 CHECK (checkout_event_count>=0),
  first_checkin_at timestamp,
  last_checkout_at timestamp,
  has_manual_event boolean NOT NULL DEFAULT false,
  has_valid_leave boolean NOT NULL DEFAULT false,
  has_full_day_leave boolean NOT NULL DEFAULT false,
  has_partial_day_leave boolean NOT NULL DEFAULT false,
  active_employee_days integer GENERATED ALWAYS AS
    (CASE WHEN is_employee_active THEN 1 ELSE 0 END) STORED,
  checkin_days integer GENERATED ALWAYS AS
    (CASE WHEN is_employee_active AND checkin_event_count>0 THEN 1 ELSE 0 END) STORED,
  no_checkin_days integer GENERATED ALWAYS AS
    (CASE WHEN is_employee_active AND checkin_event_count=0 THEN 1 ELSE 0 END) STORED,
  checkout_days integer GENERATED ALWAYS AS
    (CASE WHEN is_employee_active AND checkout_event_count>0 THEN 1 ELSE 0 END) STORED,
  no_checkout_days integer GENERATED ALWAYS AS
    (CASE WHEN is_employee_active AND checkout_event_count=0 THEN 1 ELSE 0 END) STORED,
  leave_days integer GENERATED ALWAYS AS
    (CASE WHEN is_employee_active AND has_valid_leave THEN 1 ELSE 0 END) STORED,
  perlu_review boolean NOT NULL DEFAULT false,
  alasan_review text,
  is_date_final boolean NOT NULL DEFAULT false,
  date_assignment_policy text NOT NULL,
  source_snapshot_at timestamptz NOT NULL,
  PRIMARY KEY (pegawai_id,tanggal),
  CHECK ((checkin_event_count>0)=(first_checkin_at IS NOT NULL)),
  CHECK ((checkout_event_count>0)=(last_checkout_at IS NOT NULL)),
  CHECK (is_employee_active IS NULL OR population_basis IS NOT NULL),
  CHECK (NOT (has_full_day_leave OR has_partial_day_leave) OR has_valid_leave)
);
CREATE INDEX attendance_date_department_idx
  ON curated.cur_attendance_daily(tanggal,departemen_id);
COMMENT ON TABLE curated.cur_attendance_daily IS
  'Union population/event/leave employee-date keys. Active population KPI; leave overlaps no-checkin/no-checkout. Unknown active status contributes zero, not inferred inactive.';

-- Preserve legacy load claims rather than letting them describe the empty v2.
CREATE TABLE etl_control.backfill_batch_legacy_20261028 AS
  SELECT * FROM etl_control.backfill_batch;
UPDATE etl_control.backfill_batch
SET status='FAILED',
    catatan=concat_ws(' | ',catatan,
      'INVALIDATED_CURATED_V2_20261028: legacy output archived; v2 empty, reload requires new ETL/date policy')
WHERE status IN ('LOADED','VALIDATED');
CREATE TABLE etl_control.curated_contract_revision (
  revision text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT current_timestamp,
  archive_schema text NOT NULL,
  reload_status text NOT NULL,
  notes text NOT NULL
);
INSERT INTO etl_control.curated_contract_revision
  (revision,archive_schema,reload_status,notes)
VALUES ('20261028_population_v2','curated_legacy_20261028','PENDING_POLICY_AND_ETL',
  'Schema only. Raw/source unchanged. Historical population and overnight attribution pending; do not run legacy backfill against v2.');
COMMIT;
