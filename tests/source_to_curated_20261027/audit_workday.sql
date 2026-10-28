-- Jalankan pada staging_bkd_test_20261027. Read-only.
-- Semua angka berdasarkan snapshot dump tanggal bisnis 2026-10-27.
BEGIN READ ONLY;

-- 1. Rekonsiliasi populasi lengkap.
SELECT is_employee_active,has_regular_schedule,is_day_off,is_expected_workday,count(*) AS pegawai
FROM curated.cur_employee_workday
WHERE tanggal=date '2026-10-27'
GROUP BY 1,2,3,4 ORDER BY 1,2,3;

-- 2. Penyebab pegawai aktif tidak memperoleh jadwal reguler.
WITH shifts AS (
 SELECT departemen_id,
 bool_or(nama ~* '(regular|reguler)') AS any_regular,
 bool_or(status IS TRUE AND nama ~* '(regular|reguler)') AS active_regular
 FROM raw.raw_shift GROUP BY departemen_id
)
SELECT CASE
 WHEN w.departemen_id IS NULL THEN 'DEPARTEMEN_KOSONG'
 WHEN s.departemen_id IS NULL THEN 'DEPARTEMEN_TANPA_SHIFT'
 WHEN NOT s.any_regular THEN 'TIDAK_ADA_NAMA_REGULAR_REGULER'
 WHEN NOT s.active_regular THEN 'REGULAR_REGULER_HANYA_NONAKTIF'
 ELSE 'REGULAR_AKTIF_TANPA_JADWAL_SELASA' END AS alasan,
 count(*) AS pegawai
FROM curated.cur_employee_workday w
LEFT JOIN shifts s ON s.departemen_id=w.departemen_id
WHERE w.tanggal=date '2026-10-27' AND w.is_employee_active AND NOT w.has_regular_schedule
GROUP BY 1 ORDER BY 2 DESC;

-- 3. Departemen dengan populasi aktif yang tidak memperoleh jadwal terbesar.
SELECT w.departemen_id,d.nama_departemen,d.parent,count(*) AS pegawai_aktif_tanpa_jadwal
FROM curated.cur_employee_workday w
LEFT JOIN raw.raw_departemen d ON d.id=w.departemen_id
WHERE w.tanggal=date '2026-10-27' AND w.is_employee_active AND NOT w.has_regular_schedule
GROUP BY 1,2,3 ORDER BY 4 DESC LIMIT 30;

-- 4. Alternatif shift aktif yang dikecualikan oleh nama; bukan rekomendasi otomatis
--    untuk menganggapnya wajib/reguler. Pegawai dapat muncul pada beberapa nama.
SELECT s.nama,count(DISTINCT w.pegawai_id) AS pegawai_aktif,
 count(DISTINCT s.departemen_id) AS departemen
FROM curated.cur_employee_workday w
JOIN raw.raw_shift s ON s.departemen_id=w.departemen_id AND s.status
JOIN raw.raw_jadwal j ON j.jenis=s.id AND j.hari='Tue'
WHERE w.tanggal=date '2026-10-27' AND w.is_employee_active AND NOT w.has_regular_schedule
GROUP BY s.nama ORDER BY 2 DESC LIMIT 30;

-- 5. Sampel detail workday. Tambahkan filter pegawai/departemen untuk investigasi.
SELECT w.*,d.nama_departemen,p.status AS kategori_pegawai_id,v.previleges AS kategori_pegawai
FROM curated.cur_employee_workday w
JOIN raw.raw_pegawai p ON p.id=w.pegawai_id
LEFT JOIN raw.raw_previleges v ON v.id=p.status
LEFT JOIN raw.raw_departemen d ON d.id=w.departemen_id
WHERE w.tanggal=date '2026-10-27'
ORDER BY w.pegawai_id LIMIT 100;

COMMIT;
