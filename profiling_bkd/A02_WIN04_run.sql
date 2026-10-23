BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30min';
SET LOCAL work_mem = '64MB';
WITH by_jadwal_day AS (
 SELECT t.pegawai_id, p.departemen AS dept_snapshot, t.jadwal_id,
        t.created_at::date AS hari_proksi,
        COUNT(*) FILTER (WHERE t.checktype=1) AS n_masuk,
        COUNT(*) FILTER (WHERE t.checktype=2) AS n_pulang
 FROM public.t_checkinout t
 LEFT JOIN public.m_pegawai p ON p.id=t.pegawai_id
 WHERE t.created_at >= TIMESTAMP '2025-09-01 00:00:00'
   AND t.created_at < TIMESTAMP '2026-09-01 00:00:00'
 GROUP BY t.pegawai_id,p.departemen,t.jadwal_id,t.created_at::date
), repeated AS (
 SELECT *, (n_masuk>1) AS multi_masuk, (n_pulang>1) AS multi_pulang
 FROM by_jadwal_day
), overall AS (
 SELECT COUNT(*) AS denominator_pegawai_jadwal_hari,
        COUNT(DISTINCT (pegawai_id,hari_proksi)) AS denominator_pegawai_hari,
        COUNT(*) FILTER (WHERE multi_masuk) AS case_masuk,
        COUNT(DISTINCT (pegawai_id,hari_proksi)) FILTER (WHERE multi_masuk) AS day_masuk,
        COUNT(DISTINCT dept_snapshot) FILTER (WHERE multi_masuk) AS dept_masuk,
        COUNT(*) FILTER (WHERE multi_pulang) AS case_pulang,
        COUNT(DISTINCT (pegawai_id,hari_proksi)) FILTER (WHERE multi_pulang) AS day_pulang,
        COUNT(DISTINCT dept_snapshot) FILTER (WHERE multi_pulang) AS dept_pulang,
        COUNT(*) FILTER (WHERE multi_masuk OR multi_pulang) AS case_any,
        COUNT(DISTINCT (pegawai_id,hari_proksi)) FILTER (WHERE multi_masuk OR multi_pulang) AS day_any,
        COUNT(DISTINCT dept_snapshot) FILTER (WHERE multi_masuk OR multi_pulang) AS dept_any
 FROM repeated
)
SELECT 'A7' AS test_id, v.metrik,
 CASE WHEN v.cases BETWEEN 1 AND 4 THEN '<5' ELSE v.cases::text END AS pegawai_jadwal_hari,
 CASE WHEN v.days BETWEEN 1 AND 4 THEN '<5' ELSE v.days::text END AS pegawai_hari,
 CASE WHEN v.depts BETWEEN 1 AND 4 THEN '<5' ELSE v.depts::text END AS departemen_snapshot,
 o.denominator_pegawai_jadwal_hari,o.denominator_pegawai_hari
FROM overall o CROSS JOIN LATERAL (VALUES
 ('masuk_berulang',o.case_masuk,o.day_masuk,o.dept_masuk),
 ('pulang_berulang',o.case_pulang,o.day_pulang,o.dept_pulang),
 ('masuk_atau_pulang_berulang',o.case_any,o.day_any,o.dept_any)
) v(metrik,cases,days,depts);
COMMIT;
