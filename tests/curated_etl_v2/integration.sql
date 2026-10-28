\set ON_ERROR_STOP on
SET client_min_messages=warning;
DO $$ BEGIN
 IF current_database()<>'staging_bkd_etl_v2_test_20261028' THEN RAISE EXCEPTION 'Isolated test DB only'; END IF;
END $$;
CREATE OR REPLACE FUNCTION public.assert_true(ok boolean,msg text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'ASSERT: %',msg; END IF; END $$;
CREATE OR REPLACE FUNCTION public.today() RETURNS date LANGUAGE sql AS $$SELECT (current_timestamp AT TIME ZONE 'Asia/Jakarta')::date$$;
INSERT INTO raw.raw_departemen(id,nama_departemen,extracted_at,pipeline_run_id) VALUES(10,'TEST',now(),'TEST');
INSERT INTO raw.raw_pegawai(id,departemen,status,extracted_at,pipeline_run_id)
VALUES(1,10,1,now(),'TEST'),(2,10,1,now(),'TEST'),(3,10,5,now(),'TEST'),(4,NULL,99,now(),'TEST');
INSERT INTO raw.raw_shift(id,nama,status,extracted_at,pipeline_run_id)
VALUES(10,'PAGI',false,now(),'TEST'),(20,'SIANG',true,now(),'TEST'),(30,'MALAM',true,now(),'TEST');
INSERT INTO raw.raw_jadwal(id,jenis,jam_masuk,jam_keluar,extracted_at,pipeline_run_id)
VALUES(100,10,'07:00','14:00',now(),'TEST'),(200,20,'14:00','21:00',now(),'TEST'),(300,30,'19:00','07:00',now(),'TEST');
INSERT INTO raw.raw_tipe_ijin(id,nama,extracted_at,pipeline_run_id) VALUES(1,'TEST',now(),'TEST');
INSERT INTO raw.raw_jenis_ijin(id,nama,tipe_id,setengah_hari,extracted_at,pipeline_run_id)
VALUES(1,'FULL',1,false,now(),'TEST'),(2,'PARTIAL',1,true,now(),'TEST');
INSERT INTO raw.raw_user(id,pegawai_id,extracted_at,pipeline_run_id) VALUES(1,1,now(),'TEST'),(2,2,now(),'TEST');
SELECT etl_control.enqueue_curated_batch('population',p_snapshot_date=>today(),p_snapshot_complete=>true);
SELECT etl_control.apply_curated_batch('population');
SELECT assert_true((SELECT count(*)=4 AND sum(active_employee_days)=2 AND sum(no_checkin_days)=2
 FROM curated.cur_attendance_daily),'population without any events, unknown and inactive');

INSERT INTO raw.raw_checkinout(id,pegawai_id,created_at,checktype,work_code,jadwal_id,is_manual,extracted_at,pipeline_run_id)
VALUES(1,1,today()+time '07:00',1,10,100,false,now(),'TEST'),
(2,1,today()+time '14:05',2,10,100,false,now(),'TEST'),
(3,1,today()+time '14:00',1,20,200,true,now(),'TEST'),
(4,1,today()+time '21:00',2,20,200,false,now(),'TEST');
SELECT etl_control.enqueue_curated_batch('events',ARRAY[1,2,3,4]);
SELECT etl_control.apply_curated_batch('events');
SELECT assert_true((SELECT checkin_days=1 AND checkout_days=1 AND checkin_event_count=2
 AND first_checkin_at=today()+time '07:00' AND last_checkout_at=today()+time '21:00'
 FROM curated.cur_attendance_daily WHERE pegawai_id=1 AND tanggal=today()),'multi-shift all names/statuses');
CREATE TEMP TABLE unchanged AS SELECT pegawai_id,tanggal,xmin::text version FROM curated.cur_attendance_daily;
SELECT etl_control.apply_curated_batch('events');
SELECT etl_control.enqueue_curated_batch('noop',ARRAY[1,2,3,4],p_snapshot_date=>today(),p_snapshot_complete=>true);
SELECT etl_control.apply_curated_batch('noop');
SELECT assert_true(NOT EXISTS(SELECT 1 FROM unchanged x JOIN curated.cur_attendance_daily d USING(pegawai_id,tanggal)
 WHERE x.version<>d.xmin::text),'no-op reprocessing performs no fact updates');
SELECT assert_true((SELECT (result->>'affected_employee_dates')::integer=0 FROM etl_control.curated_batch WHERE batch_id='noop'),'no dirty keys on no-op');

-- Correct one event into another employee and date, then remove the remaining checkout.
UPDATE raw.raw_checkinout SET pegawai_id=2,created_at=today()-1+time '21:00' WHERE id=4;
SELECT etl_control.enqueue_curated_batch('move',ARRAY[4]);
SELECT etl_control.apply_curated_batch('move');
SELECT assert_true((SELECT last_checkout_at=today()+time '14:05' FROM curated.cur_attendance_daily WHERE pegawai_id=1 AND tanggal=today()),'old date recomputed from all remaining events');
SELECT assert_true((SELECT checkout_event_count=1 AND active_employee_days=0 AND perlu_review
 FROM curated.cur_attendance_daily WHERE pegawai_id=2 AND tanggal=today()-1),'new historical date has unknown population');
DELETE FROM raw.raw_checkinout WHERE id=2;
SELECT etl_control.enqueue_curated_batch('delete',p_deleted_event_ids=>ARRAY[2]);
SELECT etl_control.apply_curated_batch('delete');
SELECT assert_true((SELECT checkout_days=0 AND no_checkout_days=1 FROM curated.cur_attendance_daily
 WHERE pegawai_id=1 AND tanggal=today()),'delete last checkout clears old flag');

-- Missing raw input rolls back everything and leaves READY for retry.
SELECT etl_control.enqueue_curated_batch('failure',ARRAY[999]);
DO $$ BEGIN
 BEGIN PERFORM etl_control.apply_curated_batch('failure'); RAISE EXCEPTION 'unexpected success';
 EXCEPTION WHEN raise_exception THEN
  IF SQLERRM='unexpected success' THEN RAISE; END IF;
 END;
END $$;
SELECT assert_true((SELECT status='READY' FROM etl_control.curated_batch WHERE batch_id='failure'),'failed batch retryable');
INSERT INTO raw.raw_checkinout(id,pegawai_id,created_at,checktype,extracted_at,pipeline_run_id)
VALUES(999,2,today()+time '08:00',1,now(),'TEST');
SELECT etl_control.apply_curated_batch('failure');
SELECT assert_true((SELECT checkin_days=1 AND perlu_review FROM curated.cur_attendance_daily
 WHERE pegawai_id=2 AND tanggal=today()),'missing schedule checkin retained');

-- Night check-out unresolved; same-day checkin contributes, no invented pairing.
INSERT INTO raw.raw_checkinout(id,pegawai_id,created_at,checktype,work_code,jadwal_id,extracted_at,pipeline_run_id)
VALUES(5,1,today()+time '19:00',1,30,300,now(),'TEST'),(6,1,today()+1+time '07:00',2,30,300,now(),'TEST');
SELECT etl_control.enqueue_curated_batch('night',ARRAY[5,6]);
SELECT etl_control.apply_curated_batch('night');
SELECT assert_true((SELECT tanggal IS NULL AND date_assignment_status='UNRESOLVED'
 FROM curated.cur_event_attendance WHERE checkinout_id_sumber=6),'overnight checkout stays unresolved');
SELECT assert_true((SELECT NOT is_date_final AND perlu_review FROM curated.cur_attendance_daily
 WHERE pegawai_id=1 AND tanggal=today()+1),'unresolved calendar date marked provisional');

INSERT INTO raw.raw_perizinan(id,pegawai_id,user_id,jenis_ijin,approval,tgl_ijin,tgl_ijin_sampai,extracted_at,pipeline_run_id)
VALUES(1,2,2,1,true,today(),today()+2,now(),'TEST'),(2,2,2,2,true,today(),today(),now(),'TEST');
SELECT etl_control.enqueue_curated_batch('leave',p_leave_ids=>ARRAY[1,2]);
SELECT etl_control.apply_curated_batch('leave');
SELECT assert_true((SELECT leave_days=1 AND has_full_day_leave AND has_partial_day_leave
 AND checkout_days=0 AND no_checkout_days=1 FROM curated.cur_attendance_daily
 WHERE pegawai_id=2 AND tanggal=today()),'overlap leave counted once and does not erase absence flags');
UPDATE raw.raw_perizinan SET tgl_ijin_sampai=today() WHERE id=1;
UPDATE raw.raw_perizinan SET approval=false WHERE id=2;
SELECT etl_control.enqueue_curated_batch('leave_shrink',p_leave_ids=>ARRAY[1,2]);
SELECT etl_control.apply_curated_batch('leave_shrink');
SELECT assert_true(NOT EXISTS(SELECT 1 FROM curated.cur_attendance_daily WHERE pegawai_id=2 AND tanggal>today()),'shortened leave removes stale old dates');
UPDATE raw.raw_perizinan SET approval=false WHERE id=1;
SELECT etl_control.enqueue_curated_batch('leave_revoke',p_leave_ids=>ARRAY[1]);
SELECT etl_control.apply_curated_batch('leave_revoke');
SELECT assert_true((SELECT leave_days=0 AND NOT has_valid_leave FROM curated.cur_attendance_daily
 WHERE pegawai_id=2 AND tanggal=today()),'approval revocation recomputes without events');
-- Invalid dates are audited without generating bad daily rows.
UPDATE raw.raw_perizinan SET tgl_ijin_sampai=today()-1 WHERE id=1;
SELECT etl_control.enqueue_curated_batch('invalid_leave',p_leave_ids=>ARRAY[1]);
SELECT etl_control.apply_curated_batch('invalid_leave');
SELECT assert_true((SELECT review_reason LIKE '%INVALID_RANGE%' FROM etl_control.curated_leave_state
 WHERE perizinan_id_sumber=1),'invalid leave audit');

UPDATE raw.raw_pegawai SET status=5 WHERE id=2;
SELECT etl_control.enqueue_curated_batch('deactivate',p_snapshot_date=>today(),p_snapshot_complete=>true);
SELECT etl_control.apply_curated_batch('deactivate');
SELECT assert_true((SELECT active_employee_days=0 AND checkin_days=0 AND checkin_event_count=1
 FROM curated.cur_attendance_daily WHERE pegawai_id=2 AND tanggal=today()),'population change updates KPI without changing evidence');
SELECT assert_true(NOT EXISTS(SELECT 1 FROM curated.cur_attendance_daily
 WHERE active_employee_days<>checkin_days+no_checkin_days
 OR active_employee_days<>checkout_days+no_checkout_days),'all complement identities');
DO $$ BEGIN
 BEGIN INSERT INTO etl_control.curated_batch_item VALUES('events','EVENT',9,'UPSERT');
 RAISE EXCEPTION 'unexpected success';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='unexpected success' THEN RAISE; END IF; END;
END $$;
SELECT etl_control.enqueue_curated_batch('historical_snapshot',p_snapshot_date=>today()-1,p_snapshot_complete=>true);
DO $$ BEGIN
 BEGIN PERFORM etl_control.apply_curated_batch('historical_snapshot'); RAISE EXCEPTION 'unexpected success';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='unexpected success' THEN RAISE; END IF; END;
END $$;
SELECT 'PASS: incremental, two shifts, no-op xmin, correction, deletion, retry, overnight review, leave shrink/revoke, population changes, manifest immutability, historical guard' result;

-- Fail after curated event write to prove transaction rolls back outputs and batch marker.
CREATE FUNCTION public.fail_daily_for_test() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'INJECTED_DAILY_FAILURE'; END $$;
CREATE TRIGGER injected_failure BEFORE UPDATE ON curated.cur_attendance_daily
FOR EACH ROW EXECUTE FUNCTION public.fail_daily_for_test();
UPDATE raw.raw_checkinout SET created_at=today()+time '06:30' WHERE id=1;
SELECT etl_control.enqueue_curated_batch('late_failure',ARRAY[1]);
DO $$ BEGIN
 BEGIN PERFORM etl_control.apply_curated_batch('late_failure'); RAISE EXCEPTION 'unexpected success';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'INJECTED_DAILY_FAILURE' THEN RAISE; END IF; END;
END $$;
SELECT assert_true((SELECT waktu_event=today()+time '07:00' FROM curated.cur_event_attendance
 WHERE checkinout_id_sumber=1),'event write rolled back after downstream failure');
SELECT assert_true((SELECT status='READY' FROM etl_control.curated_batch WHERE batch_id='late_failure'),'downstream failure leaves retryable marker');
DROP TRIGGER injected_failure ON curated.cur_attendance_daily;
SELECT etl_control.apply_curated_batch('late_failure');
SELECT assert_true((SELECT first_checkin_at=today()+time '06:30' FROM curated.cur_attendance_daily
 WHERE pegawai_id=1 AND tanggal=today()),'retry after downstream rollback');
-- Remove only deliberately rejected, unapplied test batch to exercise queue wrapper.
DELETE FROM etl_control.curated_batch WHERE batch_id='historical_snapshot';
SELECT etl_control.enqueue_curated_batch('queue_noop');
SELECT etl_control.apply_next_curated_batch();
SELECT assert_true((SELECT status='APPLIED' FROM etl_control.curated_batch WHERE batch_id='queue_noop'),'queue entrypoint');
SELECT assert_true(etl_control.apply_next_curated_batch()->>'status'='EMPTY','empty queue');
SELECT 'PASS: downstream atomic rollback, retry, queue wrapper' result;
