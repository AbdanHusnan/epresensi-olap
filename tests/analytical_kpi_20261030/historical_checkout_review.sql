\set ON_ERROR_STOP on
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';
SET LOCAL max_parallel_workers_per_gather = 2;
-- Fixed physical-block sample. Not independent observations or population totals.
WITH events AS MATERIALIZED (
 SELECT id, created_at, checktype, jadwal_id, work_code, departemen,
        jam_masuk, jam_keluar, jam_keluar_akhir, is_manual, keterangan
 FROM public.t_checkinout TABLESAMPLE SYSTEM (0.1) REPEATABLE (417)
 WHERE created_at >= TIMESTAMP '2024-01-01'
   AND created_at < TIMESTAMP '2026-10-01'
   AND checktype = 2
   AND COALESCE(keterangan, '') NOT LIKE 'SOURCE_DASHBOARD_20261030%'
   AND COALESCE(keterangan, '') NOT LIKE 'BULK_CURATED_20261028%'
   AND COALESCE(keterangan, '') NOT LIKE 'E2E_CURATED_TWO_SHIFT_20261028%'
), details AS (
 SELECT e.*, j.id AS master_id, j.jenis AS shift_id, j.hari AS schedule_day,
        j.jam_keluar AS master_end, j.jam_keluar_akhir AS master_last,
        s.id AS found_shift
 FROM events e LEFT JOIN public.m_jadwal j ON j.id=e.jadwal_id
 LEFT JOIN public.m_shift s ON s.id=j.jenis
)
SELECT COALESCE(EXTRACT(YEAR FROM created_at)::text, 'ALL') AS event_year,
 count(*) AS sampled_checkouts,
 min(created_at)::date AS first_date, max(created_at)::date AS last_date,
 count(*) FILTER (WHERE is_manual IS TRUE) AS manual,
 count(*) FILTER (WHERE master_id IS NULL) AS missing_schedule,
 count(*) FILTER (WHERE found_shift IS NULL) AS missing_shift,
 count(*) FILTER (WHERE master_id IS NOT NULL AND work_code IS DISTINCT FROM shift_id) AS shift_code_mismatch,
 count(*) FILTER (WHERE jam_masuk IS NULL) AS missing_start,
 count(*) FILTER (WHERE jam_keluar IS NULL) AS missing_end,
 count(*) FILTER (WHERE jam_keluar_akhir IS NULL) AS missing_last,
 count(*) FILTER (WHERE jam_keluar IS NOT NULL AND master_id IS NOT NULL AND jam_keluar IS DISTINCT FROM master_end) AS end_differs_from_current,
 count(*) FILTER (WHERE jam_keluar_akhir IS NOT NULL AND master_id IS NOT NULL AND jam_keluar_akhir IS DISTINCT FROM master_last) AS last_differs_from_current,
 count(*) FILTER (WHERE jam_keluar < jam_masuk) AS overnight_indicator,
 count(*) FILTER (WHERE jam_keluar = jam_masuk) AS equal_start_end,
 count(*) FILTER (WHERE jam_keluar > jam_masuk) AS same_day_indicator,
 count(*) FILTER (WHERE jam_keluar > jam_masuk AND jam_keluar_akhir > jam_keluar) AS same_day_ordered_window,
 count(*) FILTER (WHERE jam_keluar > jam_masuk AND jam_keluar_akhir = jam_keluar) AS same_day_equal_window,
 count(*) FILTER (WHERE jam_keluar > jam_masuk AND jam_keluar_akhir < jam_keluar) AS same_day_cross_midnight_or_reversed_window,
 count(*) FILTER (WHERE jam_keluar > jam_masuk AND jam_keluar_akhir > jam_keluar AND created_at::time < jam_keluar) AS before_end,
 count(*) FILTER (WHERE jam_keluar > jam_masuk AND jam_keluar_akhir > jam_keluar AND created_at::time BETWEEN jam_keluar AND jam_keluar_akhir) AS inside_inclusive,
 count(*) FILTER (WHERE jam_keluar > jam_masuk AND jam_keluar_akhir > jam_keluar AND created_at::time > jam_keluar_akhir) AS after_last,
 count(*) FILTER (WHERE jam_keluar > jam_masuk AND jam_keluar_akhir > jam_keluar AND created_at::time = jam_keluar) AS at_end,
 count(*) FILTER (WHERE jam_keluar > jam_masuk AND jam_keluar_akhir > jam_keluar AND created_at::time = jam_keluar_akhir) AS at_last,
 count(*) FILTER (WHERE master_id IS NOT NULL AND lower(schedule_day) IS DISTINCT FROM lower(to_char(created_at, 'Dy'))) AS day_mismatch
FROM details
GROUP BY GROUPING SETS ((EXTRACT(YEAR FROM created_at)), ())
ORDER BY event_year;
WITH events AS MATERIALIZED (
 SELECT created_at, jam_masuk, jam_keluar, jam_keluar_akhir, is_manual
 FROM public.t_checkinout TABLESAMPLE SYSTEM (0.1) REPEATABLE (417)
 WHERE created_at >= TIMESTAMP '2024-01-01' AND created_at < TIMESTAMP '2026-10-01'
 AND checktype=2
 AND COALESCE(keterangan, '') NOT LIKE 'SOURCE_DASHBOARD_20261030%'
 AND COALESCE(keterangan, '') NOT LIKE 'BULK_CURATED_20261028%'
 AND COALESCE(keterangan, '') NOT LIKE 'E2E_CURATED_TWO_SHIFT_20261028%'
), early AS (
 SELECT *, EXTRACT(EPOCH FROM (jam_keluar-created_at::time))/60 AS minutes_before_end
 FROM events WHERE jam_keluar > jam_masuk AND jam_keluar_akhir > jam_keluar
 AND created_at::time < jam_keluar
)
SELECT 'same_day_early_checkouts' AS audit, count(*) AS total,
 count(*) FILTER (WHERE is_manual IS TRUE) AS manual,
 count(*) FILTER (WHERE created_at::time < jam_masuk) AS before_scheduled_start,
 count(*) FILTER (WHERE minutes_before_end <= 5) AS within_5_minutes,
 count(*) FILTER (WHERE minutes_before_end > 5 AND minutes_before_end <= 60) AS over_5_through_60_minutes,
 count(*) FILTER (WHERE minutes_before_end > 60) AS over_60_minutes,
 round(percentile_cont(0.5) WITHIN GROUP (ORDER BY minutes_before_end)::numeric, 2) AS median_minutes_before_end
FROM early;
SELECT 'schedule_master' AS audit, count(*) AS schedules,
 count(*) FILTER (WHERE jam_keluar IS NULL OR jam_keluar_akhir IS NULL) AS missing_bounds,
 count(*) FILTER (WHERE jam_keluar < jam_keluar_akhir) AS end_before_last,
 count(*) FILTER (WHERE jam_keluar = jam_keluar_akhir) AS equal_bounds,
 count(*) FILTER (WHERE jam_keluar > jam_keluar_akhir) AS end_after_last
FROM public.m_jadwal;
COMMIT;
