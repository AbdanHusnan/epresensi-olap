-- Install definitions only. No snapshot or delivery is executed by this file.
BEGIN;
SET LOCAL lock_timeout='5s';
SELECT pg_advisory_xact_lock(hashtext('curated_population_v2_apply'));
CREATE TABLE etl_control.mart_outbox_stream (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 stream_id text NOT NULL UNIQUE DEFAULT md5(random()::text || clock_timestamp()::text),
 last_sequence bigint NOT NULL DEFAULT 0,
 bootstrap_prepared boolean NOT NULL DEFAULT false
);
INSERT INTO etl_control.mart_outbox_stream(singleton) VALUES(true);
CREATE TABLE etl_control.mart_outbox_batch (
 batch_sequence bigint PRIMARY KEY,
 transaction_key text NOT NULL UNIQUE,
 kind text NOT NULL CHECK(kind IN ('BOOTSTRAP','DELTA')),
 created_at timestamptz NOT NULL DEFAULT current_timestamp,
 delivered_at timestamptz
);
CREATE TABLE etl_control.mart_outbox_item (
 batch_sequence bigint NOT NULL REFERENCES etl_control.mart_outbox_batch,
 pegawai_id integer NOT NULL,
 tanggal date NOT NULL,
 operation text NOT NULL CHECK(operation IN ('UPSERT','DELETE')),
 payload jsonb,
 PRIMARY KEY(batch_sequence,pegawai_id,tanggal),
 CHECK((operation='UPSERT')=(payload IS NOT NULL)),
 CHECK(payload IS NULL OR (payload->>'pegawai_id')::integer=pegawai_id),
 CHECK(payload IS NULL OR (payload->>'tanggal')::date=tanggal)
);
CREATE FUNCTION etl_control.new_mart_outbox_batch(p_transaction_key text,p_kind text)
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE v_seq bigint;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('curated_population_v2_apply'));
 SELECT batch_sequence INTO v_seq FROM etl_control.mart_outbox_batch WHERE transaction_key=p_transaction_key;
 IF FOUND THEN RETURN v_seq; END IF;
 UPDATE etl_control.mart_outbox_stream SET last_sequence=last_sequence+1
 WHERE singleton RETURNING last_sequence INTO v_seq;
 INSERT INTO etl_control.mart_outbox_batch(batch_sequence,transaction_key,kind)
 VALUES(v_seq,p_transaction_key,p_kind);
 RETURN v_seq;
END $$;
CREATE FUNCTION etl_control.lock_mart_outbox_writer() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('curated_population_v2_apply'));
 IF TG_OP='TRUNCATE' THEN RAISE EXCEPTION 'TRUNCATE curated daily is forbidden: use explicit keyed deletes for mart delivery'; END IF;
 RETURN NULL;
END $$;
CREATE FUNCTION etl_control.capture_mart_outbox() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_seq bigint;
BEGIN
 -- Transition tables avoid per-row trigger queries. Ignore snapshot timestamp-only updates.
 DROP TABLE IF EXISTS pg_temp.mart_capture_changes;
 CREATE TEMP TABLE mart_capture_changes(pegawai_id integer,tanggal date,operation text,payload jsonb) ON COMMIT DROP;
 IF TG_OP='INSERT' THEN
  INSERT INTO mart_capture_changes SELECT n.pegawai_id,n.tanggal,'UPSERT',to_jsonb(n) FROM new_daily n;
 ELSIF TG_OP='DELETE' THEN
  INSERT INTO mart_capture_changes SELECT o.pegawai_id,o.tanggal,'DELETE',NULL FROM old_daily o;
 ELSE
  INSERT INTO mart_capture_changes
  SELECT o.pegawai_id,o.tanggal,'DELETE',NULL FROM old_daily o
  WHERE NOT EXISTS(SELECT 1 FROM new_daily n WHERE (n.pegawai_id,n.tanggal)=(o.pegawai_id,o.tanggal));
  INSERT INTO mart_capture_changes
  SELECT n.pegawai_id,n.tanggal,'UPSERT',to_jsonb(n) FROM new_daily n
  LEFT JOIN old_daily o USING(pegawai_id,tanggal)
  WHERE o.pegawai_id IS NULL OR (to_jsonb(o)-'source_snapshot_at') IS DISTINCT FROM (to_jsonb(n)-'source_snapshot_at');
 END IF;
 IF NOT EXISTS(SELECT 1 FROM mart_capture_changes) THEN RETURN NULL; END IF;
 IF NOT (SELECT bootstrap_prepared FROM etl_control.mart_outbox_stream WHERE singleton) THEN
  RAISE EXCEPTION 'Prepare mart bootstrap explicitly before changing curated daily; downstream is not initialized';
 END IF;
 v_seq:=etl_control.new_mart_outbox_batch(txid_current()::text,'DELTA');
 INSERT INTO etl_control.mart_outbox_item
 SELECT v_seq,pegawai_id,tanggal,operation,payload FROM mart_capture_changes
 ON CONFLICT(batch_sequence,pegawai_id,tanggal) DO UPDATE
 SET operation=EXCLUDED.operation,payload=EXCLUDED.payload;
 RETURN NULL;
END $$;
-- Capture triggers are deliberately NOT enabled at install time. The explicit
-- bootstrap function enables them under the same lock and snapshots existing rows.
CREATE FUNCTION etl_control.prepare_mart_bootstrap() RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE d date; v_seq bigint; v_count integer:=0;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('curated_population_v2_apply'));
 LOCK TABLE curated.cur_attendance_daily IN SHARE ROW EXCLUSIVE MODE;
 IF (SELECT bootstrap_prepared FROM etl_control.mart_outbox_stream WHERE singleton)
 OR EXISTS(SELECT 1 FROM etl_control.mart_outbox_batch) THEN
  RAISE EXCEPTION 'Bootstrap already prepared; retry delivery, never rebuild stream silently';
 END IF;
 -- Hold one consistent source snapshot. One delivery per date bounds JSON size.
 FOR d IN SELECT DISTINCT tanggal FROM curated.cur_attendance_daily ORDER BY tanggal LOOP
  v_seq:=etl_control.new_mart_outbox_batch(txid_current()::text||':'||d::text,'BOOTSTRAP');
  INSERT INTO etl_control.mart_outbox_item
  SELECT v_seq,pegawai_id,tanggal,'UPSERT',to_jsonb(c) FROM curated.cur_attendance_daily c WHERE tanggal=d;
  v_count:=v_count+1;
 END LOOP;
 IF v_count=0 THEN
  v_seq:=etl_control.new_mart_outbox_batch(txid_current()::text||':empty','BOOTSTRAP');
 END IF;
 EXECUTE 'CREATE TRIGGER mart_outbox_lock BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON curated.cur_attendance_daily FOR EACH STATEMENT EXECUTE FUNCTION etl_control.lock_mart_outbox_writer()';
 EXECUTE 'CREATE TRIGGER mart_outbox_insert AFTER INSERT ON curated.cur_attendance_daily REFERENCING NEW TABLE AS new_daily FOR EACH STATEMENT EXECUTE FUNCTION etl_control.capture_mart_outbox()';
 EXECUTE 'CREATE TRIGGER mart_outbox_update AFTER UPDATE ON curated.cur_attendance_daily REFERENCING OLD TABLE AS old_daily NEW TABLE AS new_daily FOR EACH STATEMENT EXECUTE FUNCTION etl_control.capture_mart_outbox()';
 EXECUTE 'CREATE TRIGGER mart_outbox_delete AFTER DELETE ON curated.cur_attendance_daily REFERENCING OLD TABLE AS old_daily FOR EACH STATEMENT EXECUTE FUNCTION etl_control.capture_mart_outbox()';
 UPDATE etl_control.mart_outbox_stream SET bootstrap_prepared=true WHERE singleton;
 RETURN jsonb_build_object('dates',v_count,'last_sequence',v_seq);
END $$;
CREATE FUNCTION etl_control.next_mart_delivery() RETURNS TABLE(batch_payload text)
LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object('contract_version','ATTENDANCE_DAILY_V1',
 'stream_id',s.stream_id,'sequence',b.batch_sequence,'kind',b.kind,
 'items',COALESCE((SELECT jsonb_agg(jsonb_build_object('pegawai_id',i.pegawai_id,
 'tanggal',i.tanggal,'operation',i.operation,'payload',i.payload) ORDER BY i.tanggal,i.pegawai_id)
 FROM etl_control.mart_outbox_item i WHERE i.batch_sequence=b.batch_sequence),'[]'::jsonb))::text
 FROM etl_control.mart_outbox_stream s
 CROSS JOIN LATERAL(SELECT * FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL ORDER BY batch_sequence LIMIT 1) b
 WHERE s.bootstrap_prepared;
$$;
CREATE FUNCTION etl_control.ack_mart_delivery(p_receipt jsonb) RETURNS text LANGUAGE plpgsql AS $$
DECLARE v_stream text; v_seq bigint; v_next bigint;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('curated_population_v2_apply'));
 SELECT stream_id INTO v_stream FROM etl_control.mart_outbox_stream WHERE singleton;
 IF p_receipt->>'stream_id' IS DISTINCT FROM v_stream THEN RAISE EXCEPTION 'Receipt stream mismatch'; END IF;
 v_seq:=(p_receipt->>'sequence')::bigint;
 IF v_seq IS NULL OR NOT EXISTS(SELECT 1 FROM etl_control.mart_outbox_batch WHERE batch_sequence=v_seq) THEN
  RAISE EXCEPTION 'Unknown receipt sequence'; END IF;
 IF EXISTS(SELECT 1 FROM etl_control.mart_outbox_batch WHERE batch_sequence=v_seq AND delivered_at IS NOT NULL) THEN RETURN 'ALREADY_ACKNOWLEDGED'; END IF;
 SELECT min(batch_sequence) INTO v_next FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL;
 IF v_seq<>v_next THEN RAISE EXCEPTION 'Out-of-order acknowledgement'; END IF;
 UPDATE etl_control.mart_outbox_batch SET delivered_at=current_timestamp WHERE batch_sequence=v_seq;
 RETURN 'ACKNOWLEDGED';
END $$;
REVOKE ALL ON FUNCTION etl_control.prepare_mart_bootstrap() FROM PUBLIC;
REVOKE ALL ON FUNCTION etl_control.new_mart_outbox_batch(text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION etl_control.next_mart_delivery() FROM PUBLIC;
REVOKE ALL ON FUNCTION etl_control.ack_mart_delivery(jsonb) FROM PUBLIC;
CREATE FUNCTION etl_control.guard_mart_outbox_item() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE b etl_control.mart_outbox_batch%ROWTYPE;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Outbox items are retained for audit'; END IF;
 SELECT * INTO STRICT b FROM etl_control.mart_outbox_batch WHERE batch_sequence=NEW.batch_sequence;
 IF b.delivered_at IS NOT NULL OR split_part(b.transaction_key,':',1)<>txid_current()::text THEN
  RAISE EXCEPTION 'Committed outbox payload is immutable';
 END IF;
 IF TG_OP='UPDATE' AND (NEW.batch_sequence,NEW.pegawai_id,NEW.tanggal) IS DISTINCT FROM (OLD.batch_sequence,OLD.pegawai_id,OLD.tanggal) THEN
  RAISE EXCEPTION 'Cannot move outbox item key';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER mart_outbox_item_immutable BEFORE INSERT OR UPDATE OR DELETE ON etl_control.mart_outbox_item
FOR EACH ROW EXECUTE FUNCTION etl_control.guard_mart_outbox_item();
CREATE FUNCTION etl_control.guard_mart_outbox_header() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Outbox headers are retained for audit'; END IF;
 IF (to_jsonb(NEW)-'delivered_at') IS DISTINCT FROM (to_jsonb(OLD)-'delivered_at')
 OR OLD.delivered_at IS NOT NULL OR NEW.delivered_at IS NULL THEN
  RAISE EXCEPTION 'Only first delivery acknowledgement can change outbox header';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER mart_outbox_header_immutable BEFORE UPDATE OR DELETE ON etl_control.mart_outbox_batch
FOR EACH ROW EXECUTE FUNCTION etl_control.guard_mart_outbox_header();
COMMIT;
