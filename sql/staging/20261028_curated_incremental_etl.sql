-- Atomic raw -> curated v2. Install with psql -v ON_ERROR_STOP=1.
-- SECURITY INVOKER: never embeds source credentials or connects to source DB.
BEGIN;
CREATE TABLE IF NOT EXISTS etl_control.curated_active_status (
 status_sumber integer PRIMARY KEY, label text NOT NULL, is_active boolean NOT NULL,
 evidence text NOT NULL
);
INSERT INTO etl_control.curated_active_status VALUES
 (1,'PNS',true,'Verified raw.raw_previleges in staging_bkd_test_20261027'),
 (2,'PTT',true,'Verified raw.raw_previleges in staging_bkd_test_20261027'),
 (3,'PPPK',true,'Verified raw.raw_previleges in staging_bkd_test_20261027'),
 (4,'PPPK Paruh Waktu',true,'Verified raw.raw_previleges in staging_bkd_test_20261027'),
 (5,'Non-Aktif',false,'Verified raw.raw_previleges in staging_bkd_test_20261027')
ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS etl_control.curated_batch (
 batch_id text PRIMARY KEY CHECK (batch_id ~ '^[A-Za-z0-9_-]{1,100}$'),
 snapshot_date date,
 snapshot_complete boolean NOT NULL DEFAULT false,
 status text NOT NULL DEFAULT 'READY' CHECK (status IN ('READY','APPLIED')),
 created_at timestamptz NOT NULL DEFAULT current_timestamp,
 applied_at timestamptz,
 result jsonb,
 CHECK (snapshot_date IS NULL OR snapshot_complete)
);
CREATE TABLE IF NOT EXISTS etl_control.curated_batch_item (
 batch_id text NOT NULL REFERENCES etl_control.curated_batch(batch_id),
 entity text NOT NULL CHECK (entity IN ('EVENT','LEAVE')),
 source_id integer NOT NULL,
 operation text NOT NULL CHECK (operation IN ('UPSERT','DELETE')),
 PRIMARY KEY(batch_id,entity,source_id)
);
CREATE TABLE IF NOT EXISTS etl_control.curated_leave_state (
 perizinan_id_sumber integer PRIMARY KEY,
 fingerprint jsonb NOT NULL,
 review_reason text,
 processed_at timestamptz NOT NULL DEFAULT current_timestamp
);
CREATE OR REPLACE FUNCTION etl_control.guard_curated_manifest()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE b text;
BEGIN
 b := CASE WHEN TG_OP='DELETE' THEN OLD.batch_id ELSE NEW.batch_id END;
 -- Manifest writers and consumers serialize on the parent row.
 PERFORM 1 FROM etl_control.curated_batch WHERE batch_id=b FOR UPDATE;
 IF EXISTS (SELECT 1 FROM etl_control.curated_batch WHERE batch_id=b AND status='APPLIED')
 THEN RAISE EXCEPTION 'Applied batch % is immutable',b; END IF;
 IF TG_OP='UPDATE' AND NEW.batch_id<>OLD.batch_id THEN
   RAISE EXCEPTION 'Cannot move manifest item between batches';
 END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
DROP TRIGGER IF EXISTS curated_manifest_guard ON etl_control.curated_batch_item;
CREATE TRIGGER curated_manifest_guard BEFORE INSERT OR UPDATE OR DELETE
 ON etl_control.curated_batch_item FOR EACH ROW EXECUTE FUNCTION etl_control.guard_curated_manifest();

CREATE OR REPLACE FUNCTION etl_control.enqueue_curated_batch(
 p_batch_id text,
 p_event_ids integer[] DEFAULT ARRAY[]::integer[],
 p_leave_ids integer[] DEFAULT ARRAY[]::integer[],
 p_deleted_event_ids integer[] DEFAULT ARRAY[]::integer[],
 p_deleted_leave_ids integer[] DEFAULT ARRAY[]::integer[],
 p_snapshot_date date DEFAULT NULL,
 p_snapshot_complete boolean DEFAULT false
) RETURNS text LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO etl_control.curated_batch(batch_id,snapshot_date,snapshot_complete)
 VALUES(p_batch_id,p_snapshot_date,p_snapshot_complete);
 INSERT INTO etl_control.curated_batch_item
 SELECT p_batch_id,'EVENT',id,'UPSERT' FROM (SELECT DISTINCT unnest(p_event_ids) id) x
 UNION ALL SELECT p_batch_id,'LEAVE',id,'UPSERT' FROM (SELECT DISTINCT unnest(p_leave_ids) id) x
 UNION ALL SELECT p_batch_id,'EVENT',id,'DELETE' FROM (SELECT DISTINCT unnest(p_deleted_event_ids) id) x
 UNION ALL SELECT p_batch_id,'LEAVE',id,'DELETE' FROM (SELECT DISTINCT unnest(p_deleted_leave_ids) id) x;
 RETURN p_batch_id;
END $$;

CREATE OR REPLACE FUNCTION etl_control.apply_curated_batch(p_batch_id text)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
 b etl_control.curated_batch%ROWTYPE;
 v_event integer:=0; v_leave integer:=0; v_population integer:=0;
 v_event_daily integer:=0; v_daily integer:=0; v_removed integer:=0;
 v_result jsonb;
BEGIN
 -- Consumers serialize; manifest raw writes must commit before READY consumption.
 PERFORM pg_advisory_xact_lock(hashtext('curated_population_v2_apply'));
 SELECT * INTO STRICT b FROM etl_control.curated_batch WHERE batch_id=p_batch_id FOR UPDATE;
 IF b.status='APPLIED' THEN RETURN b.result || jsonb_build_object('replayed',true); END IF;
 IF b.snapshot_date IS NOT NULL AND b.snapshot_date<>(current_timestamp AT TIME ZONE 'Asia/Jakarta')::date
 THEN RAISE EXCEPTION 'Daily population snapshot must be today in Asia/Jakarta; historical population requires an explicit separate policy'; END IF;
 IF b.snapshot_date IS NOT NULL AND EXISTS
 (SELECT 1 FROM curated.cur_attendance_daily WHERE tanggal=b.snapshot_date AND is_date_final)
 THEN RAISE EXCEPTION 'Population date is closed'; END IF;
 IF b.snapshot_date IS NOT NULL AND NOT EXISTS(SELECT 1 FROM raw.raw_pegawai)
 THEN RAISE EXCEPTION 'Cannot snapshot an empty employee master'; END IF;
 -- Bound one batch to known committed raw rows; prevent concurrent updates/deletes
 -- of requested raw rows while deriving curated. Also exclude raw TRUNCATE.
 LOCK TABLE raw.raw_checkinout,raw.raw_perizinan IN ACCESS SHARE MODE;
 LOCK TABLE raw.raw_jadwal,raw.raw_shift,raw.raw_user,raw.raw_jenis_ijin,raw.raw_tipe_ijin,raw.raw_departemen,
 etl_control.curated_active_status IN SHARE MODE;
 IF b.snapshot_date IS NOT NULL THEN LOCK TABLE raw.raw_pegawai IN SHARE MODE; END IF;
 PERFORM r.id FROM raw.raw_checkinout r JOIN etl_control.curated_batch_item i
  ON i.source_id=r.id AND i.entity='EVENT' AND i.batch_id=p_batch_id FOR SHARE OF r;
 PERFORM r.id FROM raw.raw_perizinan r JOIN etl_control.curated_batch_item i
  ON i.source_id=r.id AND i.entity='LEAVE' AND i.batch_id=p_batch_id FOR SHARE OF r;
 IF EXISTS (SELECT 1 FROM etl_control.curated_batch_item i
 LEFT JOIN raw.raw_checkinout r ON r.id=i.source_id
 WHERE i.batch_id=p_batch_id AND i.entity='EVENT'
 AND ((i.operation='UPSERT' AND r.id IS NULL) OR (i.operation='DELETE' AND r.id IS NOT NULL)))
 OR EXISTS (SELECT 1 FROM etl_control.curated_batch_item i
 LEFT JOIN raw.raw_perizinan r ON r.id=i.source_id
 WHERE i.batch_id=p_batch_id AND i.entity='LEAVE'
 AND ((i.operation='UPSERT' AND r.id IS NULL) OR (i.operation='DELETE' AND r.id IS NOT NULL)))
 THEN RAISE EXCEPTION 'Manifest operation conflicts with committed raw state'; END IF;

 DROP TABLE IF EXISTS pg_temp.cv2_affected,pg_temp.cv2_events,pg_temp.cv2_changed_event,
 pg_temp.cv2_population,pg_temp.cv2_changed_population,pg_temp.cv2_leave_input,
 pg_temp.cv2_changed_leave,pg_temp.cv2_event_daily,pg_temp.cv2_daily;
 CREATE TEMP TABLE cv2_affected(pegawai_id integer NOT NULL,tanggal date NOT NULL,
 PRIMARY KEY(pegawai_id,tanggal)) ON COMMIT DROP;
CREATE TEMP TABLE cv2_events (LIKE curated.cur_event_attendance INCLUDING DEFAULTS INCLUDING GENERATED) ON COMMIT DROP;
INSERT INTO cv2_events
(checkinout_id_sumber,pegawai_id,tanggal_event,waktu_event,checktype,departemen_id_event,
 jadwal_id_sumber,work_code_sumber,jam_masuk_sumber,jam_keluar_sumber,is_manual,is_wfh_sumber,
 event_updated_at,shift_id_sumber,nama_shift_snapshot,tanggal,date_assignment_status,
 date_assignment_reason,date_assignment_policy,perlu_review,alasan_review,source_snapshot_at)
SELECT r.id,r.pegawai_id,r.created_at::date,r.created_at,r.checktype,r.departemen,
 r.jadwal_id,r.work_code,r.jam_masuk,r.jam_keluar,r.is_manual,r.is_wfh,r.updated_at,
 j.jenis,s.nama,
 CASE WHEN a.unresolved THEN NULL ELSE r.created_at::date END,
 CASE WHEN a.unresolved THEN 'UNRESOLVED' ELSE 'PROVISIONAL' END,
 CASE WHEN r.pegawai_id IS NULL OR r.created_at IS NULL THEN 'MISSING_IDENTITY_OR_TIME'
      WHEN a.unresolved THEN 'CHECKOUT_OVERNIGHT_OR_SCHEDULE_UNKNOWN_PENDING_POLICY'
      ELSE 'CALENDAR_DATE_PENDING_DAY_CLOSE' END,
 CASE WHEN a.unresolved THEN NULL ELSE 'SAME_DAY_PROVISIONAL_V1' END,
 a.unresolved OR j.id IS NULL OR s.id IS NULL OR r.work_code IS DISTINCT FROM j.jenis,
 NULLIF(concat_ws(';',
   CASE WHEN a.unresolved THEN 'DATE_UNRESOLVED' END,
   CASE WHEN j.id IS NULL OR s.id IS NULL THEN 'SCHEDULE_REFERENCE_MISSING' END,
   CASE WHEN r.work_code IS DISTINCT FROM j.jenis THEN 'WORK_CODE_MISMATCH' END),'') ,r.extracted_at
FROM etl_control.curated_batch_item i JOIN raw.raw_checkinout r ON r.id=i.source_id
LEFT JOIN raw.raw_jadwal j ON j.id=r.jadwal_id LEFT JOIN raw.raw_shift s ON s.id=j.jenis
CROSS JOIN LATERAL (SELECT r.pegawai_id IS NULL OR r.created_at IS NULL OR
 (r.checktype=2 AND (COALESCE(r.jam_masuk,j.jam_masuk) IS NULL
                OR COALESCE(r.jam_keluar,j.jam_keluar) IS NULL
                OR COALESCE(r.jam_keluar,j.jam_keluar)<=COALESCE(r.jam_masuk,j.jam_masuk))) AS unresolved) a
WHERE i.batch_id=p_batch_id AND i.entity='EVENT' AND i.operation='UPSERT';
CREATE TEMP TABLE cv2_changed_event ON COMMIT DROP AS
SELECT n.checkinout_id_sumber id FROM cv2_events n
LEFT JOIN curated.cur_event_attendance o USING(checkinout_id_sumber)
WHERE (to_jsonb(n)-'source_snapshot_at') IS DISTINCT FROM (to_jsonb(o)-'source_snapshot_at')
UNION SELECT i.source_id FROM etl_control.curated_batch_item i
JOIN curated.cur_event_attendance e ON e.checkinout_id_sumber=i.source_id
WHERE i.batch_id=p_batch_id AND i.entity='EVENT' AND i.operation='DELETE';
SELECT count(*) INTO v_event FROM cv2_changed_event;
-- Include old and new keys, including calendar keys of unresolved events, so
-- moving/removing the last event cannot leave a stale positive daily flag.
INSERT INTO cv2_affected
SELECT pegawai_id,d FROM (
 SELECT e.pegawai_id,COALESCE(e.tanggal,e.tanggal_event) d
 FROM curated.cur_event_attendance e JOIN cv2_changed_event c ON c.id=e.checkinout_id_sumber
 UNION SELECT e.pegawai_id,COALESCE(e.tanggal,e.tanggal_event)
 FROM cv2_events e JOIN cv2_changed_event c ON c.id=e.checkinout_id_sumber
) x WHERE pegawai_id IS NOT NULL AND d IS NOT NULL ON CONFLICT DO NOTHING;
DELETE FROM curated.cur_event_attendance e USING etl_control.curated_batch_item i
WHERE i.batch_id=p_batch_id AND i.entity='EVENT' AND i.operation='DELETE'
AND e.checkinout_id_sumber=i.source_id;
INSERT INTO curated.cur_event_attendance AS dst (checkinout_id_sumber,pegawai_id,tanggal_event,waktu_event,checktype,departemen_id_event,jadwal_id_sumber,work_code_sumber,jam_masuk_sumber,jam_keluar_sumber,is_manual,is_wfh_sumber,event_updated_at,shift_id_sumber,nama_shift_snapshot,tanggal,date_assignment_status,date_assignment_reason,date_assignment_policy,paired_checkin_id_sumber,perlu_review,alasan_review,source_snapshot_at)
 SELECT checkinout_id_sumber,pegawai_id,tanggal_event,waktu_event,checktype,departemen_id_event,jadwal_id_sumber,work_code_sumber,jam_masuk_sumber,jam_keluar_sumber,is_manual,is_wfh_sumber,event_updated_at,shift_id_sumber,nama_shift_snapshot,tanggal,date_assignment_status,date_assignment_reason,date_assignment_policy,paired_checkin_id_sumber,perlu_review,alasan_review,source_snapshot_at FROM cv2_events
 ON CONFLICT (checkinout_id_sumber) DO UPDATE SET pegawai_id=EXCLUDED.pegawai_id,
 tanggal_event=EXCLUDED.tanggal_event,
 waktu_event=EXCLUDED.waktu_event,
 checktype=EXCLUDED.checktype,
 departemen_id_event=EXCLUDED.departemen_id_event,
 jadwal_id_sumber=EXCLUDED.jadwal_id_sumber,
 work_code_sumber=EXCLUDED.work_code_sumber,
 jam_masuk_sumber=EXCLUDED.jam_masuk_sumber,
 jam_keluar_sumber=EXCLUDED.jam_keluar_sumber,
 is_manual=EXCLUDED.is_manual,
 is_wfh_sumber=EXCLUDED.is_wfh_sumber,
 event_updated_at=EXCLUDED.event_updated_at,
 shift_id_sumber=EXCLUDED.shift_id_sumber,
 nama_shift_snapshot=EXCLUDED.nama_shift_snapshot,
 tanggal=EXCLUDED.tanggal,
 date_assignment_status=EXCLUDED.date_assignment_status,
 date_assignment_reason=EXCLUDED.date_assignment_reason,
 date_assignment_policy=EXCLUDED.date_assignment_policy,
 paired_checkin_id_sumber=EXCLUDED.paired_checkin_id_sumber,
 perlu_review=EXCLUDED.perlu_review,
 alasan_review=EXCLUDED.alasan_review,
 source_snapshot_at=EXCLUDED.source_snapshot_at
 WHERE (to_jsonb(dst)-'source_snapshot_at') IS DISTINCT FROM
       (to_jsonb(EXCLUDED)-'source_snapshot_at');

-- Snapshot population independently of presence. Compare business values so an
-- unchanged daily snapshot does not rewrite employee/day facts on every batch.
IF b.snapshot_date IS NOT NULL THEN
CREATE TEMP TABLE cv2_population (LIKE curated.cur_employee_population_daily INCLUDING DEFAULTS INCLUDING GENERATED) ON COMMIT DROP;
 INSERT INTO cv2_population
 (pegawai_id,tanggal,departemen_id,status_sumber,is_employee_active,population_basis,
 source_snapshot_at,source_updated_at,perlu_review,alasan_review)
 SELECT p.id,b.snapshot_date,p.departemen,p.status,a.is_active,'EXTRACTION_SNAPSHOT',
 p.extracted_at,p.updated_at,a.status_sumber IS NULL OR d.id IS NULL,
 NULLIF(concat_ws(';',CASE WHEN a.status_sumber IS NULL THEN 'UNKNOWN_ACTIVE_STATUS' END,
 CASE WHEN d.id IS NULL THEN 'DEPARTMENT_UNMAPPED' END),'')
 FROM raw.raw_pegawai p LEFT JOIN etl_control.curated_active_status a ON a.status_sumber=p.status
 LEFT JOIN raw.raw_departemen d ON d.id=p.departemen;
 CREATE TEMP TABLE cv2_changed_population ON COMMIT DROP AS
 SELECT COALESCE(n.pegawai_id,o.pegawai_id) pegawai_id,b.snapshot_date tanggal
 FROM cv2_population n FULL JOIN
 (SELECT * FROM curated.cur_employee_population_daily WHERE tanggal=b.snapshot_date) o
 USING(pegawai_id,tanggal)
 WHERE (to_jsonb(n)-'source_snapshot_at') IS DISTINCT FROM (to_jsonb(o)-'source_snapshot_at');
 SELECT count(*) INTO v_population FROM cv2_changed_population;
 INSERT INTO cv2_affected SELECT * FROM cv2_changed_population ON CONFLICT DO NOTHING;
 DELETE FROM curated.cur_employee_population_daily p WHERE p.tanggal=b.snapshot_date
 AND NOT EXISTS(SELECT 1 FROM cv2_population n WHERE n.pegawai_id=p.pegawai_id);
INSERT INTO curated.cur_employee_population_daily AS dst (pegawai_id,tanggal,departemen_id,status_sumber,is_employee_active,population_basis,source_snapshot_at,source_updated_at,perlu_review,alasan_review)
 SELECT pegawai_id,tanggal,departemen_id,status_sumber,is_employee_active,population_basis,source_snapshot_at,source_updated_at,perlu_review,alasan_review FROM cv2_population
 ON CONFLICT (pegawai_id,tanggal) DO UPDATE SET departemen_id=EXCLUDED.departemen_id,
 status_sumber=EXCLUDED.status_sumber,
 is_employee_active=EXCLUDED.is_employee_active,
 population_basis=EXCLUDED.population_basis,
 source_snapshot_at=EXCLUDED.source_snapshot_at,
 source_updated_at=EXCLUDED.source_updated_at,
 perlu_review=EXCLUDED.perlu_review,
 alasan_review=EXCLUDED.alasan_review
 WHERE (to_jsonb(dst)-'source_snapshot_at') IS DISTINCT FROM
       (to_jsonb(EXCLUDED)-'source_snapshot_at');
END IF;

-- Fingerprint each requested leave plus joined reference values. Invalid ranges
-- and missing identity remain visible in leave_state even if no daily expansion.
CREATE TEMP TABLE cv2_leave_input ON COMMIT DROP AS
SELECT r.*,u.pegawai_id user_pegawai_id,j.nama jenis_nama,j.setengah_hari,
 t.id tipe_id,t.nama tipe_nama,
 jsonb_build_object('pegawai_id',r.pegawai_id,'user_id',r.user_id,'departemen',r.departemen,
 'jenis_ijin',r.jenis_ijin,'tipe_ijin',r.tipe_ijin,'leave_contract','TRANSACTION_TYPE_V3',
 'approval',r.approval,'approval_at',r.approval_at,
 'tgl_ijin',r.tgl_ijin,'tgl_ijin_sampai',r.tgl_ijin_sampai,'updated_at',r.updated_at,
 'joined_jenis_id',j.id,'user_employee',u.pegawai_id,'jenis',j.nama,'partial',j.setengah_hari,
                    'type_id',t.id,'type_name',t.nama) fingerprint,
 NULLIF(concat_ws(';',
 CASE WHEN r.pegawai_id IS NULL THEN 'MISSING_EMPLOYEE' END,
 CASE WHEN r.user_id IS NOT NULL AND u.pegawai_id IS DISTINCT FROM r.pegawai_id THEN 'IDENTITY_MISMATCH' END,
 CASE WHEN r.tgl_ijin IS NULL OR COALESCE(r.tgl_ijin_sampai,r.tgl_ijin)<r.tgl_ijin THEN 'INVALID_RANGE' END,
 CASE WHEN r.tipe_ijin IS NULL OR r.tipe_ijin NOT IN (1,2,3) THEN 'UNKNOWN_LEAVE_TRANSACTION_TYPE' END,
 CASE WHEN j.id IS NULL OR t.id IS NULL THEN 'LEAVE_REFERENCE_MISSING' END),'') review_reason
FROM etl_control.curated_batch_item i JOIN raw.raw_perizinan r ON r.id=i.source_id
LEFT JOIN raw.raw_user u ON u.id=r.user_id
LEFT JOIN raw.raw_jenis_ijin j ON j.id=r.jenis_ijin
LEFT JOIN raw.raw_tipe_ijin t ON t.id=j.tipe_id
WHERE i.batch_id=p_batch_id AND i.entity='LEAVE' AND i.operation='UPSERT';
CREATE TEMP TABLE cv2_changed_leave ON COMMIT DROP AS
SELECT n.id FROM cv2_leave_input n LEFT JOIN etl_control.curated_leave_state o
ON o.perizinan_id_sumber=n.id WHERE n.fingerprint IS DISTINCT FROM o.fingerprint
UNION SELECT i.source_id FROM etl_control.curated_batch_item i
WHERE i.batch_id=p_batch_id AND i.entity='LEAVE' AND i.operation='DELETE'
AND (EXISTS(SELECT 1 FROM curated.cur_leave_daily d WHERE d.perizinan_id_sumber=i.source_id)
 OR EXISTS(SELECT 1 FROM etl_control.curated_leave_state s WHERE s.perizinan_id_sumber=i.source_id));
SELECT count(*) INTO v_leave FROM cv2_changed_leave;
INSERT INTO cv2_affected SELECT d.pegawai_id,d.tanggal_izin FROM curated.cur_leave_daily d
JOIN cv2_changed_leave c ON c.id=d.perizinan_id_sumber ON CONFLICT DO NOTHING;
DELETE FROM curated.cur_leave_daily d USING cv2_changed_leave c WHERE d.perizinan_id_sumber=c.id;
DELETE FROM etl_control.curated_leave_state d USING cv2_changed_leave c WHERE d.perizinan_id_sumber=c.id;
INSERT INTO curated.cur_leave_daily
(perizinan_id_sumber,pegawai_id,tanggal_izin,departemen_id_izin,jenis_izin_id_sumber,
 nama_jenis_izin,tipe_izin_id_sumber,nama_tipe_izin,tipe_ijin_sumber,setengah_hari_jenis_sumber,
 approval,approval_at,is_full_day_leave,
 is_partial_day_leave,is_valid_leave,perlu_review,alasan_review,source_updated_at,source_snapshot_at)
SELECT r.id,r.pegawai_id,g.d::date,r.departemen,r.jenis_ijin,r.jenis_nama,r.tipe_id,r.tipe_nama,
 r.tipe_ijin,r.setengah_hari,r.approval,r.approval_at,
 CASE WHEN r.tipe_ijin IN (1,2,3) THEN r.tipe_ijin=1 END,
 CASE WHEN r.tipe_ijin IN (1,2,3) THEN r.tipe_ijin IN (2,3) END,
 r.approval IS TRUE AND r.review_reason IS NULL,r.review_reason IS NOT NULL,
 r.review_reason,r.updated_at,r.extracted_at
FROM cv2_leave_input r JOIN cv2_changed_leave c ON c.id=r.id
CROSS JOIN LATERAL generate_series(r.tgl_ijin::timestamp,
 COALESCE(r.tgl_ijin_sampai,r.tgl_ijin)::timestamp,interval '1 day') g(d)
WHERE r.pegawai_id IS NOT NULL AND r.tgl_ijin IS NOT NULL;
INSERT INTO etl_control.curated_leave_state(perizinan_id_sumber,fingerprint,review_reason)
SELECT r.id,r.fingerprint,r.review_reason FROM cv2_leave_input r JOIN cv2_changed_leave c ON c.id=r.id;
INSERT INTO cv2_affected SELECT d.pegawai_id,d.tanggal_izin FROM curated.cur_leave_daily d
JOIN cv2_changed_leave c ON c.id=d.perizinan_id_sumber ON CONFLICT DO NOTHING;

CREATE TEMP TABLE cv2_event_daily (LIKE curated.cur_attendance_event_daily INCLUDING DEFAULTS INCLUDING GENERATED) ON COMMIT DROP;
INSERT INTO cv2_event_daily
(pegawai_id,tanggal,checkin_event_count,checkout_event_count,first_checkin_at,last_checkout_at,
 has_manual_event,schedule_count,shift_count,perlu_review,alasan_review,is_date_final,
 date_assignment_policy,source_snapshot_at)
SELECT e.pegawai_id,e.tanggal,count(*) FILTER(WHERE e.checktype=1),count(*) FILTER(WHERE e.checktype=2),
 min(e.waktu_event) FILTER(WHERE e.checktype=1),max(e.waktu_event) FILTER(WHERE e.checktype=2),
 bool_or(e.is_manual IS TRUE),count(DISTINCT e.jadwal_id_sumber),count(DISTINCT e.shift_id_sumber),
 bool_or(e.perlu_review),string_agg(DISTINCT e.alasan_review,';'),false,
 'SAME_DAY_PROVISIONAL_V1',max(e.source_snapshot_at)
FROM cv2_affected a JOIN curated.cur_event_attendance e
ON e.pegawai_id=a.pegawai_id AND e.tanggal=a.tanggal
WHERE e.checktype IN (1,2) GROUP BY e.pegawai_id,e.tanggal;
DELETE FROM curated.cur_attendance_event_daily d USING cv2_affected a
WHERE d.pegawai_id=a.pegawai_id AND d.tanggal=a.tanggal
AND NOT EXISTS(SELECT 1 FROM cv2_event_daily n WHERE n.pegawai_id=d.pegawai_id AND n.tanggal=d.tanggal);
GET DIAGNOSTICS v_removed=ROW_COUNT;
INSERT INTO curated.cur_attendance_event_daily AS dst (pegawai_id,tanggal,checkin_event_count,checkout_event_count,first_checkin_at,last_checkout_at,has_manual_event,schedule_count,shift_count,perlu_review,alasan_review,is_date_final,date_assignment_policy,source_snapshot_at)
 SELECT pegawai_id,tanggal,checkin_event_count,checkout_event_count,first_checkin_at,last_checkout_at,has_manual_event,schedule_count,shift_count,perlu_review,alasan_review,is_date_final,date_assignment_policy,source_snapshot_at FROM cv2_event_daily
 ON CONFLICT (pegawai_id,tanggal) DO UPDATE SET checkin_event_count=EXCLUDED.checkin_event_count,
 checkout_event_count=EXCLUDED.checkout_event_count,
 first_checkin_at=EXCLUDED.first_checkin_at,
 last_checkout_at=EXCLUDED.last_checkout_at,
 has_manual_event=EXCLUDED.has_manual_event,
 schedule_count=EXCLUDED.schedule_count,
 shift_count=EXCLUDED.shift_count,
 perlu_review=EXCLUDED.perlu_review,
 alasan_review=EXCLUDED.alasan_review,
 is_date_final=EXCLUDED.is_date_final,
 date_assignment_policy=EXCLUDED.date_assignment_policy,
 source_snapshot_at=EXCLUDED.source_snapshot_at
 WHERE (to_jsonb(dst)-'source_snapshot_at') IS DISTINCT FROM
       (to_jsonb(EXCLUDED)-'source_snapshot_at');
GET DIAGNOSTICS v_event_daily=ROW_COUNT;
v_event_daily:=v_event_daily+v_removed;

CREATE TEMP TABLE cv2_daily (LIKE curated.cur_attendance_daily INCLUDING DEFAULTS INCLUDING GENERATED) ON COMMIT DROP;
INSERT INTO cv2_daily
(pegawai_id,tanggal,departemen_id,is_employee_active,population_basis,checkin_event_count,
 checkout_event_count,first_checkin_at,last_checkout_at,has_manual_event,has_valid_leave,
 has_full_day_leave,has_partial_day_leave,has_excused_checkin,has_excused_checkout,
 perlu_review,alasan_review,is_date_final,
 date_assignment_policy,source_snapshot_at)
SELECT a.pegawai_id,a.tanggal,p.departemen_id,p.is_employee_active,p.population_basis,
 COALESCE(e.checkin_event_count,0),COALESCE(e.checkout_event_count,0),e.first_checkin_at,e.last_checkout_at,
 COALESCE(e.has_manual_event,false),COALESCE(l.valid,false),COALESCE(l.full_day,false),COALESCE(l.partial_day,false),
 COALESCE(l.excused_checkin,false),COALESCE(l.excused_checkout,false),
 p.pegawai_id IS NULL OR p.is_employee_active IS NULL OR COALESCE(p.perlu_review,false)
 OR COALESCE(e.perlu_review,false) OR COALESCE(l.review,false) OR u.n>0,
 NULLIF(concat_ws(';',p.alasan_review,e.alasan_review,l.reasons,
 CASE WHEN p.pegawai_id IS NULL THEN 'POPULATION_SNAPSHOT_MISSING' END,
 CASE WHEN p.is_employee_active IS NULL THEN 'ACTIVE_STATUS_UNKNOWN' END,
 CASE WHEN u.n>0 THEN 'UNRESOLVED_EVENT_ON_CALENDAR_DATE' END),''),false,
 'SAME_DAY_PROVISIONAL_V1',GREATEST(p.source_snapshot_at,e.source_snapshot_at,l.snapshot_at,u.snapshot_at)
FROM cv2_affected a
LEFT JOIN curated.cur_employee_population_daily p USING(pegawai_id,tanggal)
LEFT JOIN curated.cur_attendance_event_daily e USING(pegawai_id,tanggal)
LEFT JOIN LATERAL (
 SELECT count(*) n,bool_or(is_valid_leave) valid,
 bool_or(is_valid_leave AND is_full_day_leave) full_day,
 bool_or(is_valid_leave AND is_partial_day_leave) partial_day,
 bool_or(excuses_checkin) excused_checkin,bool_or(excuses_checkout) excused_checkout,
 bool_or(perlu_review) review,string_agg(DISTINCT alasan_review,';') reasons,
 max(source_snapshot_at) snapshot_at FROM curated.cur_leave_daily l
 WHERE l.pegawai_id=a.pegawai_id AND l.tanggal_izin=a.tanggal
) l ON true
LEFT JOIN LATERAL (
 SELECT count(*) n,max(source_snapshot_at) snapshot_at FROM curated.cur_event_attendance u
 WHERE u.pegawai_id=a.pegawai_id AND u.tanggal IS NULL AND u.tanggal_event=a.tanggal
) u ON true
WHERE p.pegawai_id IS NOT NULL OR e.pegawai_id IS NOT NULL OR l.n>0 OR u.n>0;
DELETE FROM curated.cur_attendance_daily d USING cv2_affected a
WHERE d.pegawai_id=a.pegawai_id AND d.tanggal=a.tanggal
AND NOT EXISTS(SELECT 1 FROM cv2_daily n WHERE n.pegawai_id=d.pegawai_id AND n.tanggal=d.tanggal);
GET DIAGNOSTICS v_removed=ROW_COUNT;
INSERT INTO curated.cur_attendance_daily AS dst (pegawai_id,tanggal,departemen_id,is_employee_active,population_basis,checkin_event_count,checkout_event_count,first_checkin_at,last_checkout_at,has_manual_event,has_valid_leave,has_full_day_leave,has_partial_day_leave,has_excused_checkin,has_excused_checkout,perlu_review,alasan_review,is_date_final,date_assignment_policy,source_snapshot_at)
 SELECT pegawai_id,tanggal,departemen_id,is_employee_active,population_basis,checkin_event_count,checkout_event_count,first_checkin_at,last_checkout_at,has_manual_event,has_valid_leave,has_full_day_leave,has_partial_day_leave,has_excused_checkin,has_excused_checkout,perlu_review,alasan_review,is_date_final,date_assignment_policy,source_snapshot_at FROM cv2_daily
 ON CONFLICT (pegawai_id,tanggal) DO UPDATE SET departemen_id=EXCLUDED.departemen_id,
 is_employee_active=EXCLUDED.is_employee_active,
 population_basis=EXCLUDED.population_basis,
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
 perlu_review=EXCLUDED.perlu_review,
 alasan_review=EXCLUDED.alasan_review,
 is_date_final=EXCLUDED.is_date_final,
 date_assignment_policy=EXCLUDED.date_assignment_policy,
 source_snapshot_at=EXCLUDED.source_snapshot_at
 WHERE (to_jsonb(dst)-'source_snapshot_at') IS DISTINCT FROM
       (to_jsonb(EXCLUDED)-'source_snapshot_at');
GET DIAGNOSTICS v_daily=ROW_COUNT;
v_daily:=v_daily+v_removed;
v_result:=jsonb_build_object('batch_id',p_batch_id,'event_changes',v_event,
 'leave_changes',v_leave,'population_changes',v_population,'event_daily_changes',v_event_daily,
 'attendance_daily_changes',v_daily,'affected_employee_dates',(SELECT count(*) FROM cv2_affected),
 'date_policy','SAME_DAY_PROVISIONAL_V1','leave_policy','TRANSACTION_TYPE_V3','replayed',false);
UPDATE etl_control.curated_batch SET status='APPLIED',applied_at=current_timestamp,result=v_result
WHERE batch_id=p_batch_id;
RETURN v_result;
END $$;
COMMENT ON FUNCTION etl_control.apply_curated_batch(text) IS
 'Atomic manifest-based raw-to-curated batch. Overnight/unknown checkout schedule unresolved; no final KPI claims. Re-enqueue IDs on reference changes. Raw deletes require explicit tombstones.';

CREATE INDEX IF NOT EXISTS event_unresolved_employee_calendar_idx
 ON curated.cur_event_attendance(pegawai_id,tanggal_event) WHERE tanggal IS NULL;
CREATE OR REPLACE FUNCTION etl_control.guard_curated_batch_header()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.status='APPLIED' THEN RAISE EXCEPTION 'Applied batch % is immutable',OLD.batch_id; END IF;
 IF TG_OP='UPDATE' AND OLD.batch_id<>NEW.batch_id THEN RAISE EXCEPTION 'Batch ID is immutable'; END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
DROP TRIGGER IF EXISTS curated_batch_header_guard ON etl_control.curated_batch;
CREATE TRIGGER curated_batch_header_guard BEFORE UPDATE OR DELETE ON etl_control.curated_batch
 FOR EACH ROW EXECUTE FUNCTION etl_control.guard_curated_batch_header();
CREATE OR REPLACE FUNCTION etl_control.apply_next_curated_batch()
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE v_id text;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('curated_population_v2_apply'));
 SELECT batch_id INTO v_id FROM etl_control.curated_batch WHERE status='READY'
 ORDER BY created_at,batch_id LIMIT 1 FOR UPDATE;
 IF v_id IS NULL THEN RETURN jsonb_build_object('status','EMPTY','replayed',false); END IF;
 RETURN etl_control.apply_curated_batch(v_id);
END $$;

COMMIT;
