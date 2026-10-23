BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30min';
SET LOCAL work_mem = '64MB';
WITH events AS (
 SELECT t.id, t.pegawai_id, p.departemen AS dept_snapshot, t.jadwal_id,
        t.checktype, t.created_at, t.is_wfh, t.is_manual,
        t.approval_at, t.updated_at
 FROM public.t_checkinout t
 LEFT JOIN public.m_pegawai p ON p.id=t.pegawai_id
 WHERE t.created_at >= TIMESTAMP '2025-08-31 23:59:00'
   AND t.created_at < TIMESTAMP '2026-09-01 00:00:00'
), marks AS (
 SELECT events.*,
   ROW_NUMBER() OVER (
     PARTITION BY pegawai_id,jadwal_id,checktype,created_at,is_wfh,
                  is_manual,approval_at,updated_at ORDER BY id
   ) AS signature_rownum,
   LAG(created_at) OVER (
     PARTITION BY pegawai_id,jadwal_id,checktype ORDER BY created_at,id
   ) AS prev_created_at
 FROM events
), per_day AS (
 SELECT pegawai_id, dept_snapshot, created_at::date AS hari_proksi,
   COUNT(*) FILTER (WHERE signature_rownum>1) AS excess_identik,
   COUNT(*) FILTER (WHERE prev_created_at IS NOT NULL
       AND created_at-prev_created_at < INTERVAL '1 minute') AS near_adjacent,
   COUNT(*) FILTER (WHERE prev_created_at IS NOT NULL
       AND created_at>prev_created_at
       AND created_at-prev_created_at < INTERVAL '1 minute') AS near_waktu_berbeda
 FROM marks
 WHERE created_at >= TIMESTAMP '2025-09-01 00:00:00'
 GROUP BY pegawai_id, dept_snapshot, created_at::date
), agg AS (
 SELECT COUNT(*) AS observed_days,
   COALESCE(SUM(excess_identik),0)::bigint AS ex,
   COUNT(*) FILTER (WHERE excess_identik>0) AS exday,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE excess_identik>0) AS exdep,
   COALESCE(SUM(near_adjacent),0)::bigint AS nearall,
   COUNT(*) FILTER (WHERE near_adjacent>0) AS nearday,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE near_adjacent>0) AS neardep,
   COALESCE(SUM(near_waktu_berbeda),0)::bigint AS neardifferent,
   COUNT(*) FILTER (WHERE near_waktu_berbeda>0) AS differentday,
   COUNT(DISTINCT dept_snapshot) FILTER (WHERE near_waktu_berbeda>0) AS differentdep
 FROM per_day
)
SELECT 'A5' AS test_id, v.metrik,
 CASE WHEN v.affected_events BETWEEN 1 AND 4 THEN '<5' ELSE v.affected_events::text END AS event_berlebih_atau_berdekatan,
 CASE WHEN v.affected_days BETWEEN 1 AND 4 THEN '<5' ELSE v.affected_days::text END AS pegawai_hari_terdampak,
 CASE WHEN v.affected_depts BETWEEN 1 AND 4 THEN '<5' ELSE v.affected_depts::text END AS departemen_snapshot_terdampak,
 a.observed_days AS denominator_pegawai_hari_teramati
FROM agg a CROSS JOIN LATERAL (VALUES
 ('identik_signature_excess',a.ex,a.exday,a.exdep),
 ('near_adjacent_lt_1_menit_termasuk_identik',a.nearall,a.nearday,a.neardep),
 ('near_positif_lt_1_menit',a.neardifferent,a.differentday,a.differentdep)
) v(metrik,affected_events,affected_days,affected_depts);
COMMIT;
