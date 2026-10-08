WITH combined AS (
 SELECT j.id AS jadwal_id_sumber, j.jenis AS shift_id_sumber,
 s.nama AS nama_shift, s.departemen_id AS departemen_id_sumber,
 s.status AS is_aktif_saat_ini, s.nama ~* 'regular|reguler' AS is_reguler,
 s.is_flexible AS is_flexible_kode_sumber,
 CASE s.is_flexible WHEN 0 THEN false WHEN 1 THEN true ELSE NULL END AS is_flexible,
 s.event_id AS event_id_sumber, s.created_at AS shift_source_created_at,
 j.created_at AS jadwal_source_created_at, j.hari AS hari_sumber,
 CASE lower(btrim(j.hari))
  WHEN 'mon' THEN 1 WHEN 'monday' THEN 1 WHEN 'senin' THEN 1
  WHEN 'tue' THEN 2 WHEN 'tuesday' THEN 2 WHEN 'selasa' THEN 2
  WHEN 'wed' THEN 3 WHEN 'wednesday' THEN 3 WHEN 'rabu' THEN 3
  WHEN 'thu' THEN 4 WHEN 'thursday' THEN 4 WHEN 'kamis' THEN 4
  WHEN 'fri' THEN 5 WHEN 'friday' THEN 5 WHEN 'jumat' THEN 5
  WHEN 'sat' THEN 6 WHEN 'saturday' THEN 6 WHEN 'sabtu' THEN 6
  WHEN 'sun' THEN 7 WHEN 'sunday' THEN 7 WHEN 'minggu' THEN 7
 END AS hari_iso,
 j.jam_masuk, j.jam_keluar, j.jam_masuk_awal, j.jam_keluar_akhir,
 j.flexible_time AS flexible_time_sumber,
 j.jam_keluar < j.jam_masuk AS indikasi_lintas_tengah_malam,
 j.jam_keluar = j.jam_masuk AS is_jam_sama
 FROM public.m_jadwal j LEFT JOIN public.m_shift s ON s.id=j.jenis
)
SELECT *, (ARRAY['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu'])[hari_iso] AS hari
FROM combined ORDER BY jadwal_id_sumber
