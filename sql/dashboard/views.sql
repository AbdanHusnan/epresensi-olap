-- Non-materialized views: committed ETL changes are visible without refresh jobs.
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE OR REPLACE VIEW analytics.attendance_daily AS
SELECT f.pegawai_id, f.tanggal, f.departemen_id, d.nama_departemen,
       f.status_kehadiran, f.is_expected_workday, f.has_masuk, f.has_pulang,
       f.is_terlambat, f.menit_terlambat,
       CASE WHEN f.status_kehadiran <> 'HADIR' THEN 'NOT_PRESENT'
            WHEN f.is_wfo AND f.is_wfh THEN 'MIXED'
            WHEN f.is_wfo THEN 'WFO' WHEN f.is_wfh THEN 'WFH'
            ELSE 'UNKNOWN' END AS work_mode,
       CASE WHEN NOT f.is_terlambat OR f.menit_terlambat IS NULL THEN NULL
            WHEN f.menit_terlambat < 1 THEN '<1'
            WHEN f.menit_terlambat <= 15 THEN '1-15'
            WHEN f.menit_terlambat <= 30 THEN '16-30'
            WHEN f.menit_terlambat <= 60 THEN '31-60'
            ELSE '>60' END AS lateness_bucket,
       CASE WHEN f.is_expected_workday THEN 1 ELSE 0 END AS expected_days,
       CASE WHEN f.is_expected_workday AND f.status_kehadiran='HADIR' THEN 1 ELSE 0 END AS present_days,
       CASE WHEN f.is_expected_workday AND f.status_kehadiran='IZIN' THEN 1 ELSE 0 END AS leave_days,
       CASE WHEN f.is_expected_workday AND f.status_kehadiran='TIDAK_ABSEN' THEN 1 ELSE 0 END AS absent_days,
       CASE WHEN f.is_expected_workday AND f.status_kehadiran='HADIR'
                  AND f.menit_terlambat IS NOT NULL THEN 1 ELSE 0 END AS evaluated_days,
       CASE WHEN f.is_expected_workday AND f.status_kehadiran='HADIR'
                  AND f.menit_terlambat IS NOT NULL AND NOT f.is_terlambat THEN 1 ELSE 0 END AS ontime_days,
       CASE WHEN f.is_expected_workday AND f.status_kehadiran='HADIR'
                  AND f.menit_terlambat IS NOT NULL AND f.is_terlambat THEN 1 ELSE 0 END AS late_days,
       CASE WHEN f.is_expected_workday AND f.status_kehadiran='HADIR'
                  AND f.menit_terlambat IS NOT NULL AND f.is_terlambat
            THEN f.menit_terlambat ELSE 0 END AS late_minutes,
       NULL::numeric AS attendance_target,
       NULL::numeric AS ontime_target,
       NULL::numeric AS absence_target,
       NULL::numeric AS lateness_target,
       'TARGET_NOT_SET'::text AS target_status,
       f.etl_loaded_at
FROM public.fact_kehadiran f
LEFT JOIN public.dim_departemen d ON d.departemen_id=f.departemen_id;

CREATE OR REPLACE VIEW analytics.attendance_department_daily AS
SELECT tanggal, departemen_id, nama_departemen,
       count(*) AS employee_days,
       sum(expected_days) AS expected_days, sum(present_days) AS present_days,
       sum(leave_days) AS leave_days, sum(absent_days) AS absent_days,
       sum(evaluated_days) AS evaluated_days, sum(ontime_days) AS ontime_days,
       sum(late_days) AS late_days, sum(late_minutes) AS late_minutes,
       count(*) FILTER (WHERE has_masuk) AS checkin_days,
       count(*) FILTER (WHERE has_pulang) AS checkout_days,
       count(*) FILTER (WHERE work_mode='WFO') AS wfo_days,
       count(*) FILTER (WHERE work_mode='WFH') AS wfh_days,
       count(*) FILTER (WHERE work_mode='MIXED') AS mixed_days,
       count(*) FILTER (WHERE work_mode='UNKNOWN') AS unknown_mode_days,
       NULL::numeric AS attendance_target, NULL::numeric AS ontime_target,
       NULL::numeric AS absence_target, NULL::numeric AS lateness_target,
       'TARGET_NOT_SET'::text AS target_status,
       max(etl_loaded_at) AS etl_loaded_at
FROM analytics.attendance_daily
GROUP BY tanggal, departemen_id, nama_departemen;
