BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30min';
SET LOCAL work_mem = '64MB';
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
