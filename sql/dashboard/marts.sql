-- Install while holding the cooperative ETL advisory lock. Ordinary source views stay intact.
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE TABLE IF NOT EXISTS analytics.mart_dirty_dates (tanggal date PRIMARY KEY);
CREATE TABLE IF NOT EXISTS analytics.mart_refresh_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    refreshed_at timestamptz NOT NULL, generation bigint NOT NULL,
    refreshed_dates integer NOT NULL, source_employee_days bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS analytics.mart_attendance_department_daily AS
SELECT tanggal, departemen_id, nama_departemen,
       count(*) AS employee_days,
       sum(expected_days) AS expected_days, sum(present_days) AS present_days,
       sum(leave_days) AS leave_days, sum(absent_days) AS absent_days,
       sum(evaluated_days) AS evaluated_days, sum(ontime_days) AS ontime_days,
       sum(late_days) AS late_days, sum(late_minutes) AS late_minutes,
       count(*) FILTER (WHERE has_masuk) AS checkin_days,
       count(*) FILTER (WHERE has_pulang) AS checkout_days,
       count(*) FILTER (WHERE work_mode='WFO') AS wfo_days,
       count(*) FILTER (WHERE work_mode='WFH') AS wfh_days,
       count(*) FILTER (WHERE work_mode='MIXED') AS mixed_days,
       count(*) FILTER (WHERE work_mode='UNKNOWN') AS unknown_mode_days,
       NULL::numeric AS attendance_target, NULL::numeric AS ontime_target,
       NULL::numeric AS absence_target, NULL::numeric AS lateness_target,
       'TARGET_NOT_SET'::text AS target_status,
       max(etl_loaded_at) AS etl_loaded_at
FROM analytics.attendance_daily
GROUP BY tanggal, departemen_id, nama_departemen
WITH NO DATA;
CREATE INDEX IF NOT EXISTS mart_department_date_department ON analytics.mart_attendance_department_daily(tanggal, departemen_id);
CREATE TABLE IF NOT EXISTS analytics.mart_attendance_composition_daily AS
SELECT tanggal, departemen_id, nama_departemen, status_kehadiran, work_mode,
       is_expected_workday, count(*) AS employee_days,
       sum(expected_days) AS expected_days, sum(present_days) AS present_days,
       sum(leave_days) AS leave_days, sum(absent_days) AS absent_days,
       max(etl_loaded_at) AS etl_loaded_at
FROM analytics.attendance_daily
GROUP BY tanggal, departemen_id, nama_departemen, status_kehadiran, work_mode, is_expected_workday
WITH NO DATA;
CREATE INDEX IF NOT EXISTS mart_composition_date_department ON analytics.mart_attendance_composition_daily(tanggal, departemen_id);
CREATE TABLE IF NOT EXISTS analytics.mart_attendance_lateness_daily AS
SELECT tanggal, departemen_id, nama_departemen, lateness_bucket,
       sum(late_days) AS late_days, sum(late_minutes) AS late_minutes,
       max(etl_loaded_at) AS etl_loaded_at
FROM analytics.attendance_daily
WHERE late_days > 0
GROUP BY tanggal, departemen_id, nama_departemen, lateness_bucket
WITH NO DATA;
CREATE INDEX IF NOT EXISTS mart_lateness_date_department ON analytics.mart_attendance_lateness_daily(tanggal, departemen_id);
CREATE OR REPLACE VIEW analytics.dashboard_departments AS
SELECT departemen_id, nama_departemen FROM public.dim_departemen;

-- Capture the old AND new dates from each statement, including updates that move rows.
CREATE OR REPLACE FUNCTION analytics.mark_mart_dates() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,analytics AS $$
BEGIN
 IF TG_OP IN ('UPDATE','DELETE') THEN
   INSERT INTO analytics.mart_dirty_dates SELECT DISTINCT tanggal FROM old_rows ON CONFLICT DO NOTHING;
 END IF;
 IF TG_OP IN ('UPDATE','INSERT') THEN
   INSERT INTO analytics.mart_dirty_dates SELECT DISTINCT tanggal FROM new_rows ON CONFLICT DO NOTHING;
 END IF;
 RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION analytics.mark_all_mart_dates() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,analytics AS $$
BEGIN
 INSERT INTO analytics.mart_dirty_dates
 SELECT DISTINCT tanggal FROM analytics.mart_attendance_department_daily
 ON CONFLICT DO NOTHING;
 RETURN NULL;
END $$;

-- Serialize all writers with master/incremental/initial-load, including direct repairs.
CREATE OR REPLACE FUNCTION analytics.lock_mart_writer() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,analytics AS $$
BEGIN
 IF NOT pg_try_advisory_xact_lock(718392046) THEN
   RAISE EXCEPTION 'Another ETL/mart writer is active';
 END IF;
 RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION analytics.refresh_attendance_marts() RETURNS integer
LANGUAGE plpgsql SET search_path=pg_catalog,analytics AS $$
DECLARE dates date[]; source_count bigint; stage_count bigint; late_count bigint;
BEGIN
 IF NOT pg_try_advisory_xact_lock(718392046) THEN
   RAISE EXCEPTION 'Another ETL/mart writer is active';
 END IF;
 SELECT array_agg(tanggal ORDER BY tanggal) INTO dates FROM analytics.mart_dirty_dates;
 IF dates IS NULL THEN RETURN 0; END IF;
 -- Evaluate the facts once for the affected dates; never commit intermediate marts.
 CREATE TEMP TABLE mart_source_stage ON COMMIT DROP AS
 SELECT * FROM analytics.attendance_daily WHERE tanggal=ANY(dates);
 SELECT count(*), coalesce(sum(late_days),0) INTO source_count,late_count FROM pg_temp.mart_source_stage;
 CREATE TEMP TABLE mart_department_stage ON COMMIT DROP AS
SELECT tanggal, departemen_id, nama_departemen,
       count(*) AS employee_days,
       sum(expected_days) AS expected_days, sum(present_days) AS present_days,
       sum(leave_days) AS leave_days, sum(absent_days) AS absent_days,
       sum(evaluated_days) AS evaluated_days, sum(ontime_days) AS ontime_days,
       sum(late_days) AS late_days, sum(late_minutes) AS late_minutes,
       count(*) FILTER (WHERE has_masuk) AS checkin_days,
       count(*) FILTER (WHERE has_pulang) AS checkout_days,
       count(*) FILTER (WHERE work_mode='WFO') AS wfo_days,
       count(*) FILTER (WHERE work_mode='WFH') AS wfh_days,
       count(*) FILTER (WHERE work_mode='MIXED') AS mixed_days,
       count(*) FILTER (WHERE work_mode='UNKNOWN') AS unknown_mode_days,
       NULL::numeric AS attendance_target, NULL::numeric AS ontime_target,
       NULL::numeric AS absence_target, NULL::numeric AS lateness_target,
       'TARGET_NOT_SET'::text AS target_status,
       max(etl_loaded_at) AS etl_loaded_at
FROM pg_temp.mart_source_stage
GROUP BY tanggal, departemen_id, nama_departemen;
 CREATE TEMP TABLE mart_composition_stage ON COMMIT DROP AS
SELECT tanggal, departemen_id, nama_departemen, status_kehadiran, work_mode,
       is_expected_workday, count(*) AS employee_days,
       sum(expected_days) AS expected_days, sum(present_days) AS present_days,
       sum(leave_days) AS leave_days, sum(absent_days) AS absent_days,
       max(etl_loaded_at) AS etl_loaded_at
FROM pg_temp.mart_source_stage
GROUP BY tanggal, departemen_id, nama_departemen, status_kehadiran, work_mode, is_expected_workday;
 CREATE TEMP TABLE mart_lateness_stage ON COMMIT DROP AS
SELECT tanggal, departemen_id, nama_departemen, lateness_bucket,
       sum(late_days) AS late_days, sum(late_minutes) AS late_minutes,
       max(etl_loaded_at) AS etl_loaded_at
FROM pg_temp.mart_source_stage
WHERE late_days > 0
GROUP BY tanggal, departemen_id, nama_departemen, lateness_bucket;
 SELECT coalesce(sum(employee_days),0) INTO stage_count FROM pg_temp.mart_department_stage;
 IF stage_count <> source_count OR
    (SELECT coalesce(sum(employee_days),0) FROM pg_temp.mart_composition_stage) <> source_count OR
    (SELECT coalesce(sum(late_days),0) FROM pg_temp.mart_lateness_stage) <> late_count THEN
   RAISE EXCEPTION 'Mart validation failed: employee-day or lateness totals differ';
 END IF;
 IF EXISTS (SELECT 1 FROM pg_temp.mart_department_stage
     WHERE expected_days <> present_days + leave_days + absent_days
        OR evaluated_days <> ontime_days + late_days) THEN
   RAISE EXCEPTION 'Mart validation failed: KPI components do not reconcile';
 END IF;
 DELETE FROM analytics.mart_attendance_department_daily WHERE tanggal=ANY(dates);
 INSERT INTO analytics.mart_attendance_department_daily SELECT * FROM pg_temp.mart_department_stage;
 ANALYZE analytics.mart_attendance_department_daily;
 DROP TABLE pg_temp.mart_department_stage;
 DELETE FROM analytics.mart_attendance_composition_daily WHERE tanggal=ANY(dates);
 INSERT INTO analytics.mart_attendance_composition_daily SELECT * FROM pg_temp.mart_composition_stage;
 ANALYZE analytics.mart_attendance_composition_daily;
 DROP TABLE pg_temp.mart_composition_stage;
 DELETE FROM analytics.mart_attendance_lateness_daily WHERE tanggal=ANY(dates);
 INSERT INTO analytics.mart_attendance_lateness_daily SELECT * FROM pg_temp.mart_lateness_stage;
 ANALYZE analytics.mart_attendance_lateness_daily;
 DROP TABLE pg_temp.mart_lateness_stage;
 DROP TABLE pg_temp.mart_source_stage;
 DELETE FROM analytics.mart_dirty_dates WHERE tanggal=ANY(dates);
 INSERT INTO analytics.mart_refresh_state VALUES (true,clock_timestamp(),1,cardinality(dates),source_count)
 ON CONFLICT(singleton) DO UPDATE SET refreshed_at=excluded.refreshed_at,
 generation=analytics.mart_refresh_state.generation+1,
 refreshed_dates=excluded.refreshed_dates,source_employee_days=excluded.source_employee_days;
 RETURN cardinality(dates);
END $$;

CREATE OR REPLACE FUNCTION analytics.flush_marts_at_commit() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,analytics AS $$
BEGIN
 PERFORM analytics.refresh_attendance_marts();
 RETURN NULL;
END $$;
-- Only distinct dirty dates schedule deferred callbacks; the first flushes all of them.
DROP TRIGGER IF EXISTS flush_attendance_marts ON analytics.mart_dirty_dates;
CREATE CONSTRAINT TRIGGER flush_attendance_marts AFTER INSERT ON analytics.mart_dirty_dates
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION analytics.flush_marts_at_commit();
DROP TRIGGER IF EXISTS lock_mart_writer ON public.fact_kehadiran;
CREATE TRIGGER lock_mart_writer BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON public.fact_kehadiran
FOR EACH STATEMENT EXECUTE FUNCTION analytics.lock_mart_writer();
DROP TRIGGER IF EXISTS lock_mart_writer ON public.dim_departemen;
CREATE TRIGGER lock_mart_writer BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON public.dim_departemen
FOR EACH STATEMENT EXECUTE FUNCTION analytics.lock_mart_writer();
DROP TRIGGER IF EXISTS mark_mart_insert ON public.fact_kehadiran;
CREATE TRIGGER mark_mart_insert AFTER INSERT ON public.fact_kehadiran
REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION analytics.mark_mart_dates();
DROP TRIGGER IF EXISTS mark_mart_update ON public.fact_kehadiran;
CREATE TRIGGER mark_mart_update AFTER UPDATE ON public.fact_kehadiran
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION analytics.mark_mart_dates();
DROP TRIGGER IF EXISTS mark_mart_delete ON public.fact_kehadiran;
CREATE TRIGGER mark_mart_delete AFTER DELETE ON public.fact_kehadiran
REFERENCING OLD TABLE AS old_rows  FOR EACH STATEMENT EXECUTE FUNCTION analytics.mark_mart_dates();
DROP TRIGGER IF EXISTS mark_mart_truncate ON public.fact_kehadiran;
CREATE TRIGGER mark_mart_truncate BEFORE TRUNCATE ON public.fact_kehadiran
FOR EACH STATEMENT EXECUTE FUNCTION analytics.mark_all_mart_dates();
CREATE OR REPLACE FUNCTION analytics.mark_mart_dimension_dates() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,analytics AS $$
DECLARE changed boolean := false;
BEGIN
 IF TG_OP IN ('UPDATE','DELETE') THEN
   SELECT EXISTS(SELECT 1 FROM old_rows) INTO changed;
 END IF;
 IF NOT changed AND TG_OP IN ('UPDATE','INSERT') THEN
   SELECT EXISTS(SELECT 1 FROM new_rows) INTO changed;
 END IF;
 IF changed THEN
   INSERT INTO analytics.mart_dirty_dates
   SELECT DISTINCT tanggal FROM analytics.mart_attendance_department_daily ON CONFLICT DO NOTHING;
 END IF;
 RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS mark_mart_dimension ON public.dim_departemen;
DROP TRIGGER IF EXISTS mark_mart_dimension_insert ON public.dim_departemen;
CREATE TRIGGER mark_mart_dimension_insert AFTER INSERT ON public.dim_departemen
REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION analytics.mark_mart_dimension_dates();
DROP TRIGGER IF EXISTS mark_mart_dimension_update ON public.dim_departemen;
CREATE TRIGGER mark_mart_dimension_update AFTER UPDATE ON public.dim_departemen
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION analytics.mark_mart_dimension_dates();
DROP TRIGGER IF EXISTS mark_mart_dimension_delete ON public.dim_departemen;
CREATE TRIGGER mark_mart_dimension_delete AFTER DELETE ON public.dim_departemen
REFERENCING OLD TABLE AS old_rows  FOR EACH STATEMENT EXECUTE FUNCTION analytics.mark_mart_dimension_dates();
DROP TRIGGER IF EXISTS mark_mart_dimension_truncate ON public.dim_departemen;
CREATE TRIGGER mark_mart_dimension_truncate AFTER TRUNCATE ON public.dim_departemen
FOR EACH STATEMENT EXECUTE FUNCTION analytics.mark_all_mart_dates();
REVOKE ALL ON FUNCTION analytics.mark_mart_dimension_dates() FROM PUBLIC;

REVOKE ALL ON FUNCTION analytics.mark_mart_dates() FROM PUBLIC;
REVOKE ALL ON FUNCTION analytics.mark_all_mart_dates() FROM PUBLIC;
REVOKE ALL ON FUNCTION analytics.lock_mart_writer() FROM PUBLIC;
REVOKE ALL ON FUNCTION analytics.refresh_attendance_marts() FROM PUBLIC;
REVOKE ALL ON FUNCTION analytics.flush_marts_at_commit() FROM PUBLIC;
GRANT SELECT ON analytics.mart_attendance_department_daily,
 analytics.mart_attendance_composition_daily, analytics.mart_attendance_lateness_daily,
 analytics.dashboard_departments, analytics.mart_refresh_state TO dashboard_reader;
CREATE UNIQUE INDEX IF NOT EXISTS mart_department_grain ON analytics.mart_attendance_department_daily(tanggal,departemen_id) NULLS NOT DISTINCT;
CREATE UNIQUE INDEX IF NOT EXISTS mart_composition_grain ON analytics.mart_attendance_composition_daily(tanggal,departemen_id,status_kehadiran,work_mode,is_expected_workday) NULLS NOT DISTINCT;
CREATE UNIQUE INDEX IF NOT EXISTS mart_lateness_grain ON analytics.mart_attendance_lateness_daily(tanggal,departemen_id,lateness_bucket) NULLS NOT DISTINCT;
