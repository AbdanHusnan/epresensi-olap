BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30min';
SET LOCAL work_mem = '64MB';
WITH by_day AS (
 SELECT t.pegawai_id, p.departemen AS dept_snapshot,
        t.created_at::date AS hari_proksi, COUNT(*) AS n_event
 FROM public.t_checkinout t
 LEFT JOIN public.m_pegawai p ON p.id=t.pegawai_id
 WHERE t.created_at >= TIMESTAMP '2025-09-01 00:00:00'
   AND t.created_at < TIMESTAMP '2026-09-01 00:00:00'
 GROUP BY t.pegawai_id, p.departemen, t.created_at::date
), hist AS (
 SELECT CASE WHEN n_event=1 THEN '01'
             WHEN n_event=2 THEN '02'
             WHEN n_event=3 THEN '03'
             WHEN n_event=4 THEN '04'
             WHEN n_event BETWEEN 5 AND 9 THEN '05-09'
             WHEN n_event BETWEEN 10 AND 19 THEN '10-19'
             ELSE '20+' END AS bucket,
        COUNT(*) AS n_hari, SUM(n_event)::bigint AS n_event,
        COUNT(DISTINCT dept_snapshot) AS n_dept
 FROM by_day
 GROUP BY 1
)
SELECT 'A6' AS test_id, bucket,
 CASE WHEN n_hari BETWEEN 1 AND 4 THEN '<5' ELSE n_hari::text END AS pegawai_hari,
 CASE WHEN n_event BETWEEN 1 AND 4 THEN '<5' ELSE n_event::text END AS event,
 CASE WHEN n_dept BETWEEN 1 AND 4 THEN '<5' ELSE n_dept::text END AS departemen_snapshot,
 (SELECT COUNT(*) FROM by_day) AS denominator_pegawai_hari_teramati
FROM hist ORDER BY bucket;

COMMIT;
