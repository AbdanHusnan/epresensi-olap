SELECT current_database();
SELECT n.nspname AS schema_name,c.relname,c.relkind
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname IN ('mart_kehadiran','serving','etl_control') AND c.relkind IN ('r','v')
ORDER BY 1,2;
SELECT 'fact' AS object,count(*) FROM mart_kehadiran.fact_kehadiran_daily
UNION ALL SELECT 'aggregate',count(*) FROM serving.agg_kehadiran_departemen_harian
UNION ALL SELECT 'calendar',count(*) FROM mart_kehadiran.dim_calendar
UNION ALL SELECT 'employee',count(*) FROM mart_kehadiran.dim_pegawai
UNION ALL SELECT 'department_unknown',count(*) FROM mart_kehadiran.dim_departemen WHERE departemen_key=0
UNION ALL SELECT 'department_business',count(*) FROM mart_kehadiran.dim_departemen WHERE departemen_key<>0
UNION ALL SELECT 'batch',count(*) FROM etl_control.mart_batch
UNION ALL SELECT 'date_state',count(*) FROM serving.attendance_date_state;
