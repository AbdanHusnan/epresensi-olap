\set ON_ERROR_STOP on
BEGIN;
SELECT pg_advisory_xact_lock(hashtext('SIMULATED_202611'));
CREATE TABLE IF NOT EXISTS etl_control.simulation_month_202611 (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 seed text NOT NULL DEFAULT 'november-2026-v1',
 created_at timestamptz NOT NULL DEFAULT now(),
 description text NOT NULL DEFAULT 'Simulated transactions with actual extracted employee and schedule master; all November calendar days. Not observed attendance.'
);
INSERT INTO etl_control.simulation_month_202611(singleton) VALUES(true) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS etl_control.simulation_employee_202611 AS
SELECT p.id emp,p.departemen dep,p.status,p.updated_at,p.extracted_at,
 u.uid
FROM raw.raw_pegawai p LEFT JOIN (SELECT pegawai_id,min(id) uid FROM raw.raw_user GROUP BY pegawai_id) u ON u.pegawai_id=p.id WHERE p.status IN(1,2,3,4);
CREATE UNIQUE INDEX IF NOT EXISTS simulation_employee_202611_pk ON etl_control.simulation_employee_202611(emp);
CREATE TABLE IF NOT EXISTS etl_control.simulation_schedule_202611 AS
WITH eligible AS (
 SELECT j.*,s.departemen_id,
 CASE lower(trim(j.hari)) WHEN 'mon' THEN 1 WHEN 'senin' THEN 1
 WHEN 'tue' THEN 2 WHEN 'selasa' THEN 2 WHEN 'wed' THEN 3 WHEN 'rabu' THEN 3
 WHEN 'thu' THEN 4 WHEN 'kamis' THEN 4 WHEN 'fri' THEN 5 WHEN 'jumat' THEN 5 WHEN 'jumat ' THEN 5
 WHEN 'sat' THEN 6 WHEN 'sabtu' THEN 6 WHEN 'sun' THEN 7 WHEN 'minggu' THEN 7 END dow
 FROM raw.raw_jadwal j JOIN raw.raw_shift s ON s.id=j.jenis
 WHERE s.status IS TRUE AND j.jam_masuk_awal<=j.jam_masuk
 AND j.jam_keluar>j.jam_masuk AND j.jam_keluar_akhir>=j.jam_keluar
 AND j.jam_masuk<=time '22:00'
)
SELECT DISTINCT ON (departemen_id,dow) * FROM eligible WHERE dow IS NOT NULL
ORDER BY departemen_id,dow,jam_masuk,id;
CREATE UNIQUE INDEX IF NOT EXISTS simulation_schedule_202611_pk ON etl_control.simulation_schedule_202611(departemen_id,dow);
CREATE TABLE IF NOT EXISTS etl_control.simulation_day_202611 (
 tanggal date PRIMARY KEY CHECK(tanggal BETWEEN DATE '2026-11-01' AND DATE '2026-11-30'),
 batch_id text NOT NULL UNIQUE,event_count integer NOT NULL,leave_count integer NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS etl_control.simulation_day_employee_202611 (
 tanggal date NOT NULL,emp integer NOT NULL,scenario text NOT NULL,jadwal_id integer,
 PRIMARY KEY(tanggal,emp)
);
CREATE OR REPLACE FUNCTION etl_control.seed_simulated_day_202611(p_day date)
RETURNS text LANGUAGE plpgsql SET work_mem='64MB' SET jit=off AS $$
DECLARE
 v_batch text := 'SIMULATED_202611_'||to_char(p_day,'YYYYMMDD');
 v_event_base bigint; v_leave_base bigint; v_events integer[]; v_leaves integer[];
 v_population integer;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('SIMULATED_202611'));
 PERFORM pg_advisory_xact_lock(hashtext('curated_population_v2_apply'));
 IF current_database()<>'staging_bkd' OR p_day NOT BETWEEN DATE '2026-11-01' AND DATE '2026-11-30' THEN
  RAISE EXCEPTION 'Actual staging_bkd, November 2026 only'; END IF;
 IF EXISTS(SELECT 1 FROM etl_control.simulation_day_202611 WHERE tanggal=p_day) THEN RETURN v_batch; END IF;
 IF EXISTS(SELECT 1 FROM curated.cur_attendance_daily WHERE tanggal=p_day) THEN
  RAISE EXCEPTION 'Date % already has curated records outside this generator',p_day; END IF;
 SELECT count(*) INTO v_population FROM etl_control.simulation_employee_202611;
 IF v_population=0 THEN RAISE EXCEPTION 'Master population is empty'; END IF;
 -- Reserve IDs beyond existing raw PKs. Locks prevent concurrent raw insert races.
 LOCK TABLE raw.raw_checkinout,raw.raw_perizinan IN SHARE ROW EXCLUSIVE MODE;
 SELECT COALESCE(max(id),0)::bigint INTO v_event_base FROM raw.raw_checkinout;
 SELECT COALESCE(max(id),0)::bigint INTO v_leave_base FROM raw.raw_perizinan;
 IF v_event_base+v_population*2>2147483647 OR v_leave_base+v_population>2147483647 THEN
  RAISE EXCEPTION 'Insufficient integer ID space'; END IF;
 CREATE TEMP TABLE simulation_people ON COMMIT DROP AS
 SELECT p.*,row_number() OVER(ORDER BY p.emp)::integer n,j.id schedule_id,
 j.jenis,j.hari,j.jam_masuk_awal,j.jam_masuk,j.jam_keluar,j.jam_keluar_akhir,j.flexible_time,
 CASE WHEN j.id IS NULL THEN 'NO_SCHEDULE'
 WHEN r<58 THEN 'ON_TIME' WHEN r<78 THEN 'LATE'
 WHEN r<83 THEN 'FULL_DAY_IZIN' WHEN r<87 THEN 'PARTIAL_MORNING'
 WHEN r<91 THEN 'PARTIAL_AFTERNOON' WHEN r<94 THEN 'MISSING_CHECKOUT'
 WHEN r<97 THEN 'MISSING_CHECKIN' ELSE 'ABSENT' END scenario
 FROM etl_control.simulation_employee_202611 p
 CROSS JOIN LATERAL (SELECT (('x'||substr(md5(p.emp::text||'/'||p_day::text||'/november-2026-v1'),1,8))::bit(32)::bigint % 100)::integer r) rnd
 LEFT JOIN etl_control.simulation_schedule_202611 j ON j.departemen_id=p.dep AND j.dow=extract(isodow FROM p_day);
 INSERT INTO etl_control.simulation_day_employee_202611 SELECT p_day,emp,scenario,schedule_id FROM simulation_people;
 -- Explicit simulation population policy: extrapolate current extraction for
 -- this requested month only. It does not establish historical/future status.
 INSERT INTO curated.cur_employee_population_daily
 (pegawai_id,tanggal,departemen_id,status_sumber,is_employee_active,population_basis,source_snapshot_at,source_updated_at)
 SELECT emp,p_day,dep,status,true,'EXTRACTION_SNAPSHOT',extracted_at,updated_at FROM simulation_people;
 -- Baseline retains employees with no events or leave, including missing schedules.
 INSERT INTO curated.cur_attendance_daily
 (pegawai_id,tanggal,departemen_id,is_employee_active,population_basis,lateness_status,lateness_reason,
 date_assignment_policy,source_snapshot_at,perlu_review,alasan_review)
 SELECT emp,p_day,dep,true,'EXTRACTION_SNAPSHOT','NOT_ASSESSED','NO_CHECKIN',
 'SIMULATED_MONTH_202611',now(),schedule_id IS NULL,
 CASE WHEN schedule_id IS NULL THEN 'SIMULATED_NO_MATCHING_ACTIVE_SAME_DAY_SCHEDULE' END FROM simulation_people;
 CREATE TEMP TABLE simulation_event_load (LIKE raw.raw_checkinout INCLUDING DEFAULTS) ON COMMIT DROP;
 WITH ins AS (
 INSERT INTO simulation_event_load
 (id,pegawai_id,departemen,checktype,created_at,updated_at,work_code,jadwal_id,hari,
 jam_masuk_awal,jam_masuk,jam_keluar,jam_keluar_akhir,flexible_time,is_manual,is_wfh,keterangan,extracted_at,pipeline_run_id)
 SELECT (v_event_base+n*2+side-1)::integer,emp,dep,side,
 p_day+CASE WHEN side=1 THEN
   CASE WHEN scenario='LATE' THEN LEAST(jam_masuk+interval '5 minutes'+(n%40)*interval '1 minute',jam_keluar-interval '1 minute')
        ELSE jam_masuk_awal+(jam_masuk-jam_masuk_awal)*((n%100)/100.0) END
 ELSE jam_keluar+(jam_keluar_akhir-jam_keluar)*((n%100)/100.0) END,
 p_day+time '23:59:00',jenis,schedule_id,hari,jam_masuk_awal,jam_masuk,jam_keluar,jam_keluar_akhir,
 flexible_time,false,0,'SIMULATED_202611:'||scenario,now(),'SIMULATED_202611'
 FROM simulation_people CROSS JOIN generate_series(1,2) side
 WHERE schedule_id IS NOT NULL AND
 ((side=1 AND scenario IN('ON_TIME','LATE','PARTIAL_AFTERNOON','MISSING_CHECKOUT')) OR
  (side=2 AND scenario IN('ON_TIME','LATE','PARTIAL_MORNING','MISSING_CHECKIN')))
 RETURNING id)
 SELECT COALESCE(array_agg(id),'{}'::integer[]) INTO v_events FROM ins;
 -- COPY uses PostgreSQL bulk insertion while retaining the same transaction,
 -- raw table, indexes and manifest contract. The dedicated file is overwritten
 -- only under this run's advisory lock; loader removes it after generation.
 COPY simulation_event_load TO '/tmp/simulated_202611_events.csv' WITH (FORMAT csv);
 COPY raw.raw_checkinout FROM '/tmp/simulated_202611_events.csv' WITH (FORMAT csv);
 WITH ins AS (
 INSERT INTO raw.raw_perizinan
 (id,pegawai_id,user_id,departemen,jenis_ijin,tipe_ijin,approval,approval_at,tgl_ijin,tgl_ijin_sampai,
 created_at,updated_at,alasan,catatan,extracted_at,pipeline_run_id)
 SELECT (v_leave_base+n)::integer,emp,uid,dep,
 (SELECT min(j.id) FROM raw.raw_jenis_ijin j WHERE j.setengah_hari=(scenario<>'FULL_DAY_IZIN')
 AND j.tipe_id IN(SELECT id FROM raw.raw_tipe_ijin)),
 CASE scenario WHEN 'FULL_DAY_IZIN' THEN 1 WHEN 'PARTIAL_MORNING' THEN 2 ELSE 3 END,
 true,p_day+time '06:00',p_day,p_day,p_day+time '05:00',p_day+time '06:00',
 'SIMULATED_202611:'||scenario,'Generated November dashboard transactions; not observed attendance',now(),'SIMULATED_202611'
 FROM simulation_people WHERE scenario IN('FULL_DAY_IZIN','PARTIAL_MORNING','PARTIAL_AFTERNOON')
 RETURNING id)
 SELECT COALESCE(array_agg(id),'{}'::integer[]) INTO v_leaves FROM ins;
 PERFORM etl_control.enqueue_curated_batch(v_batch,p_event_ids=>v_events,p_leave_ids=>v_leaves);
 INSERT INTO etl_control.simulation_day_202611(tanggal,batch_id,event_count,leave_count)
 VALUES(p_day,v_batch,cardinality(v_events),cardinality(v_leaves));
 RETURN v_batch;
END $$;
-- Bound temporary-table planning memory to this consumer only.
ALTER FUNCTION etl_control.apply_curated_batch(text) SET work_mem='64MB';
ALTER FUNCTION etl_control.apply_curated_batch(text) SET jit=off;
COMMIT;
