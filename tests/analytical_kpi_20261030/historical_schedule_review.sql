\set ON_ERROR_STOP on
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';
SET LOCAL max_parallel_workers_per_gather = 2;
-- Reproducible physical-block sample. SYSTEM samples blocks rather than
-- independent rows, so results are not population totals or precise estimates.
WITH events AS MATERIALIZED (
 SELECT id, pegawai_id, created_at, checktype, jadwal_id, work_code, departemen,
        jam_masuk, jam_masuk_awal, jam_keluar, is_manual, keterangan
 FROM public.t_checkinout TABLESAMPLE SYSTEM (0.1) REPEATABLE (417)
 WHERE created_at >= TIMESTAMP '2024-01-01'
   AND created_at < TIMESTAMP '2026-10-01'
   AND checktype = 1
   AND COALESCE(keterangan, '') NOT LIKE 'SOURCE_DASHBOARD_20261030%'
   AND COALESCE(keterangan, '') NOT LIKE 'BULK_CURATED_20261028%'
   AND COALESCE(keterangan, '') NOT LIKE 'E2E_CURATED_TWO_SHIFT_20261028%'
), details AS (
 SELECT e.*, j.id AS master_id, j.jenis AS shift_id, j.jam_masuk AS master_start,
        j.jam_masuk_awal AS master_early, j.hari AS schedule_day,
        s.id AS found_shift, s.departemen_id AS shift_department
 FROM events e LEFT JOIN public.m_jadwal j ON j.id=e.jadwal_id
 LEFT JOIN public.m_shift s ON s.id=j.jenis
)
SELECT COALESCE(EXTRACT(YEAR FROM created_at)::text, 'ALL') AS event_year,
 count(*) AS sampled_checkins,
 min(created_at)::date AS first_date, max(created_at)::date AS last_date,
 count(*) FILTER (WHERE is_manual IS TRUE) AS manual,
 count(*) FILTER (WHERE jadwal_id IS NULL) AS missing_schedule_id,
 count(*) FILTER (WHERE master_id IS NULL) AS missing_schedule,
 count(*) FILTER (WHERE found_shift IS NULL) AS missing_shift,
 count(*) FILTER (WHERE master_id IS NOT NULL AND work_code IS DISTINCT FROM shift_id) AS shift_code_mismatch,
 count(*) FILTER (WHERE jam_masuk IS NULL) AS missing_transaction_start,
 count(*) FILTER (WHERE jam_masuk_awal IS NULL) AS missing_transaction_early,
 count(*) FILTER (WHERE master_id IS NOT NULL AND jam_masuk IS NOT NULL AND jam_masuk IS DISTINCT FROM master_start) AS transaction_start_differs,
 count(*) FILTER (WHERE master_id IS NOT NULL AND jam_masuk_awal IS NOT NULL AND jam_masuk_awal IS DISTINCT FROM master_early) AS transaction_early_differs,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk) AS ordinary_window,
 count(*) FILTER (WHERE jam_masuk_awal = jam_masuk) AS equal_bounds,
 count(*) FILTER (WHERE jam_masuk_awal > jam_masuk) AS reversed_bounds,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk AND created_at::time < jam_masuk_awal) AS before_early,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk AND created_at::time BETWEEN jam_masuk_awal AND jam_masuk) AS inside_inclusive,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk AND created_at::time > jam_masuk) AS after_start,
 count(*) FILTER (WHERE jam_masuk_awal < jam_masuk AND created_at::time = jam_masuk) AS at_start,
 count(*) FILTER (WHERE master_id IS NOT NULL AND lower(schedule_day) IS DISTINCT FROM lower(to_char(created_at, 'Dy'))) AS day_mismatch,
 count(*) FILTER (WHERE shift_department IS NULL) AS missing_shift_department,
 count(*) FILTER (WHERE shift_department IS NOT NULL AND departemen IS DISTINCT FROM shift_department) AS other_shift_department
FROM details
GROUP BY GROUPING SETS ((EXTRACT(YEAR FROM created_at)), ())
ORDER BY event_year;
COMMIT;
