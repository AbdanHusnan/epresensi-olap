-- Read-only, jalankan pada staging_bkd_test_20261027; tidak menetapkan shift.
BEGIN READ ONLY;
SET LOCAL statement_timeout='30s';
SELECT reason,count(*) departments,sum(active_employees) active_employees
FROM test_control.workday_missing_regular_breakdown GROUP BY reason ORDER BY reason;
SELECT b.reason,p.status_shift,count(*) active_employees
FROM test_control.workday_missing_regular_breakdown b
JOIN raw.raw_pegawai p ON p.departemen=b.departemen_id
JOIN raw.raw_previleges v ON v.id=p.status
WHERE v.previleges IN ('PNS','PTT','PPPK','PPPK Paruh Waktu')
GROUP BY b.reason,p.status_shift ORDER BY b.reason,p.status_shift;
WITH candidates AS (
 SELECT b.*, EXISTS(SELECT 1 FROM raw.raw_shift s JOIN raw.raw_jadwal j ON j.jenis=s.id
 WHERE s.departemen_id=b.departemen_id AND s.status IS TRUE AND j.hari='Tue') has_any_tuesday,
 EXISTS(SELECT 1 FROM raw.raw_shift s JOIN raw.raw_jadwal j ON j.jenis=s.id
 WHERE s.departemen_id=b.departemen_id AND s.status IS TRUE AND j.hari='Tue'
 AND j.jam_masuk IS NOT NULL AND j.jam_keluar IS NOT NULL
 AND j.jam_masuk<>j.jam_keluar) has_distinct_times
 FROM test_control.workday_missing_regular_breakdown b
)
SELECT reason,has_any_tuesday,has_distinct_times,count(*) departments,sum(active_employees) active_employees
FROM candidates GROUP BY 1,2,3 ORDER BY 1,2,3;
SELECT ancestor_depth,count(*) departments,sum(active_employees) active_employees
FROM test_control.workday_missing_regular_breakdown GROUP BY 1 ORDER BY 1;
COMMIT;
