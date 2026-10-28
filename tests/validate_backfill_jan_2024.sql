-- Rekonsiliasi setelah menjalankan backfill_jan_2024.sql.
SELECT 'cur_event_attendance' AS objek, count(*) AS baris,
       min(tanggal_event) AS tanggal_min, max(tanggal_event) AS tanggal_max,
       count(*) FILTER (WHERE perlu_review) AS perlu_review
FROM curated.cur_event_attendance
WHERE tanggal_event >= date '2024-01-01' AND tanggal_event < date '2024-02-01'
UNION ALL
SELECT 'cur_regular_event_daily', count(*), min(tanggal_kerja), max(tanggal_kerja), count(*) FILTER (WHERE perlu_review)
FROM curated.cur_regular_event_daily
WHERE tanggal_kerja >= date '2024-01-01' AND tanggal_kerja < date '2024-02-01'
UNION ALL
SELECT 'cur_nonregular_event_daily', count(*), min(tanggal_kerja), max(tanggal_kerja), count(*) FILTER (WHERE perlu_review)
FROM curated.cur_nonregular_event_daily
WHERE tanggal_kerja >= date '2024-01-01' AND tanggal_kerja < date '2024-02-01'
UNION ALL
SELECT 'cur_leave_daily', count(*), min(tanggal_izin), max(tanggal_izin), count(*) FILTER (WHERE perlu_review)
FROM curated.cur_leave_daily
WHERE tanggal_izin >= date '2024-01-01' AND tanggal_izin < date '2024-02-01'
UNION ALL
SELECT 'cur_attendance_regular_daily', count(*), min(tanggal), max(tanggal), count(*) FILTER (WHERE perlu_review)
FROM curated.cur_attendance_regular_daily
WHERE tanggal >= date '2024-01-01' AND tanggal < date '2024-02-01';

SELECT
  count(*) AS employee_workday_januari,
  count(*) FILTER (WHERE is_expected_workday IS TRUE) AS expected_workday_terisi
FROM curated.cur_employee_workday
WHERE tanggal >= date '2024-01-01' AND tanggal < date '2024-02-01';

SELECT
  count(*) AS daily_dengan_kewajiban_terisi,
  count(*) FILTER (WHERE scheduled_regular_days IS NOT NULL) AS scheduled_days_terisi
FROM curated.cur_attendance_regular_daily
WHERE tanggal >= date '2024-01-01' AND tanggal < date '2024-02-01';

-- Rekonsiliasi KPI harian terhadap Raw sumber.  Status m_shift sengaja tidak
-- dipakai sebagai filter; klasifikasi berasal dari jadwal transaksi → nama shift.
WITH source_event AS MATERIALIZED (
  SELECT
    c.id,
    c.pegawai_id,
    c.created_at::date AS tanggal,
    c.checktype,
    c.jadwal_id,
    CASE WHEN sh.id IS NOT NULL THEN sh.nama ~* '(regular|reguler)' END AS is_regular,
    CASE WHEN sh.id IS NOT NULL THEN NOT (sh.nama ~* '(regular|reguler)') END AS is_nonregular
  FROM raw.raw_checkinout c
  LEFT JOIN raw.raw_jadwal j ON j.id = c.jadwal_id
  LEFT JOIN raw.raw_shift sh ON sh.id = j.jenis
  WHERE c.id >= 81901693 AND c.id < 84621693
    AND c.created_at >= timestamp '2024-01-01'
    AND c.created_at < timestamp '2024-02-01'
), source_regular_employee_day AS (
  SELECT pegawai_id, tanggal,
         bool_or(checktype = 1) AS has_masuk,
         bool_or(checktype = 2) AS has_pulang
  FROM source_event
  WHERE is_regular IS TRUE AND checktype IN (1, 2)
  GROUP BY pegawai_id, tanggal
), source_nonregular_employee_day AS (
  SELECT pegawai_id, tanggal, jadwal_id,
         bool_or(checktype = 1) AS has_masuk,
         bool_or(checktype = 2) AS has_pulang
  FROM source_event
  WHERE is_nonregular IS TRUE AND checktype IN (1, 2)
  GROUP BY pegawai_id, tanggal, jadwal_id
), source_leave_employee_day AS (
  SELECT p.pegawai_id, d.tanggal_izin::date AS tanggal
  FROM raw.raw_perizinan p
  CROSS JOIN LATERAL generate_series(
    p.tgl_ijin, coalesce(p.tgl_ijin_sampai, p.tgl_ijin), interval '1 day'
  ) d(tanggal_izin)
  LEFT JOIN raw.raw_user u ON u.id = p.user_id
  LEFT JOIN raw.raw_jenis_ijin ji ON ji.id = p.jenis_ijin
  WHERE p.approval IS TRUE
    AND p.pegawai_id IS NOT NULL
    AND p.tgl_ijin IS NOT NULL
    AND coalesce(p.tgl_ijin_sampai, p.tgl_ijin) >= p.tgl_ijin
    AND ji.id IS NOT NULL
    AND ji.setengah_hari IS FALSE
    AND (p.user_id IS NULL OR (u.id IS NOT NULL AND u.pegawai_id = p.pegawai_id))
    AND d.tanggal_izin >= date '2024-01-01'
    AND d.tanggal_izin < date '2024-02-01'
), source_event_daily AS (
  SELECT tanggal, count(*) AS source_event FROM source_event GROUP BY tanggal
), source_regular_daily AS (
  SELECT tanggal,
         count(*) FILTER (WHERE has_masuk) AS source_checkin_reguler,
         count(*) FILTER (WHERE has_pulang) AS source_checkout_reguler,
         count(*) FILTER (WHERE has_masuk AND has_pulang) AS source_lengkap_reguler,
         count(*) FILTER (WHERE has_masuk AND NOT has_pulang) AS source_belum_pulang
  FROM source_regular_employee_day GROUP BY tanggal
), source_nonregular_daily AS (
  SELECT tanggal,
         count(DISTINCT pegawai_id) FILTER (WHERE has_masuk) AS source_checkin_nonreguler,
         count(DISTINCT pegawai_id) FILTER (WHERE has_pulang) AS source_checkout_nonreguler,
         count(DISTINCT pegawai_id) FILTER (WHERE has_masuk AND has_pulang) AS source_lengkap_nonreguler
  FROM source_nonregular_employee_day GROUP BY tanggal
), source_leave_daily AS (
  SELECT tanggal, count(*) AS source_izin
  FROM (SELECT DISTINCT pegawai_id, tanggal FROM source_leave_employee_day) d
  GROUP BY tanggal
), curated_daily AS (
  SELECT tanggal,
         count(*) FILTER (WHERE has_masuk) AS curated_checkin_reguler,
         count(*) FILTER (WHERE has_pulang) AS curated_checkout_reguler,
         count(*) FILTER (WHERE is_complete_attendance) AS curated_lengkap_reguler,
         count(*) FILTER (WHERE has_masuk AND NOT has_pulang) AS curated_belum_pulang,
         coalesce(sum(leave_days), 0) AS curated_izin
  FROM curated.cur_attendance_regular_daily
  WHERE tanggal >= date '2024-01-01' AND tanggal < date '2024-02-01'
  GROUP BY tanggal
), curated_event_daily AS (
  SELECT tanggal_event AS tanggal, count(*) AS curated_event
  FROM curated.cur_event_attendance
  WHERE tanggal_event >= date '2024-01-01' AND tanggal_event < date '2024-02-01'
  GROUP BY tanggal_event
), curated_nonregular_daily AS (
  SELECT tanggal_kerja AS tanggal,
         count(DISTINCT pegawai_id) FILTER (WHERE has_masuk) AS curated_checkin_nonreguler,
         count(DISTINCT pegawai_id) FILTER (WHERE has_pulang) AS curated_checkout_nonreguler,
         count(DISTINCT pegawai_id) FILTER (WHERE is_complete_attendance) AS curated_lengkap_nonreguler
  FROM curated.cur_nonregular_event_daily
  WHERE tanggal_kerja >= date '2024-01-01' AND tanggal_kerja < date '2024-02-01'
  GROUP BY tanggal_kerja
)
SELECT d.tanggal,
       coalesce(se.source_event, 0) AS source_event,
       coalesce(ce.curated_event, 0) AS curated_event,
       coalesce(sr.source_checkin_reguler, 0) AS source_checkin_reguler,
       coalesce(cd.curated_checkin_reguler, 0) AS curated_checkin_reguler,
       coalesce(sr.source_checkout_reguler, 0) AS source_checkout_reguler,
       coalesce(cd.curated_checkout_reguler, 0) AS curated_checkout_reguler,
       coalesce(sr.source_lengkap_reguler, 0) AS source_lengkap_reguler,
       coalesce(cd.curated_lengkap_reguler, 0) AS curated_lengkap_reguler,
       coalesce(sr.source_belum_pulang, 0) AS source_belum_pulang,
       coalesce(cd.curated_belum_pulang, 0) AS curated_belum_pulang,
       coalesce(sl.source_izin, 0) AS source_izin,
       coalesce(cd.curated_izin, 0) AS curated_izin,
       coalesce(sn.source_checkin_nonreguler, 0) AS source_checkin_nonreguler,
       coalesce(cn.curated_checkin_nonreguler, 0) AS curated_checkin_nonreguler,
       coalesce(sn.source_checkout_nonreguler, 0) AS source_checkout_nonreguler,
       coalesce(cn.curated_checkout_nonreguler, 0) AS curated_checkout_nonreguler,
       coalesce(sn.source_lengkap_nonreguler, 0) AS source_lengkap_nonreguler,
       coalesce(cn.curated_lengkap_nonreguler, 0) AS curated_lengkap_nonreguler,
       (coalesce(se.source_event, 0) = coalesce(ce.curated_event, 0)
        AND coalesce(sr.source_checkin_reguler, 0) = coalesce(cd.curated_checkin_reguler, 0)
        AND coalesce(sr.source_checkout_reguler, 0) = coalesce(cd.curated_checkout_reguler, 0)
        AND coalesce(sr.source_lengkap_reguler, 0) = coalesce(cd.curated_lengkap_reguler, 0)
        AND coalesce(sr.source_belum_pulang, 0) = coalesce(cd.curated_belum_pulang, 0)
        AND coalesce(sl.source_izin, 0) = coalesce(cd.curated_izin, 0)
        AND coalesce(sn.source_checkin_nonreguler, 0) = coalesce(cn.curated_checkin_nonreguler, 0)
        AND coalesce(sn.source_checkout_nonreguler, 0) = coalesce(cn.curated_checkout_nonreguler, 0)
        AND coalesce(sn.source_lengkap_nonreguler, 0) = coalesce(cn.curated_lengkap_nonreguler, 0)) AS seluruh_metrik_cocok
FROM generate_series(date '2024-01-01', date '2024-01-31', interval '1 day') d(tanggal)
LEFT JOIN source_event_daily se USING (tanggal)
LEFT JOIN source_regular_daily sr USING (tanggal)
LEFT JOIN source_nonregular_daily sn USING (tanggal)
LEFT JOIN source_leave_daily sl USING (tanggal)
LEFT JOIN curated_daily cd USING (tanggal)
LEFT JOIN curated_event_daily ce USING (tanggal)
LEFT JOIN curated_nonregular_daily cn USING (tanggal)
ORDER BY d.tanggal;
