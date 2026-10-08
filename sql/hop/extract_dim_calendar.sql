WITH bounds AS (
 SELECT '${START_DATE}'::date AS start_date, '${END_DATE}'::date AS end_date
), dates AS (
 SELECT b.start_date + n AS tanggal
 FROM bounds b
 CROSS JOIN LATERAL generate_series(0 + 1 / CASE WHEN b.end_date >= b.start_date THEN 1 ELSE 0 END - 1,
 b.end_date - b.start_date) AS n
), holidays AS (
 SELECT tanggal, string_agg(DISTINCT keterangan, '; ' ORDER BY keterangan) AS keterangan_libur,
 array_to_string(array_agg(DISTINCT id ORDER BY id), ',') AS libur_id_sumber,
 max(created_at) AS libur_source_created_at_terakhir
 FROM public.m_hari_libur GROUP BY tanggal
)
SELECT d.tanggal,
 extract(year FROM d.tanggal)::integer AS tahun,
 extract(month FROM d.tanggal)::integer AS bulan,
 (ARRAY['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'])[extract(month FROM d.tanggal)::integer] AS nama_bulan,
 extract(day FROM d.tanggal)::integer AS hari,
 (ARRAY['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu'])[extract(isodow FROM d.tanggal)::integer] AS nama_hari,
 extract(week FROM d.tanggal)::integer AS minggu_ke,
 extract(quarter FROM d.tanggal)::integer AS kuartal,
 extract(isodow FROM d.tanggal)>=6 AS is_weekend,
 h.tanggal IS NOT NULL AS is_hari_libur,
 h.keterangan_libur,
 extract(isodow FROM d.tanggal)::integer AS hari_iso,
 extract(isoyear FROM d.tanggal)::integer AS tahun_iso,
 extract(isodow FROM d.tanggal)<=5 AS is_hari_kerja_normal,
 h.libur_id_sumber, h.libur_source_created_at_terakhir
FROM dates d LEFT JOIN holidays h ON h.tanggal=d.tanggal
ORDER BY d.tanggal
