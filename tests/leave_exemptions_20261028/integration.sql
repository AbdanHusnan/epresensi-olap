\set ON_ERROR_STOP on
SET client_min_messages=warning;
DO $$ BEGIN
 IF current_database()<>'staging_bkd_leave_v3_test_20261028' THEN
   RAISE EXCEPTION 'Dedicated synthetic database only';
 END IF;
END $$;
CREATE FUNCTION public.today() RETURNS date LANGUAGE sql AS
$$ SELECT (current_timestamp AT TIME ZONE 'Asia/Jakarta')::date $$;
CREATE FUNCTION public.assert_true(ok boolean,msg text) RETURNS void LANGUAGE plpgsql AS
$$ BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'ASSERT: %',msg; END IF; END $$;
INSERT INTO raw.raw_departemen(id,extracted_at,pipeline_run_id) VALUES(10,now(),'TEST');
INSERT INTO raw.raw_pegawai(id,departemen,status,extracted_at,pipeline_run_id)
SELECT n,10,CASE WHEN n=12 THEN 5 ELSE 1 END,now(),'TEST' FROM generate_series(1,15) n;
INSERT INTO raw.raw_user(id,pegawai_id,extracted_at,pipeline_run_id)
SELECT n,n,now(),'TEST' FROM generate_series(1,15) n;
INSERT INTO raw.raw_shift(id,nama,status,extracted_at,pipeline_run_id)
VALUES(100,'TEST SHIFT',true,now(),'TEST');
INSERT INTO raw.raw_jadwal(id,jenis,jam_masuk,jam_keluar,extracted_at,pipeline_run_id)
VALUES(1000,100,'07:00','16:00',now(),'TEST');
INSERT INTO raw.raw_tipe_ijin(id,nama,extracted_at,pipeline_run_id)
VALUES(4,'MASTER_CATEGORY_NOT_TRANSACTION_TYPE',now(),'TEST');
INSERT INTO raw.raw_jenis_ijin(id,nama,tipe_id,setengah_hari,extracted_at,pipeline_run_id)
VALUES(10,'MASTER_FULL',4,false,now(),'TEST'),(11,'MASTER_PARTIAL',4,true,now(),'TEST');
SELECT etl_control.enqueue_curated_batch('POP',p_snapshot_date=>today(),p_snapshot_complete=>true);
SELECT etl_control.apply_curated_batch('POP');

INSERT INTO raw.raw_checkinout(id,pegawai_id,created_at,checktype,work_code,jadwal_id,extracted_at,pipeline_run_id)
VALUES(1,3,today()+time '16:00',2,100,1000,now(),'TEST'),
      (2,4,today()+time '07:00',1,100,1000,now(),'TEST'),
      (3,7,today()+time '07:00',1,100,1000,now(),'TEST'),
      (4,7,today()+time '16:00',2,100,1000,now(),'TEST');
INSERT INTO raw.raw_perizinan(id,pegawai_id,user_id,jenis_ijin,tipe_ijin,approval,tgl_ijin,tgl_ijin_sampai,extracted_at,pipeline_run_id)
SELECT id,emp,emp,kind,typ,approved,today(),today(),now(),'TEST'
FROM (VALUES (2,2,10,1,true),(3,3,10,2,true),(4,4,11,3,true),
 (5,5,11,2,true),(6,6,11,3,true),(7,7,10,1,true),
 (8,8,11,2,true),(80,8,11,3,true),
 (9,9,11,1,true),(90,9,11,2,true),
 (10,10,10,1,false),(11,11,11,99,true),(12,12,10,1,true),
 (13,13,10,NULL::integer,true),(14,14,10,1,true),(15,15,10,1,true)
) x(id,emp,kind,typ,approved);
UPDATE raw.raw_perizinan SET user_id=1 WHERE id=14;
UPDATE raw.raw_perizinan SET tgl_ijin_sampai=today()-1 WHERE id=15;
SELECT etl_control.enqueue_curated_batch('INITIAL',ARRAY[1,2,3,4],
 ARRAY[2,3,4,5,6,7,8,80,9,90,10,11,12,13,14,15]);
SELECT etl_control.apply_curated_batch('INITIAL');
CREATE TABLE public.expected_initial(emp integer,ci integer,co integer,nci integer,nco integer,
 eci integer,eco integer,izin integer);
INSERT INTO public.expected_initial VALUES
 (1,0,0,1,1,0,0,0),(2,0,0,0,0,1,1,1),
 (3,0,1,0,0,1,0,1),(4,1,0,0,0,0,1,1),
 (5,0,0,0,1,1,0,1),(6,0,0,1,0,0,1,1),
 (7,1,1,0,0,1,1,1),(8,0,0,0,0,1,1,1),(9,0,0,0,0,1,1,1),
 (10,0,0,1,1,0,0,0),(11,0,0,1,1,0,0,0),
 (12,0,0,0,0,0,0,0),(13,0,0,1,1,0,0,0),
 (14,0,0,1,1,0,0,0),(15,0,0,1,1,0,0,0);
SELECT assert_true(NOT EXISTS(
 SELECT 1 FROM public.expected_initial e LEFT JOIN curated.cur_attendance_daily d
 ON d.pegawai_id=e.emp AND d.tanggal=today()
 WHERE ROW(d.checkin_days,d.checkout_days,d.no_checkin_days,d.no_checkout_days,
 d.excused_checkin_days,d.excused_checkout_days,d.leave_days)
 IS DISTINCT FROM ROW(e.ci,e.co,e.nci,e.nco,e.eci,e.eco,e.izin)),
 '15 cases: full, each partial side with/without event, overlap, rejected/unknown/invalid, inactive');
SELECT assert_true((SELECT is_partial_day_leave AND NOT is_full_day_leave
 AND tipe_ijin_sumber=2 AND tipe_izin_id_sumber=4 AND setengah_hari_jenis_sumber=false
 FROM curated.cur_leave_daily WHERE perizinan_id_sumber=3),
 'transaction code overrides master half-day flag; category ID remains separate');
SELECT assert_true((SELECT is_full_day_leave AND setengah_hari_jenis_sumber=true
 FROM curated.cur_leave_daily WHERE perizinan_id_sumber=9),'full transaction overrides partial master');
SELECT assert_true((SELECT checkin_days=1 AND checkout_days=1 AND required_checkin_present_days=0
 AND required_checkout_present_days=0 FROM curated.cur_attendance_daily WHERE pegawai_id=7),
 'full leave preserves evidence but excludes it from required-attendance numerator');
SELECT assert_true((SELECT bool_and(perlu_review AND NOT is_valid_leave)
 FROM curated.cur_leave_daily WHERE perizinan_id_sumber IN(11,13,14)),
 'unknown/null type and identity mismatch never exempt');
SELECT assert_true((SELECT review_reason LIKE '%INVALID_RANGE%' FROM etl_control.curated_leave_state
 WHERE perizinan_id_sumber=15),'invalid range remains audited');

-- Identical content and a new batch must not rewrite either daily or leave rows.
CREATE TEMP TABLE original_versions AS SELECT pegawai_id,tanggal,xmin::text version FROM curated.cur_attendance_daily;
SELECT etl_control.enqueue_curated_batch('NOOP',ARRAY[1,2,3,4],ARRAY[2,3,4,5,6,7,8,80,9,90,10,11,12,13,14,15]);
SELECT etl_control.apply_curated_batch('NOOP');
SELECT assert_true((SELECT (result->>'leave_changes')::integer=0
 AND (result->>'attendance_daily_changes')::integer=0 FROM etl_control.curated_batch WHERE batch_id='NOOP'),
 'unchanged leave is no-op');
SELECT assert_true(NOT EXISTS(SELECT 1 FROM original_versions v JOIN curated.cur_attendance_daily d
 USING(pegawai_id,tanggal) WHERE d.xmin::text<>v.version),'daily versions unchanged');

-- Change ONLY tipe_ijin: timestamps and master category remain unchanged.
UPDATE raw.raw_perizinan SET tipe_ijin=3 WHERE id=5;
SELECT etl_control.enqueue_curated_batch('TYPE_ONLY',p_leave_ids=>ARRAY[5]);
SELECT etl_control.apply_curated_batch('TYPE_ONLY');
SELECT assert_true((SELECT no_checkin_days=1 AND no_checkout_days=0
 AND NOT has_excused_checkin AND has_excused_checkout FROM curated.cur_attendance_daily WHERE pegawai_id=5),
 'type-only update reverses exemption without event changes');
UPDATE raw.raw_perizinan SET approval=false WHERE id=2;
SELECT etl_control.enqueue_curated_batch('REVOKE',p_leave_ids=>ARRAY[2]);
SELECT etl_control.apply_curated_batch('REVOKE');
SELECT assert_true((SELECT no_checkin_days=1 AND no_checkout_days=1 AND leave_days=0
 FROM curated.cur_attendance_daily WHERE pegawai_id=2),'revocation restores both requirements');
UPDATE raw.raw_perizinan SET approval=true WHERE id=10;
SELECT etl_control.enqueue_curated_batch('APPROVE',p_leave_ids=>ARRAY[10]);
SELECT etl_control.apply_curated_batch('APPROVE');
SELECT assert_true((SELECT no_checkin_days=0 AND no_checkout_days=0 AND leave_days=1
 FROM curated.cur_attendance_daily WHERE pegawai_id=10),'approval changes KPI without event');

-- Removing one half of overlap restores only that side.
DELETE FROM raw.raw_perizinan WHERE id=80;
SELECT etl_control.enqueue_curated_batch('DELETE_HALF',p_deleted_leave_ids=>ARRAY[80]);
SELECT etl_control.apply_curated_batch('DELETE_HALF');
SELECT assert_true((SELECT no_checkin_days=0 AND no_checkout_days=1 AND leave_days=1
 FROM curated.cur_attendance_daily WHERE pegawai_id=8),'overlap deletion recomputes remaining leave');

-- Range and identity corrections must rebuild old AND new employee/date keys.
UPDATE raw.raw_perizinan SET tgl_ijin_sampai=today()+1 WHERE id=6;
SELECT etl_control.enqueue_curated_batch('EXPAND',p_leave_ids=>ARRAY[6]);
SELECT etl_control.apply_curated_batch('EXPAND');
SELECT assert_true(EXISTS(SELECT 1 FROM curated.cur_leave_daily WHERE perizinan_id_sumber=6
 AND tanggal_izin=today()+1),'inclusive leave range');
UPDATE raw.raw_perizinan SET tgl_ijin_sampai=today(),pegawai_id=1,user_id=1 WHERE id=6;
SELECT etl_control.enqueue_curated_batch('MOVE_SHRINK',p_leave_ids=>ARRAY[6]);
SELECT etl_control.apply_curated_batch('MOVE_SHRINK');
SELECT assert_true((SELECT no_checkin_days=1 AND no_checkout_days=1 AND leave_days=0
 FROM curated.cur_attendance_daily WHERE pegawai_id=6 AND tanggal=today()),'old employee restored');
SELECT assert_true((SELECT no_checkin_days=1 AND no_checkout_days=0 AND leave_days=1
 FROM curated.cur_attendance_daily WHERE pegawai_id=1 AND tanggal=today()),'new employee exempted');
SELECT assert_true(NOT EXISTS(SELECT 1 FROM curated.cur_attendance_daily WHERE pegawai_id=6
 AND tanggal=today()+1),'removed range leaves no stale daily row');

-- Inject a downstream failure after leave has been changed; retry is atomic.
CREATE FUNCTION public.fail_daily() RETURNS trigger LANGUAGE plpgsql AS
$$ BEGIN RAISE EXCEPTION 'INJECTED_FAILURE'; END $$;
CREATE TRIGGER fail_daily BEFORE UPDATE ON curated.cur_attendance_daily
 FOR EACH ROW EXECUTE FUNCTION public.fail_daily();
UPDATE raw.raw_perizinan SET tipe_ijin=1 WHERE id=5;
SELECT etl_control.enqueue_curated_batch('ROLLBACK',p_leave_ids=>ARRAY[5]);
DO $$ BEGIN
 BEGIN
  PERFORM etl_control.apply_curated_batch('ROLLBACK');
  RAISE EXCEPTION 'Expected failure';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'INJECTED_FAILURE' THEN RAISE; END IF; END;
END $$;
SELECT assert_true((SELECT tipe_ijin_sumber=3 FROM curated.cur_leave_daily WHERE perizinan_id_sumber=5),
 'leave update rolled back with daily failure');
SELECT assert_true((SELECT status='READY' FROM etl_control.curated_batch WHERE batch_id='ROLLBACK'),
 'failed batch remains retryable');
DROP TRIGGER fail_daily ON curated.cur_attendance_daily;
SELECT etl_control.apply_curated_batch('ROLLBACK');
SELECT assert_true((SELECT has_full_day_leave AND no_checkin_days=0 AND no_checkout_days=0
 FROM curated.cur_attendance_daily WHERE pegawai_id=5),'retry applies full leave');
SELECT assert_true(NOT EXISTS(SELECT 1 FROM curated.cur_attendance_daily
 WHERE active_employee_days<>required_checkin_days+excused_checkin_days
 OR active_employee_days<>required_checkout_days+excused_checkout_days
 OR required_checkin_days<>required_checkin_present_days+no_checkin_days
 OR required_checkout_days<>required_checkout_present_days+no_checkout_days),
 'all revised KPI identities');
SELECT assert_true((SELECT result->>'replayed'='true' FROM
 (SELECT etl_control.apply_curated_batch('ROLLBACK') result) x),'applied retry no-op');
SELECT 'PASS: 15 initial cases, type-only correction, approval/revocation, overlap deletion, range/identity correction, no-op, rollback/retry and KPI identities' result;
