-- Run read-only against mart_bkd_bulk_20261029.
BEGIN READ ONLY;
SELECT departemen_id_sumber,
       SUM(active_employee_days) AS active,
       SUM(checkin_days) AS checkin,
       SUM(checkout_days) AS checkout,
       SUM(no_checkin_days) AS missing_checkin,
       SUM(no_checkout_days) AS missing_checkout,
       SUM(leave_days) AS leave,
       100.0 * SUM(checkin_days) / NULLIF(SUM(active_employee_days), 0) AS checkin_rate,
       100.0 * SUM(checkout_days) / NULLIF(SUM(active_employee_days), 0) AS checkout_rate,
       100.0 * SUM(required_checkin_present_days) / NULLIF(SUM(required_checkin_days), 0) AS required_checkin_rate,
       100.0 * SUM(required_checkout_present_days) / NULLIF(SUM(required_checkout_days), 0) AS required_checkout_rate
FROM serving.v_kehadiran_departemen_harian
WHERE tanggal = DATE '2026-10-28'
GROUP BY GROUPING SETS ((), (departemen_id_sumber))
ORDER BY departemen_id_sumber NULLS FIRST;
COMMIT;
