BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '5min';
SET LOCAL work_mem = '64MB';
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
COMMIT;
