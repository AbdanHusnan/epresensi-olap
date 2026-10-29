SELECT current_database();
SELECT 'fact' AS object,count(*) AS rows FROM mart_kehadiran.fact_kehadiran_daily
UNION ALL SELECT 'aggregate',count(*) FROM serving.agg_kehadiran_departemen_harian
UNION ALL SELECT 'batch',count(*) FROM etl_control.mart_batch
UNION ALL SELECT 'receipt',count(*) FROM etl_control.mart_delivery_receipt
UNION ALL SELECT 'cursor',count(*) FROM etl_control.mart_delivery_cursor
UNION ALL SELECT 'date_state',count(*) FROM serving.attendance_date_state;
SELECT proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='etl_control' AND proname='apply_mart_delivery';
