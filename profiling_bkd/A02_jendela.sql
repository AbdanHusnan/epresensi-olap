-- BKD Jatim / Data Profiling Kelompok A / Jendela pegawai-hari
-- Periode [2025-09-01, 2026-09-01). work_date = created_at::date PROKSI,
-- BUKAN tanggal kerja final. Departemen = atribut m_pegawai SAAT SNAPSHOT,
-- BUKAN histori organisasi; jangan tafsirkan sebagai historical as-of.
-- Semua output agregat; sel hitungan 1..4 disamarkan.
-- Jalankan bagian-bagian bertanda QUERY secara terpisah bila beban server tinggi.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15min';
SET LOCAL work_mem = '64MB';

-- QUERY A-WIN-01: SIZING DAMPAK A1, A2, A3, A4, A7.
-- Denominator event: seluruh event bertimestamp dalam jendela.
-- Denominator pegawai-hari: pegawai x tanggal kalender dengan >=1 event.
-- Pegawai-hari tanpa event TIDAK termasuk denominator ini.
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

-- QUERY A-WIN-02: A5 duplicate signature & near duplicate (< 1 menit).
-- IDENTIK di sini hanya 8 kolom profil (pegawai_id, jadwal_id, checktype,
-- created_at, is_wfh, is_manual, approval_at, updated_at), BUKAN seluruh row.
-- Near-duplicate = tetangga berurutan pada pegawai/jadwal/checktype.
-- Tidak membuktikan koreksi/revisi, juga tidak menyatakan event harus dihapus.
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

-- QUERY A-WIN-03: A6 jumlah event per pegawai-tanggal kalender (proksi).
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

-- QUERY A-WIN-04: A7 perulangan checktype sama pada pegawai-jadwal-hari.
-- Bukti pola; bukan bukti identitas sesi atau mekanisme perubahan terakhir.
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
