\set ON_ERROR_STOP on
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '90s';
SELECT 'schedule_master' AS audit,
 count(*) AS total,
 count(*) FILTER (WHERE jam_masuk_awal IS NULL OR jam_masuk IS NULL) AS missing_bounds,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk) AS early_before_start,
 count(*) FILTER (WHERE jam_masuk_awal = jam_masuk) AS equal_bounds,
 count(*) FILTER (WHERE jam_masuk_awal > jam_masuk) AS early_after_start,
 count(*) FILTER (WHERE jam_masuk = time '00:00' AND jam_keluar = time '00:00') AS midnight_schedule
FROM public.m_jadwal;

-- Sample by indexed ID, rather than scan the entire historical transaction table.
WITH recent AS MATERIALIZED (
 SELECT * FROM public.t_checkinout ORDER BY id DESC LIMIT 100000
), checkins AS (
 SELECT t.*, j.id AS master_id, j.jenis AS master_shift, j.hari AS master_day,
        j.jam_masuk AS master_start, j.jam_masuk_awal AS master_early,
        s.id AS shift_id, s.departemen_id AS shift_department
 FROM recent t LEFT JOIN public.m_jadwal j ON j.id=t.jadwal_id
 LEFT JOIN public.m_shift s ON s.id=j.jenis WHERE t.checktype=1
)
SELECT 'recent_checkins' AS audit, count(*) AS checkins,
 min(created_at)::date AS earliest_date, max(created_at)::date AS latest_date,
 count(*) FILTER (WHERE master_id IS NULL) AS missing_master,
 count(*) FILTER (WHERE shift_id IS NULL) AS missing_shift,
 count(*) FILTER (WHERE work_code IS DISTINCT FROM master_shift) AS shift_code_mismatch,
 count(*) FILTER (WHERE shift_department IS DISTINCT FROM departemen) AS department_differs_or_unknown,
 count(*) FILTER (WHERE jam_masuk IS NULL OR jam_masuk_awal IS NULL) AS missing_snapshot_bounds,
 count(*) FILTER (WHERE jam_masuk IS DISTINCT FROM master_start OR jam_masuk_awal IS DISTINCT FROM master_early) AS snapshot_differs_from_current_master,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk) AS early_before_start,
 count(*) FILTER (WHERE jam_masuk_awal = jam_masuk) AS equal_bounds,
 count(*) FILTER (WHERE jam_masuk_awal > jam_masuk) AS early_after_start,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk AND created_at::time < jam_masuk_awal) AS before_early,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk AND created_at::time BETWEEN jam_masuk_awal AND jam_masuk) AS in_window,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk AND created_at::time > jam_masuk) AS after_start
FROM checkins;

-- Earlier records below the first ID of the tagged dashboard fixture.
WITH prior AS MATERIALIZED (
 SELECT * FROM public.t_checkinout
 WHERE id < (SELECT min(id) FROM test_source_dashboard_20261030.events)
 ORDER BY id DESC LIMIT 100000
), checkins AS (
 SELECT t.*, j.id AS master_id, j.jenis AS master_shift, j.hari AS master_day,
        j.jam_masuk AS master_start, j.jam_masuk_awal AS master_early,
        s.id AS shift_id, s.departemen_id AS shift_department
 FROM prior t LEFT JOIN public.m_jadwal j ON j.id=t.jadwal_id
 LEFT JOIN public.m_shift s ON s.id=j.jenis WHERE t.checktype=1
)
SELECT 'prior_checkins' AS audit, count(*) AS checkins,
 min(created_at)::date AS earliest_date, max(created_at)::date AS latest_date,
 count(*) FILTER (WHERE master_id IS NULL) AS missing_master,
 count(*) FILTER (WHERE shift_id IS NULL) AS missing_shift,
 count(*) FILTER (WHERE work_code IS DISTINCT FROM master_shift) AS shift_code_mismatch,
 count(*) FILTER (WHERE shift_department IS DISTINCT FROM departemen) AS department_differs_or_unknown,
 count(*) FILTER (WHERE jam_masuk IS NULL OR jam_masuk_awal IS NULL) AS missing_snapshot_bounds,
 count(*) FILTER (WHERE jam_masuk IS DISTINCT FROM master_start OR jam_masuk_awal IS DISTINCT FROM master_early) AS snapshot_differs_from_current_master,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk) AS early_before_start,
 count(*) FILTER (WHERE jam_masuk_awal = jam_masuk) AS equal_bounds,
 count(*) FILTER (WHERE jam_masuk_awal > jam_masuk) AS early_after_start,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk AND created_at::time < jam_masuk_awal) AS before_early,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk AND created_at::time BETWEEN jam_masuk_awal AND jam_masuk) AS in_window,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk AND created_at::time > jam_masuk) AS after_start
FROM checkins;

SELECT 'constraints' AS audit, tc.table_name, tc.constraint_type, kcu.column_name,
       ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu USING (constraint_catalog,constraint_schema,constraint_name)
LEFT JOIN information_schema.constraint_column_usage ccu USING (constraint_catalog,constraint_schema,constraint_name)
WHERE tc.table_schema='public' AND tc.table_name IN ('m_jadwal','m_shift','t_checkinout')
AND tc.constraint_type='FOREIGN KEY' ORDER BY tc.table_name,kcu.column_name;
COMMIT;
