-- Compact, READ-ONLY E-Presensi database assessment export.
-- Produces one CSV on stdout: section, record (JSON text).
-- Run with psql -X -q -v ON_ERROR_STOP=1 -f ... > epresensi_reference_data.csv
-- Avoids exporting complete employee lists and scanning all 89M+ attendance rows.

SET statement_timeout = '120s';
SET default_transaction_read_only = on;

COPY (
  SELECT section, record
  FROM (
    SELECT 1 AS sort_order, 'database_info'::text AS section,
           to_jsonb(q)::text AS record
    FROM (SELECT current_database() AS database_name, current_user AS database_user,
                 current_setting('server_version') AS pg_version) q

    UNION ALL
    SELECT 2, 'estimated_table_sizes', to_jsonb(q)::text
    FROM (
      SELECT n.nspname AS schema_name, c.relname AS table_name,
             c.reltuples::bigint AS estimated_rows,
             pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public'
        AND c.relname IN ('m_pegawai','m_departemen','m_shift','m_jadwal',
                          'm_user','m_jenis_ijin','m_tipe_ijin','m_hari_libur',
                          't_libur_shift','t_checkinout','t_perizinan')
        AND c.relkind IN ('r','p')
    ) q

    UNION ALL
    SELECT 3, 'employee_sample', to_jsonb(q)::text
    FROM (
      SELECT id AS pegawai_id, departemen AS departemen_id,
             status, status_shift, unit_kerja_induk
      FROM public.m_pegawai ORDER BY id LIMIT 150
    ) q

    UNION ALL
    SELECT 4, 'employee_status_distribution', to_jsonb(q)::text
    FROM (
      SELECT status, status_shift, count(*) AS employee_count
      FROM public.m_pegawai GROUP BY status, status_shift
    ) q

    UNION ALL
    SELECT 5, 'department_sample', to_jsonb(q)::text
    FROM (
      SELECT id AS departemen_id, kode, parent, opd_parent,
             unit_kerja_induk, is_allow_wfh
      FROM public.m_departemen ORDER BY id LIMIT 150
    ) q

    UNION ALL
    SELECT 6, 'shift_sample', to_jsonb(q)::text
    FROM (
      SELECT id AS shift_id, nama AS shift_name, status AS is_active,
             departemen_id, event_id, is_flexible
      FROM public.m_shift ORDER BY id LIMIT 150
    ) q

    UNION ALL
    SELECT 7, 'schedule_sample', to_jsonb(q)::text
    FROM (
      SELECT j.id AS jadwal_id, j.jenis AS shift_id, s.departemen_id,
             s.nama AS shift_name, s.status AS shift_is_active,
             j.hari, j.jam_masuk, j.jam_keluar,
             j.jam_masuk_awal, j.jam_keluar_akhir, j.flexible_time
      FROM public.m_jadwal j
      LEFT JOIN public.m_shift s ON s.id=j.jenis
      ORDER BY j.id LIMIT 200
    ) q

    UNION ALL
    SELECT 8, 'user_employee_mapping_sample', to_jsonb(q)::text
    FROM (
      SELECT id AS user_id, pegawai_id
      FROM public.m_user WHERE pegawai_id IS NOT NULL
      ORDER BY id LIMIT 150
    ) q

    UNION ALL
    SELECT 9, 'permission_kind_master', to_jsonb(q)::text
    FROM (
      SELECT id AS jenis_ijin_id, nama, kode, setengah_hari,
             tipe_id, potongan, is_aktif, label_kode
      FROM public.m_jenis_ijin
    ) q

    UNION ALL
    SELECT 10, 'permission_type_master', to_jsonb(q)::text
    FROM (
      SELECT id AS tipe_ijin_id, nama, tipe
      FROM public.m_tipe_ijin
    ) q

    UNION ALL
    SELECT 11, 'public_holidays', to_jsonb(q)::text
    FROM (
      SELECT id, tanggal, keterangan FROM public.m_hari_libur
    ) q

    UNION ALL
    SELECT 12, 'employee_shift_holiday_sample', to_jsonb(q)::text
    FROM (
      SELECT id, departemen_id, pegawai_id, tanggal
      FROM public.t_libur_shift ORDER BY id DESC LIMIT 100
    ) q

    UNION ALL
    SELECT 13, 'attendance_sample_recent_id', to_jsonb(q)::text
    FROM (
      SELECT id, pegawai_id, departemen, location, checktype,
             approval, approval_at, created_at, updated_at,
             is_wfh, work_code, jadwal_id, hari,
             jam_masuk, jam_keluar, jam_masuk_awal,
             jam_keluar_akhir, flexible_time, is_manual
      FROM public.t_checkinout ORDER BY id DESC LIMIT 100
    ) q

    UNION ALL
    SELECT 14, 'permission_sample_recent_id', to_jsonb(q)::text
    FROM (
      SELECT id, user_id, departemen, tipe_ijin, jenis_ijin,
             approval, approval_at, created_at,
             tgl_ijin, tgl_ijin_sampai, pegawai_id,
             updated_at, status, updated_user
      FROM public.t_perizinan ORDER BY id DESC LIMIT 100
    ) q

    UNION ALL
    SELECT 15, 'shift_department_coverage_sample', to_jsonb(q)::text
    FROM (
      SELECT s.departemen_id,
             count(DISTINCT s.id) AS shift_count,
             count(DISTINCT j.id) AS schedule_count,
             count(DISTINCT s.id) FILTER (WHERE s.status IS TRUE) AS active_shift_count
      FROM public.m_shift s
      LEFT JOIN public.m_jadwal j ON j.jenis=s.id
      GROUP BY s.departemen_id ORDER BY s.departemen_id LIMIT 100
    ) q

    UNION ALL
    SELECT 16, 'transaction_time_ranges_from_samples', to_jsonb(q)::text
    FROM (
      SELECT 't_checkinout' AS table_name,
             min(created_at)::text AS sample_min_timestamp,
             max(created_at)::text AS sample_max_timestamp
      FROM (SELECT created_at FROM public.t_checkinout ORDER BY id DESC LIMIT 1000) recent
      UNION ALL
      SELECT 't_perizinan', min(created_at)::text, max(created_at)::text
      FROM (SELECT created_at FROM public.t_perizinan ORDER BY id DESC LIMIT 1000) recent
    ) q
  ) sections
  ORDER BY sort_order, record
) TO STDOUT WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
