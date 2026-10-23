BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30min';
SET LOCAL work_mem = '64MB';
WITH ed AS (
 SELECT t.pegawai_id, p.departemen AS dept_snapshot, t.created_at::date AS hari_proksi,
   COUNT(*) AS events,
   COUNT(*) FILTER (WHERE t.jadwal_id IS NULL) AS a1_null,
   COUNT(*) FILTER (WHERE t.jadwal_id IS NOT NULL AND j.id IS NULL) AS a1_orphan,
   COUNT(*) FILTER (WHERE t.checktype IS NULL OR t.checktype NOT IN (1,2)) AS a2_checktype,
   COUNT(*) FILTER (WHERE t.is_wfh IS NULL OR t.is_wfh NOT IN (0,1)) AS a2_wfh,
   COUNT(*) FILTER (WHERE t.is_manual IS NULL) AS a2_manual,
   COUNT(*) FILTER (WHERE t.is_manual IS TRUE AND t.approval_at IS NULL) AS a3_noapproval,
   COUNT(*) FILTER (WHERE t.approval_at IS NOT NULL AND t.approval_at < t.created_at) AS a3_early,
   COUNT(*) FILTER (WHERE t.is_manual IS FALSE AND t.approval_at IS NOT NULL) AS a3_nonmanual,
   COUNT(*) FILTER (WHERE p.created_at IS NOT NULL AND t.created_at < p.created_at) AS a4_prepegawai,
   COUNT(*) FILTER (WHERE t.updated_at IS NOT NULL AND t.updated_at <> t.created_at) AS a7_changed
 FROM public.t_checkinout t
 LEFT JOIN public.m_jadwal j ON j.id = t.jadwal_id
 LEFT JOIN public.m_pegawai p ON p.id = t.pegawai_id
 WHERE t.created_at >= TIMESTAMP '2025-09-01 00:00:00'
   AND t.created_at < TIMESTAMP '2026-09-01 00:00:00'
 GROUP BY t.pegawai_id, p.departemen, t.created_at::date
), totals AS (
 SELECT COUNT(*) AS total_days, COALESCE(SUM(events),0)::bigint AS total_events,
        COUNT(DISTINCT dept_snapshot) AS total_departemen
 FROM ed
), damage AS (
 SELECT
   SUM(a1_null)::bigint AS ev1, COUNT(*) FILTER (WHERE a1_null>0) AS day1,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE a1_null>0) AS dep1,
   SUM(a1_orphan)::bigint AS ev2, COUNT(*) FILTER (WHERE a1_orphan>0) AS day2,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE a1_orphan>0) AS dep2,
   SUM(a2_checktype)::bigint AS ev3, COUNT(*) FILTER (WHERE a2_checktype>0) AS day3,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE a2_checktype>0) AS dep3,
   SUM(a2_wfh)::bigint AS ev4, COUNT(*) FILTER (WHERE a2_wfh>0) AS day4,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE a2_wfh>0) AS dep4,
   SUM(a2_manual)::bigint AS ev5, COUNT(*) FILTER (WHERE a2_manual>0) AS day5,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE a2_manual>0) AS dep5,
   SUM(a3_noapproval)::bigint AS ev6, COUNT(*) FILTER (WHERE a3_noapproval>0) AS day6,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE a3_noapproval>0) AS dep6,
   SUM(a3_early)::bigint AS ev7, COUNT(*) FILTER (WHERE a3_early>0) AS day7,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE a3_early>0) AS dep7,
   SUM(a3_nonmanual)::bigint AS ev8, COUNT(*) FILTER (WHERE a3_nonmanual>0) AS day8,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE a3_nonmanual>0) AS dep8,
   SUM(a4_prepegawai)::bigint AS ev9, COUNT(*) FILTER (WHERE a4_prepegawai>0) AS day9,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE a4_prepegawai>0) AS dep9,
   SUM(a7_changed)::bigint AS ev10, COUNT(*) FILTER (WHERE a7_changed>0) AS day10,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE a7_changed>0) AS dep10
 FROM ed
)
SELECT v.test_id, v.metrik,
 CASE WHEN v.event_count BETWEEN 1 AND 4 THEN '<5' ELSE COALESCE(v.event_count,0)::text END AS event_terdampak,
 CASE WHEN v.days_count BETWEEN 1 AND 4 THEN '<5' ELSE COALESCE(v.days_count,0)::text END AS pegawai_hari_terdampak,
 CASE WHEN v.dept_count BETWEEN 1 AND 4 THEN '<5' ELSE COALESCE(v.dept_count,0)::text END AS departemen_snapshot_terdampak,
 t.total_events AS denominator_event_jendela,
 t.total_days AS denominator_pegawai_hari_teramati,
 t.total_departemen AS departemen_teramati
FROM damage d CROSS JOIN totals t
CROSS JOIN LATERAL (VALUES
 ('A1','jadwal_id_NULL',d.ev1,d.day1,d.dep1),
 ('A1','jadwal_id_orphan',d.ev2,d.day2,d.dep2),
 ('A2','checktype_invalid_atau_NULL',d.ev3,d.day3,d.dep3),
 ('A2','is_wfh_invalid_atau_NULL',d.ev4,d.day4,d.dep4),
 ('A2','is_manual_NULL',d.ev5,d.day5,d.dep5),
 ('A3','manual_tanpa_approval',d.ev6,d.day6,d.dep6),
 ('A3','approval_at_lebih_awal',d.ev7,d.day7,d.dep7),
 ('A3','nonmanual_dengan_approval_at',d.ev8,d.day8,d.dep8),
 ('A4','created_at_sebelum_m_pegawai_created_at',d.ev9,d.day9,d.dep9),
 ('A7','updated_at_berbeda_created_at',d.ev10,d.day10,d.dep10)
) v(test_id,metrik,event_count,days_count,dept_count)
ORDER BY v.test_id, v.metrik;
COMMIT;
