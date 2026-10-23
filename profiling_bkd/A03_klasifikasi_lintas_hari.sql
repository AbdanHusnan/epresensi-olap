-- BKD Jatim / Data Profiling Kelompok A / A8 dan A9.
-- Seluruh klasifikasi terhadap m_shift.status = STATUS PADA SNAPSHOT,
-- tidak dapat dianggap sebagai status historis saat setiap event tercipta.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15min';
SET LOCAL work_mem = '64MB';

-- QUERY A-WIN-05: A8 kelas event dan >1 jadwal_id reguler per pegawai-hari.
-- REGULER = nama memuat REGULAR/REGULER dan m_shift.status IS TRUE (saat snapshot).
-- Jumlah kategori event tidak boleh dibaca sebagai jumlah pegawai-hari.
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

-- QUERY A-MASTER-01: A9 jadwal yang JAM KELUAR < JAM MASUK.
-- ::time mensyaratkan nilai kolom bisa diparse sebagai jam.
-- Jika error tipe/format, hentikan dan kirim pesan error tanpa menebak/membersihkan.
WITH m AS (
 SELECT j.id, s.departemen_id,
   (j.jam_masuk IS NULL OR j.jam_keluar IS NULL) AS waktu_tidak_lengkap,
   (j.jam_masuk IS NOT NULL AND j.jam_keluar IS NOT NULL
    AND j.jam_keluar::time < j.jam_masuk::time) AS indikasi_lintas_tengah_malam
 FROM public.m_jadwal j
 LEFT JOIN public.m_shift s ON s.id=j.jenis
), summary AS (
 SELECT COUNT(*) AS jadwal_total,
        COUNT(*) FILTER (WHERE waktu_tidak_lengkap) AS jadwal_jam_null,
        COUNT(*) FILTER (WHERE indikasi_lintas_tengah_malam) AS jadwal_lintas_hari,
        COUNT(DISTINCT departemen_id) FILTER (WHERE indikasi_lintas_tengah_malam) AS departemen_lintas_hari
 FROM m
)
SELECT 'A9' AS test_id, metrik,
 CASE WHEN nilai BETWEEN 1 AND 4 THEN '<5' ELSE nilai::text END AS nilai,
 s.jadwal_total AS denominator_jadwal
FROM summary s CROSS JOIN LATERAL (VALUES
 ('jam_masuk_atau_keluar_null',s.jadwal_jam_null),
 ('jam_keluar_lebih_awal_dari_jam_masuk',s.jadwal_lintas_hari),
 ('departemen_snapshot_dengan_jadwal_lintas_hari',s.departemen_lintas_hari)
) v(metrik,nilai);

-- QUERY A-WIN-06: A9 check-out tanpa check-in pada tanggal kalender sama,
-- untuk jadwal berindikasi lintas tengah malam; klasifikasi KANDIDAT saja.
-- Data 2025-08-31 dibaca sebagai konteks D-1 untuk 2025-09-01.
-- Check-out 2026-09-01 setelah shift 2026-08-31 berada di HARI SNAPSHOT
-- yang cakupannya tidak penuh: TIDAK dijadikan simpulan kelengkapan lintas hari.
WITH ev AS (
 SELECT t.pegawai_id,p.departemen AS dept_snapshot,t.jadwal_id,
        t.created_at::date AS hari_kalender_proksi,t.created_at::time AS jam_event,
        t.checktype,j.jam_keluar::time AS jam_keluar,
        (j.id IS NOT NULL AND j.jam_masuk IS NOT NULL AND j.jam_keluar IS NOT NULL
         AND j.jam_keluar::time < j.jam_masuk::time) AS jadwal_lintas_hari
 FROM public.t_checkinout t
 LEFT JOIN public.m_pegawai p ON p.id=t.pegawai_id
 LEFT JOIN public.m_jadwal j ON j.id=t.jadwal_id
 WHERE t.created_at >= TIMESTAMP '2025-08-31 00:00:00'
   AND t.created_at < TIMESTAMP '2026-09-01 00:00:00'
), jd AS (
 SELECT pegawai_id,dept_snapshot,jadwal_id,hari_kalender_proksi,
        BOOL_OR(jadwal_lintas_hari) AS night_shift,
        COUNT(*) FILTER (WHERE checktype=1) AS n_checkin,
        COUNT(*) FILTER (WHERE checktype=2) AS n_checkout,
        COUNT(*) FILTER (WHERE checktype=2 AND jam_event<=jam_keluar) AS n_checkout_sesuai_rentang_jam_awal
 FROM ev
 GROUP BY pegawai_id,dept_snapshot,jadwal_id,hari_kalender_proksi
), candidates AS (
 SELECT cur.pegawai_id,cur.dept_snapshot,cur.hari_kalender_proksi,
        cur.jadwal_id,cur.n_checkout,cur.n_checkout_sesuai_rentang_jam_awal,
        COALESCE(prev.n_checkin,0) AS prev_day_in
 FROM jd cur LEFT JOIN jd prev
   ON prev.pegawai_id=cur.pegawai_id
  AND prev.jadwal_id IS NOT DISTINCT FROM cur.jadwal_id
  AND prev.hari_kalender_proksi=cur.hari_kalender_proksi-1
 WHERE cur.hari_kalender_proksi BETWEEN DATE '2025-09-01' AND DATE '2026-08-31'
   AND cur.night_shift IS TRUE
   AND cur.n_checkout>0 AND cur.n_checkin=0
), summary AS (
 SELECT COUNT(*) AS total_pegawai_jadwal_hari,
        COUNT(DISTINCT (pegawai_id,hari_kalender_proksi)) AS total_pegawai_hari,
        COUNT(DISTINCT dept_snapshot) AS total_dept,
        COALESCE(SUM(n_checkout),0)::bigint AS total_event_checkout,
        COUNT(*) FILTER (WHERE prev_day_in=0) AS tanpa_masuk_kemarin,
        COUNT(DISTINCT (pegawai_id,hari_kalender_proksi)) FILTER (WHERE prev_day_in=0) AS day_tanpa_masuk_kemarin,
        COUNT(DISTINCT dept_snapshot) FILTER (WHERE prev_day_in=0) AS dept_tanpa_masuk_kemarin,
        COUNT(*) FILTER (WHERE prev_day_in=1) AS satu_masuk_kemarin,
        COUNT(DISTINCT (pegawai_id,hari_kalender_proksi)) FILTER (WHERE prev_day_in=1) AS day_satu_masuk_kemarin,
        COUNT(DISTINCT dept_snapshot) FILTER (WHERE prev_day_in=1) AS dept_satu_masuk_kemarin,
        COUNT(*) FILTER (WHERE prev_day_in>1) AS multi_masuk_kemarin,
        COUNT(DISTINCT (pegawai_id,hari_kalender_proksi)) FILTER (WHERE prev_day_in>1) AS day_multi_masuk_kemarin,
        COUNT(DISTINCT dept_snapshot) FILTER (WHERE prev_day_in>1) AS dept_multi_masuk_kemarin,
        COUNT(*) FILTER (WHERE n_checkout_sesuai_rentang_jam_awal>0) AS cocok_jam_awal,
        COUNT(DISTINCT (pegawai_id,hari_kalender_proksi)) FILTER (WHERE n_checkout_sesuai_rentang_jam_awal>0) AS day_cocok_jam_awal,
        COUNT(DISTINCT dept_snapshot) FILTER (WHERE n_checkout_sesuai_rentang_jam_awal>0) AS dept_cocok_jam_awal
 FROM candidates
)
SELECT 'A9' AS test_id,v.metrik,
 CASE WHEN v.jadwal_days BETWEEN 1 AND 4 THEN '<5' ELSE v.jadwal_days::text END AS pegawai_jadwal_hari_kandidat,
 CASE WHEN v.days BETWEEN 1 AND 4 THEN '<5' ELSE v.days::text END AS pegawai_hari_kandidat,
 CASE WHEN v.depts BETWEEN 1 AND 4 THEN '<5' ELSE v.depts::text END AS departemen_snapshot_kandidat,
 s.total_pegawai_jadwal_hari AS denominator_kandidat_pegawai_jadwal_hari,
 s.total_event_checkout AS event_checkout_dalam_seluruh_kandidat
FROM summary s CROSS JOIN LATERAL (VALUES
 ('checkout_only_lintas_hari_seluruh_kandidat',s.total_pegawai_jadwal_hari,s.total_pegawai_hari,s.total_dept),
 ('tanpa_checkin_jadwal_sama_di_D_minus_1',s.tanpa_masuk_kemarin,s.day_tanpa_masuk_kemarin,s.dept_tanpa_masuk_kemarin),
 ('tepat_1_checkin_jadwal_sama_di_D_minus_1',s.satu_masuk_kemarin,s.day_satu_masuk_kemarin,s.dept_satu_masuk_kemarin),
 ('lebih_1_checkin_jadwal_sama_di_D_minus_1',s.multi_masuk_kemarin,s.day_multi_masuk_kemarin,s.dept_multi_masuk_kemarin),
 ('checkout_pada_00_sampai_jam_keluar_rencana',s.cocok_jam_awal,s.day_cocok_jam_awal,s.dept_cocok_jam_awal)
) v(metrik,jadwal_days,days,depts);

COMMIT;
