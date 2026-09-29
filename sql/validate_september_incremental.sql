-- Run on OLAP after the incremental test. Read-only.
-- Expected September statuses after incremental alone:
-- HADIR=1479280; IZIN=216480; no TIDAK_ABSEN/NON_WORKING_DAY yet.
-- After September master: additionally TIDAK_ABSEN=108240, NON_WORKING_DAY=656000.
SELECT status_kehadiran, count(*) AS pegawai_hari
FROM fact_kehadiran
WHERE tanggal BETWEEN '2026-09-01' AND '2026-09-30'
GROUP BY status_kehadiran ORDER BY status_kehadiran;

-- Expected: 1695760 after incremental; 2460000 after full September master.
-- Flags: WFH=342760, late=360800, early=162360, incomplete present=72160.
-- Event total=2886400.
SELECT count(*) AS september_facts,
       count(*) FILTER (WHERE is_wfh) AS wfh,
       count(*) FILTER (WHERE is_terlambat) AS terlambat,
       count(*) FILTER (WHERE is_pulang_awal) AS pulang_awal,
       count(*) FILTER (WHERE status_kehadiran='HADIR'
                        AND NOT is_complete_attendance) AS hadir_tidak_lengkap,
       sum(jumlah_event) AS source_events
FROM fact_kehadiran
WHERE tanggal BETWEEN '2026-09-01' AND '2026-09-30';

-- Expected APPROVED=216480, PENDING=36080, REJECTED=18040.
SELECT status_pengajuan, count(*) AS pengajuan
FROM fact_perizinan
WHERE tanggal_mulai BETWEEN '2026-09-01' AND '2026-09-30'
GROUP BY status_pengajuan ORDER BY status_pengajuan;

-- Expected 0 duplicate employee-days.
SELECT count(*) AS duplicate_employee_days FROM (
    SELECT pegawai_id,tanggal FROM fact_kehadiran
    WHERE tanggal BETWEEN '2026-09-01' AND '2026-09-30'
    GROUP BY pegawai_id,tanggal HAVING count(*)>1
) duplicates;

-- Expected 0 invalid approved leave references.
SELECT count(*) AS invalid_leave_references
FROM fact_kehadiran f LEFT JOIN fact_perizinan p ON p.perizinan_id=f.perizinan_id
WHERE f.tanggal BETWEEN '2026-09-01' AND '2026-09-30'
  AND f.perizinan_id IS NOT NULL
  AND (p.perizinan_id IS NULL OR NOT p.is_valid_leave OR p.pegawai_id<>f.pegawai_id
       OR f.tanggal NOT BETWEEN p.tanggal_mulai AND p.tanggal_selesai);

SELECT pipeline_name,last_watermark_id,last_watermark_timestamp,last_success_at
FROM etl_control.pipeline_state ORDER BY pipeline_name;

SELECT run_id,pipeline_name,status,started_at,finished_at,
       rows_extracted,rows_inserted,rows_updated,error_message
FROM etl_control.pipeline_runs ORDER BY run_id DESC LIMIT 10;
