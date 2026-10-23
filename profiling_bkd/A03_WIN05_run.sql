BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30min';
SET LOCAL work_mem = '64MB';
WITH classified AS (
 SELECT t.pegawai_id, p.departemen AS dept_snapshot,
        t.created_at::date AS hari_proksi, t.jadwal_id, t.checktype,
        t.is_manual, t.approval_at,
        CASE
          WHEN t.jadwal_id IS NULL THEN 'jadwal_null'
          WHEN j.id IS NULL THEN 'jadwal_orphan'
          WHEN s.id IS NULL THEN 'jadwal_tanpa_shift'
          WHEN s.nama IS NULL THEN 'nama_shift_null'
          WHEN (UPPER(s.nama) LIKE '%REGULAR%' OR UPPER(s.nama) LIKE '%REGULER%')
               AND s.status IS TRUE THEN 'reguler_aktif_snapshot'
          WHEN (UPPER(s.nama) LIKE '%REGULAR%' OR UPPER(s.nama) LIKE '%REGULER%')
               THEN 'reguler_status_bukan_true_snapshot'
          ELSE 'nonreguler_berdasarkan_keyword'
        END AS kelas,
        (t.checktype IN (1,2) AND
          (t.is_manual IS FALSE OR (t.is_manual IS TRUE AND t.approval_at IS NOT NULL)))
          AS lolos_checktype_dan_manual_saja
 FROM public.t_checkinout t
 LEFT JOIN public.m_pegawai p ON p.id=t.pegawai_id
 LEFT JOIN public.m_jadwal j ON j.id=t.jadwal_id
 LEFT JOIN public.m_shift s ON s.id=j.jenis
 WHERE t.created_at >= TIMESTAMP '2025-09-01 00:00:00'
   AND t.created_at < TIMESTAMP '2026-09-01 00:00:00'
), by_class AS (
 SELECT kelas,
        COUNT(*) AS event_count,
        COUNT(DISTINCT (pegawai_id,hari_proksi)) AS employee_days,
        COUNT(DISTINCT dept_snapshot) AS affected_depts
 FROM classified GROUP BY kelas
), by_day AS (
 SELECT pegawai_id,dept_snapshot,hari_proksi,
        COUNT(DISTINCT jadwal_id) FILTER (WHERE kelas='reguler_aktif_snapshot') AS regular_schedules_raw,
        COUNT(DISTINCT jadwal_id) FILTER (
          WHERE kelas='reguler_aktif_snapshot' AND lolos_checktype_dan_manual_saja
        ) AS regular_schedules_filtered
 FROM classified
 GROUP BY pegawai_id,dept_snapshot,hari_proksi
), multi AS (
 SELECT COUNT(*) AS denominator_days,
        COUNT(*) FILTER (WHERE regular_schedules_raw>1) AS multi_raw,
        COUNT(DISTINCT dept_snapshot) FILTER (WHERE regular_schedules_raw>1) AS multi_dept_raw,
        COUNT(*) FILTER (WHERE regular_schedules_filtered>1) AS multi_filtered,
        COUNT(DISTINCT dept_snapshot) FILTER (WHERE regular_schedules_filtered>1) AS multi_dept_filtered,
        MAX(regular_schedules_raw) AS max_jadwal_reguler_pada_hari
 FROM by_day
)
SELECT 'A8' AS test_id, 'kategori_event_master_snapshot' AS metrik,
       kelas AS kategori,
       CASE WHEN event_count BETWEEN 1 AND 4 THEN '<5' ELSE event_count::text END AS event_atau_pegawai_hari,
       CASE WHEN employee_days BETWEEN 1 AND 4 THEN '<5' ELSE employee_days::text END AS pegawai_hari_terdampak,
       CASE WHEN affected_depts BETWEEN 1 AND 4 THEN '<5' ELSE affected_depts::text END AS departemen_snapshot_terdampak,
       (SELECT SUM(event_count) FROM by_class) AS denominator_event_jendela,
       (SELECT denominator_days FROM multi) AS denominator_pegawai_hari
FROM by_class
UNION ALL
SELECT 'A8', 'pegawai_hari_multi_jadwal_reguler', 'raw_event',
       CASE WHEN multi_raw BETWEEN 1 AND 4 THEN '<5' ELSE multi_raw::text END,
       CASE WHEN multi_raw BETWEEN 1 AND 4 THEN '<5' ELSE multi_raw::text END,
       CASE WHEN multi_dept_raw BETWEEN 1 AND 4 THEN '<5' ELSE multi_dept_raw::text END,
       (SELECT SUM(event_count) FROM by_class), denominator_days
FROM multi
UNION ALL
SELECT 'A8', 'pegawai_hari_multi_jadwal_reguler', 'checktype_manual_filter_only',
       CASE WHEN multi_filtered BETWEEN 1 AND 4 THEN '<5' ELSE multi_filtered::text END,
       CASE WHEN multi_filtered BETWEEN 1 AND 4 THEN '<5' ELSE multi_filtered::text END,
       CASE WHEN multi_dept_filtered BETWEEN 1 AND 4 THEN '<5' ELSE multi_dept_filtered::text END,
       (SELECT SUM(event_count) FROM by_class), denominator_days
FROM multi
ORDER BY metrik,kategori;
COMMIT;
