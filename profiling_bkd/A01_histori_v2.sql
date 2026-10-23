-- BKD Jatim / Data Profiling Kelompok A / Query A-HIST-01 v2
-- A1, A2, A3, A4, A7 (timestamp), A10. SATU pemindaian logis t_checkinout.
-- Hanya SELECT; CTE MATERIALIZED bersifat internal (berpotensi spill ke disk), tanpa tabel sementara atau penulisan ke database. Setiap hitungan 1-4 disamarkan.
-- Sumber: dbabsen_restore, snapshot production 2026-09-01.
-- Batas snapshot memakai TANGGAL (bukan jam dump yang tidak diketahui).
-- Dua tahap: 1x baca event -> agregat komposit -> roll-up; bukti performa perlu EXPLAIN aktual.
-- Grain proksi: created_at::date belum tanggal kerja final; timezone belum terbukti.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30min';
SET LOCAL work_mem = '64MB';
SET LOCAL enable_sort = off; -- preferensi per transaksi; EXPLAIN tetap wajib dicek

WITH event_tag AS (
  SELECT
    EXTRACT(YEAR FROM t.created_at)::int AS yr,
    date_trunc('month', t.created_at)::date AS bulan,
    EXTRACT(ISODOW FROM t.created_at)::int AS isodow,
    EXTRACT(HOUR FROM t.created_at)::int AS jam,
    COALESCE(t.checktype::text, '(NULL)') AS domain_checktype,
    COALESCE(t.is_wfh::text, '(NULL)') AS domain_wfh,
    COALESCE(t.is_manual::text, '(NULL)') AS domain_manual,
    CASE
      WHEN t.is_manual IS TRUE AND t.approval_at IS NULL THEN 'manual_tanpa_approval'
      WHEN t.is_manual IS TRUE AND t.approval_at IS NOT NULL THEN 'manual_dengan_approval'
      WHEN t.is_manual IS FALSE AND t.approval_at IS NOT NULL THEN 'nonmanual_dengan_approval'
      WHEN t.is_manual IS FALSE AND t.approval_at IS NULL THEN 'nonmanual_tanpa_approval'
      WHEN t.is_manual IS NULL AND t.approval_at IS NOT NULL THEN 'manual_null_approval_ada'
      ELSE 'manual_null_approval_null'
    END AS kategori_approval,
    (t.jadwal_id IS NULL) AS jadwal_null,
    (t.jadwal_id IS NOT NULL AND j.id IS NULL) AS jadwal_orphan,
    (t.checktype IS NULL OR t.checktype NOT IN (1, 2)) AS checktype_invalid,
    (t.is_wfh IS NULL OR t.is_wfh NOT IN (0, 1)) AS wfh_unmapped,
    (t.is_manual IS NULL) AS manual_null,
    (t.is_manual IS TRUE AND t.approval_at IS NULL) AS manual_no_approval,
    (t.approval_at IS NOT NULL AND t.created_at IS NOT NULL AND t.approval_at < t.created_at) AS approval_sebelum_event,
    (t.is_manual IS FALSE AND t.approval_at IS NOT NULL) AS nonmanual_ada_approval,
    (t.created_at IS NULL) AS event_time_null,
    (t.created_at IS NOT NULL AND p.created_at IS NOT NULL AND t.created_at < p.created_at) AS event_sebelum_pegawai_dibuat,
    (t.created_at::date > DATE '2026-09-01') AS event_setelah_tanggal_snapshot,
    (t.created_at::date = DATE '2026-09-01') AS event_pada_hari_snapshot_parsial,
    (t.updated_at IS NULL) AS updated_null,
    (t.updated_at IS NOT NULL AND t.created_at IS NOT NULL AND t.updated_at <> t.created_at) AS updated_berbeda,
    (t.updated_at IS NOT NULL AND t.created_at IS NOT NULL AND t.updated_at < t.created_at) AS updated_sebelum_event,
    (t.updated_at IS NOT NULL AND t.created_at IS NOT NULL) AS updated_dapat_dibandingkan
  FROM public.t_checkinout t
  LEFT JOIN public.m_jadwal j ON j.id = t.jadwal_id
  LEFT JOIN public.m_pegawai p ON p.id = t.pegawai_id
), base_agregat AS MATERIALIZED (
  SELECT yr, bulan, isodow, jam, domain_checktype, domain_wfh,
    domain_manual, kategori_approval,
    COUNT(*) AS n,
    COUNT(*) FILTER (WHERE jadwal_null) AS n_jadwal_null,
    COUNT(*) FILTER (WHERE jadwal_orphan) AS n_jadwal_orphan,
    COUNT(*) FILTER (WHERE checktype_invalid) AS n_checktype_invalid,
    COUNT(*) FILTER (WHERE wfh_unmapped) AS n_wfh_unmapped,
    COUNT(*) FILTER (WHERE manual_null) AS n_manual_null,
    COUNT(*) FILTER (WHERE manual_no_approval) AS n_manual_no_approval,
    COUNT(*) FILTER (WHERE approval_sebelum_event) AS n_approval_sebelum_event,
    COUNT(*) FILTER (WHERE nonmanual_ada_approval) AS n_nonmanual_ada_approval,
    COUNT(*) FILTER (WHERE event_time_null) AS n_event_time_null,
    COUNT(*) FILTER (WHERE event_sebelum_pegawai_dibuat) AS n_event_sebelum_pegawai,
    COUNT(*) FILTER (WHERE event_setelah_tanggal_snapshot) AS n_setelah_snapshot,
    COUNT(*) FILTER (WHERE event_pada_hari_snapshot_parsial) AS n_hari_snapshot,
    COUNT(*) FILTER (WHERE updated_null) AS n_updated_null,
    COUNT(*) FILTER (WHERE updated_berbeda) AS n_updated_berbeda,
    COUNT(*) FILTER (WHERE updated_sebelum_event) AS n_updated_sebelum,
    COUNT(*) FILTER (WHERE updated_dapat_dibandingkan) AS n_updated_evaluable
  FROM event_tag
  GROUP BY yr, bulan, isodow, jam, domain_checktype, domain_wfh, domain_manual, kategori_approval
), agregat AS MATERIALIZED (
  SELECT yr, bulan, isodow, jam, domain_checktype, domain_wfh,
    domain_manual, kategori_approval,
    GROUPING(yr) AS gy, GROUPING(bulan) AS gb,
    GROUPING(isodow) AS gd, GROUPING(domain_checktype) AS gc,
    GROUPING(domain_wfh) AS gw, GROUPING(domain_manual) AS gm,
    GROUPING(kategori_approval) AS ga,
    SUM(n)::bigint AS n,
    SUM(n_jadwal_null)::bigint AS n_jadwal_null,
    SUM(n_jadwal_orphan)::bigint AS n_jadwal_orphan,
    SUM(n_checktype_invalid)::bigint AS n_checktype_invalid,
    SUM(n_wfh_unmapped)::bigint AS n_wfh_unmapped,
    SUM(n_manual_null)::bigint AS n_manual_null,
    SUM(n_manual_no_approval)::bigint AS n_manual_no_approval,
    SUM(n_approval_sebelum_event)::bigint AS n_approval_sebelum_event,
    SUM(n_nonmanual_ada_approval)::bigint AS n_nonmanual_ada_approval,
    SUM(n_event_time_null)::bigint AS n_event_time_null,
    SUM(n_event_sebelum_pegawai)::bigint AS n_event_sebelum_pegawai,
    SUM(n_setelah_snapshot)::bigint AS n_setelah_snapshot,
    SUM(n_hari_snapshot)::bigint AS n_hari_snapshot,
    SUM(n_updated_null)::bigint AS n_updated_null,
    SUM(n_updated_berbeda)::bigint AS n_updated_berbeda,
    SUM(n_updated_sebelum)::bigint AS n_updated_sebelum,
    SUM(n_updated_evaluable)::bigint AS n_updated_evaluable
  FROM base_agregat
  GROUP BY GROUPING SETS (
    (), (yr), (domain_checktype), (domain_wfh), (domain_manual),
    (kategori_approval), (isodow, jam), (bulan)
  )
), total AS (
  SELECT n AS seluruh_event FROM agregat
  WHERE gy = 1 AND gb = 1 AND gd = 1 AND gc = 1
    AND gw = 1 AND gm = 1 AND ga = 1
), hasil AS (
  SELECT v.test_id, v.metrik,
    CASE
      WHEN a.gy = 0 THEN 'tahun=' || COALESCE(a.yr::text, '(NULL created_at)')
      WHEN a.gb = 0 THEN 'bulan=' || COALESCE(a.bulan::text, '(NULL created_at)')
      WHEN a.gc = 0 THEN 'checktype=' || a.domain_checktype
      WHEN a.gw = 0 THEN 'is_wfh=' || a.domain_wfh
      WHEN a.gm = 0 THEN 'is_manual=' || a.domain_manual
      WHEN a.ga = 0 THEN 'approval=' || a.kategori_approval
      WHEN a.gd = 0 THEN 'isodow=' || a.isodow::text || ';jam=' || a.jam::text
      ELSE 'SELURUH_HISTORI' END AS segmen,
    v.nilai,
    CASE WHEN a.gy = 0 THEN a.n ELSE tt.seluruh_event END AS denominator
  FROM agregat a
  CROSS JOIN total tt
  CROSS JOIN LATERAL (VALUES
    ('A1','jumlah_event',a.n, (a.gy = 0)),
    ('A1','jadwal_id_null',a.n_jadwal_null, (a.gy = 0 OR (a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1))),
    ('A1','jadwal_id_orphan',a.n_jadwal_orphan, (a.gy = 0 OR (a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1))),
    ('A2','domain_checktype',a.n, a.gc = 0),
    ('A2','domain_is_wfh',a.n, a.gw = 0),
    ('A2','domain_is_manual',a.n, a.gm = 0),
    ('A2','checktype_di_luar_1_2_atau_null',a.n_checktype_invalid, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A2','is_wfh_di_luar_0_1_atau_null',a.n_wfh_unmapped, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A2','is_manual_null',a.n_manual_null, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A3','kategori_manual_approval',a.n, a.ga = 0),
    ('A3','manual_tanpa_approval_at',a.n_manual_no_approval, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A3','approval_at_sebelum_created_at',a.n_approval_sebelum_event, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A3','nonmanual_dengan_approval_at',a.n_nonmanual_ada_approval, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A4','created_at_null',a.n_event_time_null, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A4','created_at_sebelum_m_pegawai_created_at',a.n_event_sebelum_pegawai, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A4','created_at_setelah_tanggal_snapshot',a.n_setelah_snapshot, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A4','created_at_pada_hari_snapshot_parsial',a.n_hari_snapshot, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A4','sebaran_isodow_jam_proksi',a.n, a.gd = 0),
    ('A7','updated_at_null',a.n_updated_null, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A7','updated_at_dapat_dibandingkan',a.n_updated_evaluable, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A7','updated_at_berbeda_created_at',a.n_updated_berbeda, a.gy = 0 OR (a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1)),
    ('A7','updated_at_sebelum_created_at',a.n_updated_sebelum, a.gy = 1 AND a.gb = 1 AND a.gd = 1 AND a.gc = 1 AND a.gw = 1 AND a.gm = 1 AND a.ga = 1),
    ('A10','event_per_bulan',a.n, a.gb = 0)
  ) AS v(test_id, metrik, nilai, pakai)
  WHERE v.pakai
), bulan_kosong AS (
  SELECT gs::date AS bulan
  FROM (SELECT min(bulan) AS awal, max(bulan) AS akhir
        FROM agregat WHERE gb=0 AND bulan IS NOT NULL) batas
  CROSS JOIN LATERAL generate_series(batas.awal, batas.akhir, INTERVAL '1 month') gs
  WHERE NOT EXISTS (SELECT 1 FROM agregat a WHERE a.gb=0 AND a.bulan=gs::date)
)
SELECT h.test_id, h.metrik, h.segmen,
  CASE WHEN h.nilai BETWEEN 1 AND 4 THEN '<5' ELSE h.nilai::text END AS nilai,
  CASE WHEN h.denominator BETWEEN 1 AND 4 THEN '<5' ELSE h.denominator::text END AS denominator,
  CASE WHEN h.nilai BETWEEN 1 AND 4 OR h.denominator = 0 THEN NULL
       ELSE ROUND(100.0 * h.nilai / h.denominator, 4) END AS persen
FROM hasil h
UNION ALL
SELECT 'A10', 'bulan_tanpa_event', 'bulan='|| bulan::text,
       '0', (SELECT seluruh_event::text FROM total), 0::numeric
FROM bulan_kosong
ORDER BY test_id, metrik, segmen;

COMMIT;
