BEGIN;
DO $$ BEGIN
 IF current_database() <> 'staging_bkd_test_20261027' THEN
  RAISE EXCEPTION 'Pilot SQL may run only in staging_bkd_test_20261027';
 END IF;
END $$;
SET LOCAL TIME ZONE 'Asia/Jakarta';
INSERT INTO curated.ref_calendar(tanggal,is_weekend)
VALUES ('2026-10-27',false) ON CONFLICT DO NOTHING;
WITH schedules AS (
 SELECT s.departemen_id,count(*)::int AS n
 FROM raw.raw_shift s JOIN raw.raw_jadwal j ON j.jenis=s.id
 WHERE s.status IS TRUE AND s.nama ~* '(regular|reguler)' AND j.hari='Tue'
 GROUP BY s.departemen_id
), flags AS (
 SELECT p.id,p.departemen,p.updated_at,
 CASE WHEN v.previleges IN ('PNS','PTT','PPPK','PPPK Paruh Waktu') THEN true
      WHEN v.previleges='Non-Aktif' THEN false ELSE NULL END AS active,
 coalesce(s.n,0) AS n,
 (EXTRACT(isodow FROM date '2026-10-27') IN (6,7)
  OR EXISTS(SELECT 1 FROM raw.raw_hari_libur h WHERE h.tanggal='2026-10-27')
  OR l.pegawai_id IS NOT NULL) AS off
 FROM raw.raw_pegawai p
 LEFT JOIN raw.raw_previleges v ON v.id=p.status
 LEFT JOIN schedules s ON s.departemen_id=p.departemen
 LEFT JOIN (SELECT DISTINCT pegawai_id FROM raw.raw_libur_shift WHERE tanggal='2026-10-27') l ON l.pegawai_id=p.id
)
INSERT INTO curated.cur_employee_workday
SELECT id,date '2026-10-27',departemen,active,n>0,n,off,active AND n>0 AND NOT off,
 (SELECT snapshot_at FROM test_control.run),updated_at FROM flags
ON CONFLICT (pegawai_id,tanggal) DO UPDATE SET
 departemen_id=excluded.departemen_id,is_employee_active=excluded.is_employee_active,
 has_regular_schedule=excluded.has_regular_schedule,
 candidate_regular_schedule_count=excluded.candidate_regular_schedule_count,
 is_day_off=excluded.is_day_off,is_expected_workday=excluded.is_expected_workday,
 source_snapshot_at=excluded.source_snapshot_at,source_updated_at=excluded.source_updated_at;
COMMIT;
