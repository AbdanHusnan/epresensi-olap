SELECT current_database();
SELECT last_sequence,bootstrap_prepared FROM etl_control.mart_outbox_stream;
SELECT 'outbox_batch' AS object,count(*) AS rows FROM etl_control.mart_outbox_batch
UNION ALL SELECT 'outbox_item',count(*) FROM etl_control.mart_outbox_item;
SELECT count(*) AS capture_triggers FROM pg_trigger
WHERE tgrelid='curated.cur_attendance_daily'::regclass AND tgname LIKE 'mart_outbox_%';
SELECT proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='etl_control' AND proname IN ('prepare_mart_bootstrap','next_mart_delivery','ack_mart_delivery','capture_mart_outbox');
