-- Backfill transaksi ke Curated untuk satu rentang batch.
--
-- Wajib dipanggil melalui psql dengan:
--   -v batch_id=BF_2024_Q1_M01
--   -v start_date=2024-01-01
--   -v end_date=2024-02-01
--
-- Tidak mengisi curated.cur_employee_workday. Master historis tidak tersedia,
-- maka kolom kewajiban kerja dan KPI turunan sengaja bernilai NULL/review.

BEGIN;

CREATE TEMP TABLE backfill_scope (
  batch_id text NOT NULL,
  tanggal_mulai date NOT NULL,
  tanggal_selesai date NOT NULL,
  CHECK (tanggal_selesai > tanggal_mulai)
) ON COMMIT DROP;

INSERT INTO backfill_scope VALUES
  (:'batch_id', (:'start_date')::date, (:'end_date')::date);

-- Idempoten pada cakupan batch saja; tidak menyentuh periode lain.
DELETE FROM curated.cur_attendance_regular_daily d
USING backfill_scope s
WHERE d.tanggal >= s.tanggal_mulai AND d.tanggal < s.tanggal_selesai;

DELETE FROM curated.cur_regular_event_daily d
USING backfill_scope s
WHERE d.tanggal_kerja >= s.tanggal_mulai AND d.tanggal_kerja < s.tanggal_selesai;

DELETE FROM curated.cur_nonregular_event_daily d
USING backfill_scope s
WHERE d.tanggal_kerja >= s.tanggal_mulai AND d.tanggal_kerja < s.tanggal_selesai;

DELETE FROM curated.cur_leave_daily d
USING backfill_scope s
WHERE d.tanggal_izin >= s.tanggal_mulai AND d.tanggal_izin < s.tanggal_selesai;

DELETE FROM curated.cur_event_attendance d
USING backfill_scope s
WHERE d.tanggal_event >= s.tanggal_mulai AND d.tanggal_event < s.tanggal_selesai;

INSERT INTO curated.cur_event_attendance (
  checkinout_id_sumber, pegawai_id, tanggal_event, waktu_event, checktype,
  departemen_id_event, jadwal_id_sumber, work_code_sumber, jam_masuk_sumber,
  jam_keluar_sumber, is_manual, is_wfh_sumber, event_updated_at,
  shift_id_sumber, nama_shift_snapshot, is_regular_shift, is_nonregular_shift,
  event_type, is_valid_event_type, perlu_review, alasan_review,
  source_snapshot_at
)
SELECT
  c.id,
  c.pegawai_id,
  c.created_at::date,
  c.created_at,
  c.checktype,
  c.departemen,
  c.jadwal_id,
  c.work_code,
  c.jam_masuk,
  c.jam_keluar,
  c.is_manual,
  c.is_wfh,
  c.updated_at,
  j.jenis,
  sh.nama,
  CASE WHEN sh.id IS NOT NULL THEN sh.nama ~* '(regular|reguler)' END,
  CASE WHEN sh.id IS NOT NULL THEN NOT (sh.nama ~* '(regular|reguler)') END,
  CASE c.checktype WHEN 1 THEN 'MASUK' WHEN 2 THEN 'PULANG' ELSE 'LAIN' END,
  c.checktype IN (1, 2),
  c.created_at IS NULL
    OR c.pegawai_id IS NULL
    OR c.jadwal_id IS NULL
    OR j.id IS NULL
    OR sh.id IS NULL
    OR (c.work_code IS NOT NULL AND j.jenis IS NOT NULL AND c.work_code <> j.jenis),
  concat_ws(';',
    CASE WHEN c.created_at IS NULL THEN 'WAKTU_EVENT_KOSONG' END,
    CASE WHEN c.pegawai_id IS NULL THEN 'PEGAWAI_KOSONG' END,
    CASE WHEN c.jadwal_id IS NULL OR j.id IS NULL THEN 'JADWAL_TIDAK_DITEMUKAN_PADA_SNAPSHOT' END,
    CASE WHEN j.id IS NOT NULL AND sh.id IS NULL THEN 'SHIFT_TIDAK_DITEMUKAN_PADA_SNAPSHOT' END,
    CASE WHEN c.work_code IS NOT NULL AND j.jenis IS NOT NULL AND c.work_code <> j.jenis THEN 'WORK_CODE_TIDAK_COCOK_DENGAN_SHIFT_JADWAL' END
  ),
  c.extracted_at
FROM raw.raw_checkinout c
CROSS JOIN backfill_scope sc
LEFT JOIN raw.raw_jadwal j ON j.id = c.jadwal_id
LEFT JOIN raw.raw_shift sh ON sh.id = j.jenis
WHERE c.created_at >= sc.tanggal_mulai
  AND c.created_at < sc.tanggal_selesai;

INSERT INTO curated.cur_regular_event_daily (
  pegawai_id, tanggal_kerja, departemen_id_event, has_masuk, has_pulang,
  checkin_event_count, checkout_event_count, first_checkin_at, last_checkout_at,
  has_manual_event, regular_schedule_count, is_complete_attendance,
  perlu_review, alasan_review, source_snapshot_at
)
SELECT
  pegawai_id,
  tanggal_event,
  CASE WHEN count(DISTINCT departemen_id_event) FILTER (WHERE departemen_id_event IS NOT NULL) <= 1
       THEN min(departemen_id_event) END,
  bool_or(event_type = 'MASUK'),
  bool_or(event_type = 'PULANG'),
  count(*) FILTER (WHERE event_type = 'MASUK'),
  count(*) FILTER (WHERE event_type = 'PULANG'),
  min(waktu_event) FILTER (WHERE event_type = 'MASUK'),
  max(waktu_event) FILTER (WHERE event_type = 'PULANG'),
  bool_or(coalesce(is_manual, false)),
  count(DISTINCT jadwal_id_sumber) FILTER (WHERE jadwal_id_sumber IS NOT NULL),
  bool_or(event_type = 'MASUK') AND bool_or(event_type = 'PULANG'),
  bool_or(perlu_review)
    OR count(DISTINCT departemen_id_event) FILTER (WHERE departemen_id_event IS NOT NULL) > 1
    OR count(DISTINCT jadwal_id_sumber) FILTER (WHERE jadwal_id_sumber IS NOT NULL) > 1,
  concat_ws(';',
    string_agg(DISTINCT nullif(alasan_review, ''), ';') FILTER (WHERE alasan_review IS NOT NULL),
    CASE WHEN count(DISTINCT departemen_id_event) FILTER (WHERE departemen_id_event IS NOT NULL) > 1 THEN 'DEPARTEMEN_EVENT_AMBIGU' END,
    CASE WHEN count(DISTINCT jadwal_id_sumber) FILTER (WHERE jadwal_id_sumber IS NOT NULL) > 1 THEN 'JADWAL_REGULAR_AMBIGU' END
  ),
  max(source_snapshot_at)
FROM curated.cur_event_attendance e
CROSS JOIN backfill_scope sc
WHERE e.is_regular_shift IS TRUE
  AND e.is_valid_event_type IS TRUE
  AND e.tanggal_event >= sc.tanggal_mulai
  AND e.tanggal_event < sc.tanggal_selesai
GROUP BY pegawai_id, tanggal_event;

INSERT INTO curated.cur_nonregular_event_daily (
  pegawai_id, tanggal_kerja, jadwal_id_sumber, shift_id_sumber,
  departemen_id_event, has_masuk, has_pulang, checkin_event_count,
  checkout_event_count, first_checkin_at, last_checkout_at, has_manual_event,
  mode_kerja_event, is_complete_attendance, perlu_review, alasan_review,
  source_snapshot_at
)
SELECT
  pegawai_id,
  tanggal_event,
  jadwal_id_sumber,
  min(shift_id_sumber),
  CASE WHEN count(DISTINCT departemen_id_event) FILTER (WHERE departemen_id_event IS NOT NULL) <= 1
       THEN min(departemen_id_event) END,
  bool_or(event_type = 'MASUK'),
  bool_or(event_type = 'PULANG'),
  count(*) FILTER (WHERE event_type = 'MASUK'),
  count(*) FILTER (WHERE event_type = 'PULANG'),
  min(waktu_event) FILTER (WHERE event_type = 'MASUK'),
  max(waktu_event) FILTER (WHERE event_type = 'PULANG'),
  bool_or(coalesce(is_manual, false)),
  CASE WHEN count(DISTINCT is_wfh_sumber) FILTER (WHERE is_wfh_sumber IS NOT NULL) <= 1
       THEN min(is_wfh_sumber) END,
  bool_or(event_type = 'MASUK') AND bool_or(event_type = 'PULANG'),
  bool_or(perlu_review)
    OR count(DISTINCT departemen_id_event) FILTER (WHERE departemen_id_event IS NOT NULL) > 1
    OR count(DISTINCT is_wfh_sumber) FILTER (WHERE is_wfh_sumber IS NOT NULL) > 1,
  concat_ws(';',
    string_agg(DISTINCT nullif(alasan_review, ''), ';') FILTER (WHERE alasan_review IS NOT NULL),
    CASE WHEN count(DISTINCT departemen_id_event) FILTER (WHERE departemen_id_event IS NOT NULL) > 1 THEN 'DEPARTEMEN_EVENT_AMBIGU' END,
    CASE WHEN count(DISTINCT is_wfh_sumber) FILTER (WHERE is_wfh_sumber IS NOT NULL) > 1 THEN 'MODE_KERJA_EVENT_AMBIGU' END
  ),
  max(source_snapshot_at)
FROM curated.cur_event_attendance e
CROSS JOIN backfill_scope sc
WHERE e.is_nonregular_shift IS TRUE
  AND e.is_valid_event_type IS TRUE
  AND e.jadwal_id_sumber IS NOT NULL
  AND e.tanggal_event >= sc.tanggal_mulai
  AND e.tanggal_event < sc.tanggal_selesai
GROUP BY pegawai_id, tanggal_event, jadwal_id_sumber;

INSERT INTO curated.cur_leave_daily (
  perizinan_id_sumber, pegawai_id, tanggal_izin, departemen_id_izin,
  jenis_izin_id_sumber, nama_jenis_izin, tipe_izin_id_sumber, nama_tipe_izin,
  approval, approval_at, is_full_day_leave, is_partial_day_leave,
  is_valid_leave, perlu_review, alasan_review, source_updated_at,
  source_snapshot_at
)
SELECT
  p.id,
  p.pegawai_id,
  d.tanggal_izin,
  p.departemen,
  p.jenis_ijin,
  ji.nama,
  ji.tipe_id,
  ti.nama,
  p.approval,
  p.approval_at,
  CASE WHEN ji.id IS NOT NULL THEN NOT ji.setengah_hari END,
  CASE WHEN ji.id IS NOT NULL THEN ji.setengah_hari END,
  p.approval IS TRUE
    AND p.pegawai_id IS NOT NULL
    AND p.tgl_ijin IS NOT NULL
    AND coalesce(p.tgl_ijin_sampai, p.tgl_ijin) >= p.tgl_ijin
    AND ji.id IS NOT NULL
    AND (p.user_id IS NULL OR (u.id IS NOT NULL AND u.pegawai_id = p.pegawai_id)),
  p.pegawai_id IS NULL
    OR p.tgl_ijin IS NULL
    OR coalesce(p.tgl_ijin_sampai, p.tgl_ijin) < p.tgl_ijin
    OR ji.id IS NULL
    OR (p.user_id IS NOT NULL AND (u.id IS NULL OR u.pegawai_id IS DISTINCT FROM p.pegawai_id)),
  concat_ws(';',
    CASE WHEN p.pegawai_id IS NULL THEN 'PEGAWAI_KOSONG' END,
    CASE WHEN p.tgl_ijin IS NULL OR coalesce(p.tgl_ijin_sampai, p.tgl_ijin) < p.tgl_ijin THEN 'RENTANG_IZIN_TIDAK_VALID' END,
    CASE WHEN ji.id IS NULL THEN 'JENIS_IZIN_TIDAK_DITEMUKAN' END,
    CASE WHEN p.user_id IS NOT NULL AND (u.id IS NULL OR u.pegawai_id IS DISTINCT FROM p.pegawai_id) THEN 'IDENTITAS_USER_PEGAWAI_TIDAK_COCOK' END
  ),
  p.updated_at,
  p.extracted_at
FROM raw.raw_perizinan p
CROSS JOIN backfill_scope sc
CROSS JOIN LATERAL generate_series(
  p.tgl_ijin,
  coalesce(p.tgl_ijin_sampai, p.tgl_ijin),
  interval '1 day'
) d(tanggal_izin)
LEFT JOIN raw.raw_user u ON u.id = p.user_id
LEFT JOIN raw.raw_jenis_ijin ji ON ji.id = p.jenis_ijin
LEFT JOIN raw.raw_tipe_ijin ti ON ti.id = ji.tipe_id
WHERE p.tgl_ijin IS NOT NULL
  AND coalesce(p.tgl_ijin_sampai, p.tgl_ijin) >= p.tgl_ijin
  AND d.tanggal_izin >= sc.tanggal_mulai
  AND d.tanggal_izin < sc.tanggal_selesai;

WITH event_daily AS (
  SELECT *
  FROM curated.cur_regular_event_daily e
  CROSS JOIN backfill_scope sc
  WHERE e.tanggal_kerja >= sc.tanggal_mulai AND e.tanggal_kerja < sc.tanggal_selesai
), leave_daily AS (
  SELECT
    pegawai_id,
    tanggal_izin,
    bool_or(is_valid_leave AND is_full_day_leave) AS has_full_day_leave,
    bool_or(is_valid_leave AND is_partial_day_leave) AS has_partial_day_leave,
    bool_or(perlu_review) AS perlu_review,
    string_agg(DISTINCT nullif(alasan_review, ''), ';') FILTER (WHERE alasan_review IS NOT NULL) AS alasan_review,
    max(source_snapshot_at) AS source_snapshot_at
  FROM curated.cur_leave_daily l
  CROSS JOIN backfill_scope sc
  WHERE l.tanggal_izin >= sc.tanggal_mulai AND l.tanggal_izin < sc.tanggal_selesai
  GROUP BY pegawai_id, tanggal_izin
)
INSERT INTO curated.cur_attendance_regular_daily (
  pegawai_id, tanggal, departemen_id, is_employee_active, has_regular_schedule,
  is_day_off, is_expected_workday, has_masuk, has_pulang, checkin_event_count,
  checkout_event_count, first_checkin_at, last_checkout_at, has_manual_event,
  has_full_day_leave, has_partial_day_leave, selected_leave_coverage,
  is_complete_attendance, status_kehadiran, is_late, late_minutes,
  late_schedule_id_sumber, scheduled_regular_days, checkin_days, checkout_days,
  complete_attendance_days, leave_days, perlu_review, alasan_review,
  source_snapshot_at
)
SELECT
  coalesce(e.pegawai_id, l.pegawai_id),
  coalesce(e.tanggal_kerja, l.tanggal_izin),
  e.departemen_id_event,
  NULL, NULL, NULL, NULL,
  coalesce(e.has_masuk, false),
  coalesce(e.has_pulang, false),
  coalesce(e.checkin_event_count, 0),
  coalesce(e.checkout_event_count, 0),
  e.first_checkin_at,
  e.last_checkout_at,
  coalesce(e.has_manual_event, false),
  coalesce(l.has_full_day_leave, false),
  coalesce(l.has_partial_day_leave, false),
  CASE WHEN coalesce(l.has_full_day_leave, false) THEN 'FULL'
       WHEN coalesce(l.has_partial_day_leave, false) THEN 'PARTIAL'
       ELSE 'NONE' END,
  coalesce(e.is_complete_attendance, false),
  CASE WHEN coalesce(l.has_full_day_leave, false) THEN 'IZIN'
       WHEN coalesce(e.has_masuk, false) AND coalesce(e.has_pulang, false) THEN 'HADIR_LENGKAP'
       WHEN coalesce(e.has_masuk, false) THEN 'CHECKIN_BELUM_PULANG'
       ELSE NULL END,
  NULL, NULL, NULL,
  NULL,
  CASE WHEN e.has_masuk THEN 1 ELSE 0 END,
  CASE WHEN e.has_pulang THEN 1 ELSE 0 END,
  CASE WHEN e.is_complete_attendance THEN 1 ELSE 0 END,
  CASE WHEN l.has_full_day_leave THEN 1 ELSE 0 END,
  true,
  concat_ws(';',
    'KEWAJIBAN_KERJA_HISTORIS_TIDAK_TERSEDIA',
    e.alasan_review,
    l.alasan_review
  ),
  greatest(e.source_snapshot_at, l.source_snapshot_at)
FROM event_daily e
FULL OUTER JOIN leave_daily l
  ON l.pegawai_id = e.pegawai_id AND l.tanggal_izin = e.tanggal_kerja;

COMMIT;
