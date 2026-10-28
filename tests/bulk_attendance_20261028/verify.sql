\set ON_ERROR_STOP on
\pset pager off
\x on
-- Read-only inspection; run against staging_bkd_bulk_20261028.
SELECT current_database(),test_date FROM test_bulk.config;
SELECT batch_id,status,result FROM etl_control.curated_batch ORDER BY created_at;
SELECT phase,result->'totals' AS totals FROM test_bulk.results ORDER BY phase;
SELECT c.scenario,count(*) AS employees,
 sum(d.active_employee_days) active,sum(d.checkin_days) checkin,sum(d.checkout_days) checkout,
 sum(d.excused_checkin_days) excused_checkin,sum(d.excused_checkout_days) excused_checkout,
 sum(d.required_checkin_days) required_checkin,sum(d.required_checkout_days) required_checkout,
 sum(d.no_checkin_days) no_checkin,sum(d.no_checkout_days) no_checkout,sum(d.leave_days) leave_days
FROM test_bulk.cohort c JOIN curated.cur_attendance_daily d ON d.pegawai_id=c.emp
GROUP BY c.scenario ORDER BY c.scenario;
SELECT d.pegawai_id,d.tanggal,d.checkin_event_count,d.checkout_event_count,
 d.first_checkin_at,d.last_checkout_at,d.checkin_days,d.checkout_days,
 d.no_checkin_days,d.no_checkout_days
FROM curated.cur_attendance_daily d JOIN test_bulk.cohort c ON c.emp=d.pegawai_id
WHERE c.scenario=10 ORDER BY d.pegawai_id LIMIT 10;
SELECT count(*) AS inconsistent_kpi_rows FROM curated.cur_attendance_daily WHERE
 active_employee_days<>required_checkin_days+excused_checkin_days OR
 active_employee_days<>required_checkout_days+excused_checkout_days OR
 required_checkin_days<>required_checkin_present_days+no_checkin_days OR
 required_checkout_days<>required_checkout_present_days+no_checkout_days;
