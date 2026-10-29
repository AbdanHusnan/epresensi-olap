-- Definitions only: no invocation, source read, or fact/serving load.
BEGIN;
SET LOCAL lock_timeout='5s';
SELECT pg_advisory_xact_lock(hashtext('attendance_daily_v1_apply'));
CREATE TABLE etl_control.mart_delivery_cursor (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 stream_id text NOT NULL,
 last_sequence bigint NOT NULL CHECK(last_sequence>0)
);
CREATE TABLE etl_control.mart_delivery_receipt (
 stream_id text NOT NULL,
 batch_sequence bigint NOT NULL,
 batch_id text NOT NULL UNIQUE REFERENCES etl_control.mart_batch,
 payload jsonb NOT NULL,
 applied_at timestamptz NOT NULL DEFAULT current_timestamp,
 PRIMARY KEY(stream_id,batch_sequence)
);
CREATE FUNCTION etl_control.apply_mart_delivery(p_delivery jsonb) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
 v_stream text:=p_delivery->>'stream_id';
 v_seq bigint:=(p_delivery->>'sequence')::bigint;
 v_batch text;
 v_cursor etl_control.mart_delivery_cursor%ROWTYPE;
 v_existing jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('attendance_daily_v1_apply'));
 IF p_delivery->>'contract_version' IS DISTINCT FROM 'ATTENDANCE_DAILY_V1'
 OR v_stream IS NULL OR v_stream !~ '^[a-f0-9]{32}$' OR v_seq IS NULL OR v_seq<1
 OR COALESCE(p_delivery->>'kind','') NOT IN ('BOOTSTRAP','DELTA')
 OR jsonb_typeof(p_delivery->'items') IS DISTINCT FROM 'array' THEN
  RAISE EXCEPTION 'Invalid delivery envelope';
 END IF;
 SELECT payload INTO v_existing FROM etl_control.mart_delivery_receipt
 WHERE stream_id=v_stream AND batch_sequence=v_seq;
 IF FOUND THEN
  IF v_existing IS DISTINCT FROM p_delivery THEN RAISE EXCEPTION 'Replay payload changed'; END IF;
  RETURN jsonb_build_object('stream_id',v_stream,'sequence',v_seq)::text;
 END IF;
 SELECT * INTO v_cursor FROM etl_control.mart_delivery_cursor WHERE singleton FOR UPDATE;
 IF FOUND THEN
  IF v_cursor.stream_id<>v_stream OR v_seq<>v_cursor.last_sequence+1 THEN RAISE EXCEPTION 'Wrong stream or out-of-order sequence'; END IF;
 ELSE
  IF v_seq<>1 OR p_delivery->>'kind'<>'BOOTSTRAP'
  OR EXISTS(SELECT 1 FROM mart_kehadiran.fact_kehadiran_daily)
  OR EXISTS(SELECT 1 FROM serving.agg_kehadiran_departemen_harian)
  OR EXISTS(SELECT 1 FROM etl_control.mart_batch) THEN
   RAISE EXCEPTION 'Initial delivery requires sequence 1 bootstrap and empty target';
  END IF;
 END IF;
 -- Serialize dimension writers while effective versions are resolved.
 LOCK TABLE mart_kehadiran.dim_pegawai,mart_kehadiran.dim_departemen IN SHARE ROW EXCLUSIVE MODE;
 v_batch:='ATTENDANCE_'||v_stream||'_'||v_seq::text;
 INSERT INTO etl_control.mart_batch(batch_id,contract_version,status)
 VALUES(v_batch,'ATTENDANCE_DAILY_V1','READY');
 DROP TABLE IF EXISTS pg_temp.mart_incoming,pg_temp.mart_candidate,pg_temp.mart_changed,pg_temp.mart_dirty;
 CREATE TEMP TABLE mart_incoming(
  pegawai_id integer NOT NULL,tanggal date NOT NULL,operation text NOT NULL CHECK(operation IN ('UPSERT','DELETE')),
  payload jsonb,PRIMARY KEY(pegawai_id,tanggal),
  CHECK((operation='UPSERT')=(payload IS NOT NULL))
 ) ON COMMIT DROP;
 INSERT INTO mart_incoming SELECT * FROM jsonb_to_recordset(p_delivery->'items')
 AS i(pegawai_id integer,tanggal date,operation text,payload jsonb);
 IF EXISTS(SELECT 1 FROM mart_incoming WHERE operation='UPSERT' AND
 ((payload->>'pegawai_id')::integer IS DISTINCT FROM pegawai_id OR
 (payload->>'tanggal')::date IS DISTINCT FROM tanggal OR jsonb_typeof(payload)<>'object')) THEN
  RAISE EXCEPTION 'Payload/key mismatch';
 END IF;
 IF p_delivery->>'kind'='BOOTSTRAP' AND EXISTS(SELECT 1 FROM mart_incoming WHERE operation='DELETE') THEN
  RAISE EXCEPTION 'Bootstrap cannot delete';
 END IF;
 INSERT INTO mart_kehadiran.dim_calendar(tanggal)
 SELECT DISTINCT tanggal FROM mart_incoming ON CONFLICT DO NOTHING;

 WITH missing AS (
 SELECT DISTINCT i.pegawai_id AS source_id,i.tanggal,
 (SELECT min(d.valid_from) FROM mart_kehadiran.dim_pegawai d
  WHERE d.pegawai_id_sumber=i.pegawai_id AND d.valid_from>i.tanggal) AS next_start
 FROM mart_incoming i WHERE i.operation='UPSERT' AND i.pegawai_id IS NOT NULL
 AND NOT EXISTS(SELECT 1 FROM mart_kehadiran.dim_pegawai d
 WHERE d.pegawai_id_sumber=i.pegawai_id AND i.tanggal>=d.valid_from AND (d.valid_to IS NULL OR i.tanggal<d.valid_to))
 )
 INSERT INTO mart_kehadiran.dim_pegawai(pegawai_id_sumber,nama,valid_from,valid_to)
 SELECT source_id,NULL,min(tanggal),next_start FROM missing GROUP BY source_id,next_start;

 WITH missing AS (
 SELECT DISTINCT (i.payload->>'departemen_id')::integer AS source_id,i.tanggal,
 (SELECT min(d.valid_from) FROM mart_kehadiran.dim_departemen d
  WHERE d.departemen_id_sumber=(i.payload->>'departemen_id')::integer AND d.valid_from>i.tanggal) AS next_start
 FROM mart_incoming i WHERE i.operation='UPSERT' AND (i.payload->>'departemen_id')::integer IS NOT NULL
 AND NOT EXISTS(SELECT 1 FROM mart_kehadiran.dim_departemen d
 WHERE d.departemen_id_sumber=(i.payload->>'departemen_id')::integer AND i.tanggal>=d.valid_from AND (d.valid_to IS NULL OR i.tanggal<d.valid_to))
 )
 INSERT INTO mart_kehadiran.dim_departemen(departemen_id_sumber,nama,valid_from,valid_to)
 SELECT source_id,NULL,min(tanggal),next_start FROM missing GROUP BY source_id,next_start;

 CREATE TEMP TABLE mart_candidate (LIKE mart_kehadiran.fact_kehadiran_daily INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING CONSTRAINTS) ON COMMIT DROP;
 INSERT INTO mart_candidate (pegawai_id_sumber,tanggal,pegawai_key,departemen_key,departemen_id_sumber,is_employee_active,population_basis,has_masuk,has_pulang,checkin_event_count,checkout_event_count,first_checkin_at,last_checkout_at,has_manual_event,has_valid_leave,has_full_day_leave,has_partial_day_leave,has_excused_checkin,has_excused_checkout,active_employee_days,checkin_days,checkout_days,no_checkin_days,no_checkout_days,leave_days,required_checkin_days,required_checkout_days,excused_checkin_days,excused_checkout_days,required_checkin_present_days,required_checkout_present_days,perlu_review,alasan_review,is_date_final,date_assignment_policy,source_snapshot_at,source_batch_id,contract_version,mart_loaded_at)
 SELECT r.pegawai_id_sumber,r.tanggal,r.pegawai_key,r.departemen_key,r.departemen_id_sumber,r.is_employee_active,r.population_basis,r.has_masuk,r.has_pulang,r.checkin_event_count,r.checkout_event_count,r.first_checkin_at,r.last_checkout_at,r.has_manual_event,r.has_valid_leave,r.has_full_day_leave,r.has_partial_day_leave,r.has_excused_checkin,r.has_excused_checkout,r.active_employee_days,r.checkin_days,r.checkout_days,r.no_checkin_days,r.no_checkout_days,r.leave_days,r.required_checkin_days,r.required_checkout_days,r.excused_checkin_days,r.excused_checkout_days,r.required_checkin_present_days,r.required_checkout_present_days,r.perlu_review,r.alasan_review,r.is_date_final,r.date_assignment_policy,r.source_snapshot_at,r.source_batch_id,r.contract_version,r.mart_loaded_at
 FROM mart_incoming i
 JOIN mart_kehadiran.dim_pegawai p ON p.pegawai_id_sumber=i.pegawai_id
 AND i.tanggal>=p.valid_from AND (p.valid_to IS NULL OR i.tanggal<p.valid_to)
 LEFT JOIN mart_kehadiran.dim_departemen d ON d.departemen_id_sumber=(i.payload->>'departemen_id')::integer
 AND i.tanggal>=d.valid_from AND (d.valid_to IS NULL OR i.tanggal<d.valid_to)
 CROSS JOIN LATERAL jsonb_populate_record(NULL::mart_kehadiran.fact_kehadiran_daily,
 i.payload || jsonb_build_object('pegawai_id_sumber',i.pegawai_id,
 'departemen_id_sumber',i.payload->'departemen_id','pegawai_key',p.pegawai_key,
 'departemen_key',COALESCE(d.departemen_key,0),'source_batch_id',v_batch,
 'contract_version','ATTENDANCE_DAILY_V1','mart_loaded_at',current_timestamp)) r
 WHERE i.operation='UPSERT';
 IF (SELECT count(*) FROM mart_candidate)<>(SELECT count(*) FROM mart_incoming WHERE operation='UPSERT') THEN
  RAISE EXCEPTION 'Dimension resolution lost or duplicated rows';
 END IF;
 CREATE TEMP TABLE mart_changed ON COMMIT DROP AS
 SELECT n.* FROM mart_candidate n LEFT JOIN mart_kehadiran.fact_kehadiran_daily o USING(pegawai_id_sumber,tanggal)
 WHERE o.pegawai_id_sumber IS NULL OR
 (to_jsonb(o)-ARRAY['source_batch_id','source_snapshot_at','mart_loaded_at']) IS DISTINCT FROM
 (to_jsonb(n)-ARRAY['source_batch_id','source_snapshot_at','mart_loaded_at']);
 CREATE TEMP TABLE mart_dirty(tanggal date,departemen_key bigint,PRIMARY KEY(tanggal,departemen_key)) ON COMMIT DROP;
 INSERT INTO mart_dirty
 SELECT f.tanggal,f.departemen_key FROM mart_kehadiran.fact_kehadiran_daily f
 JOIN mart_incoming i ON (i.pegawai_id,i.tanggal)=(f.pegawai_id_sumber,f.tanggal)
 WHERE i.operation='DELETE' OR EXISTS(SELECT 1 FROM mart_changed c WHERE (c.pegawai_id_sumber,c.tanggal)=(f.pegawai_id_sumber,f.tanggal))
 UNION SELECT tanggal,departemen_key FROM mart_changed;
 DELETE FROM mart_kehadiran.fact_kehadiran_daily f USING mart_incoming i
 WHERE i.operation='DELETE' AND (f.pegawai_id_sumber,f.tanggal)=(i.pegawai_id,i.tanggal);
 INSERT INTO mart_kehadiran.fact_kehadiran_daily AS dst (pegawai_id_sumber,tanggal,pegawai_key,departemen_key,departemen_id_sumber,is_employee_active,population_basis,has_masuk,has_pulang,checkin_event_count,checkout_event_count,first_checkin_at,last_checkout_at,has_manual_event,has_valid_leave,has_full_day_leave,has_partial_day_leave,has_excused_checkin,has_excused_checkout,active_employee_days,checkin_days,checkout_days,no_checkin_days,no_checkout_days,leave_days,required_checkin_days,required_checkout_days,excused_checkin_days,excused_checkout_days,required_checkin_present_days,required_checkout_present_days,perlu_review,alasan_review,is_date_final,date_assignment_policy,source_snapshot_at,source_batch_id,contract_version,mart_loaded_at)
 SELECT pegawai_id_sumber,tanggal,pegawai_key,departemen_key,departemen_id_sumber,is_employee_active,population_basis,has_masuk,has_pulang,checkin_event_count,checkout_event_count,first_checkin_at,last_checkout_at,has_manual_event,has_valid_leave,has_full_day_leave,has_partial_day_leave,has_excused_checkin,has_excused_checkout,active_employee_days,checkin_days,checkout_days,no_checkin_days,no_checkout_days,leave_days,required_checkin_days,required_checkout_days,excused_checkin_days,excused_checkout_days,required_checkin_present_days,required_checkout_present_days,perlu_review,alasan_review,is_date_final,date_assignment_policy,source_snapshot_at,source_batch_id,contract_version,mart_loaded_at FROM mart_changed
 ON CONFLICT(pegawai_id_sumber,tanggal) DO UPDATE SET
 pegawai_key=EXCLUDED.pegawai_key,
 departemen_key=EXCLUDED.departemen_key,
 departemen_id_sumber=EXCLUDED.departemen_id_sumber,
 is_employee_active=EXCLUDED.is_employee_active,
 population_basis=EXCLUDED.population_basis,
 has_masuk=EXCLUDED.has_masuk,
 has_pulang=EXCLUDED.has_pulang,
 checkin_event_count=EXCLUDED.checkin_event_count,
 checkout_event_count=EXCLUDED.checkout_event_count,
 first_checkin_at=EXCLUDED.first_checkin_at,
 last_checkout_at=EXCLUDED.last_checkout_at,
 has_manual_event=EXCLUDED.has_manual_event,
 has_valid_leave=EXCLUDED.has_valid_leave,
 has_full_day_leave=EXCLUDED.has_full_day_leave,
 has_partial_day_leave=EXCLUDED.has_partial_day_leave,
 has_excused_checkin=EXCLUDED.has_excused_checkin,
 has_excused_checkout=EXCLUDED.has_excused_checkout,
 active_employee_days=EXCLUDED.active_employee_days,
 checkin_days=EXCLUDED.checkin_days,
 checkout_days=EXCLUDED.checkout_days,
 no_checkin_days=EXCLUDED.no_checkin_days,
 no_checkout_days=EXCLUDED.no_checkout_days,
 leave_days=EXCLUDED.leave_days,
 required_checkin_days=EXCLUDED.required_checkin_days,
 required_checkout_days=EXCLUDED.required_checkout_days,
 excused_checkin_days=EXCLUDED.excused_checkin_days,
 excused_checkout_days=EXCLUDED.excused_checkout_days,
 required_checkin_present_days=EXCLUDED.required_checkin_present_days,
 required_checkout_present_days=EXCLUDED.required_checkout_present_days,
 perlu_review=EXCLUDED.perlu_review,
 alasan_review=EXCLUDED.alasan_review,
 is_date_final=EXCLUDED.is_date_final,
 date_assignment_policy=EXCLUDED.date_assignment_policy,
 source_snapshot_at=EXCLUDED.source_snapshot_at,
 source_batch_id=EXCLUDED.source_batch_id,
 contract_version=EXCLUDED.contract_version,
 mart_loaded_at=EXCLUDED.mart_loaded_at;
 DELETE FROM serving.agg_kehadiran_departemen_harian a USING mart_dirty d
 WHERE (a.tanggal,a.departemen_key)=(d.tanggal,d.departemen_key);
 INSERT INTO serving.agg_kehadiran_departemen_harian(tanggal,departemen_key,
 active_employee_days,checkin_days,checkout_days,no_checkin_days,no_checkout_days,leave_days,required_checkin_days,required_checkout_days,excused_checkin_days,excused_checkout_days,required_checkin_present_days,required_checkout_present_days,fact_rows,review_rows,nonfinal_rows,serving_batch_id)
 SELECT f.tanggal,f.departemen_key,
 SUM(f.active_employee_days),SUM(f.checkin_days),SUM(f.checkout_days),SUM(f.no_checkin_days),SUM(f.no_checkout_days),SUM(f.leave_days),SUM(f.required_checkin_days),SUM(f.required_checkout_days),SUM(f.excused_checkin_days),SUM(f.excused_checkout_days),SUM(f.required_checkin_present_days),SUM(f.required_checkout_present_days),count(*),count(*) FILTER(WHERE f.perlu_review),count(*) FILTER(WHERE NOT f.is_date_final),v_batch
 FROM mart_kehadiran.fact_kehadiran_daily f JOIN mart_dirty d USING(tanggal,departemen_key)
 GROUP BY f.tanggal,f.departemen_key;
 -- This delivery has no proof of population completeness or day closure.
 -- Invalidate previously closed/completed state on a correction, never infer finality.
 INSERT INTO serving.attendance_date_state(tanggal,population_complete,curated_delivery_complete,is_closed,published_batch_id)
 SELECT DISTINCT tanggal,false,false,false,v_batch FROM mart_dirty
 ON CONFLICT(tanggal) DO UPDATE SET population_complete=false,curated_delivery_complete=false,is_closed=false,
 published_batch_id=EXCLUDED.published_batch_id,updated_at=current_timestamp;
 UPDATE etl_control.mart_batch SET status='APPLIED',applied_at=current_timestamp WHERE batch_id=v_batch;
 INSERT INTO etl_control.mart_delivery_receipt(stream_id,batch_sequence,batch_id,payload)
 VALUES(v_stream,v_seq,v_batch,p_delivery);
 INSERT INTO etl_control.mart_delivery_cursor(singleton,stream_id,last_sequence)
 VALUES(true,v_stream,v_seq) ON CONFLICT(singleton) DO UPDATE SET last_sequence=EXCLUDED.last_sequence;
 RETURN jsonb_build_object('stream_id',v_stream,'sequence',v_seq)::text;
END $$;
REVOKE ALL ON FUNCTION etl_control.apply_mart_delivery(jsonb) FROM PUBLIC;
CREATE FUNCTION etl_control.confirm_mart_delivery(p_receipt jsonb) RETURNS text
LANGUAGE plpgsql STABLE AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM etl_control.mart_delivery_receipt r
 JOIN etl_control.mart_batch b USING(batch_id)
 WHERE r.stream_id=p_receipt->>'stream_id' AND r.batch_sequence=(p_receipt->>'sequence')::bigint
 AND b.status='APPLIED') THEN
  RAISE EXCEPTION 'Mart receipt is not committed; staging must not be acknowledged';
 END IF;
 RETURN p_receipt::text;
END $$;
REVOKE ALL ON FUNCTION etl_control.confirm_mart_delivery(jsonb) FROM PUBLIC;
COMMIT;
