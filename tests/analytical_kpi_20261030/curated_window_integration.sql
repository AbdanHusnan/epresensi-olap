\set ON_ERROR_STOP on
DO $$ BEGIN
 IF current_database() <> 'staging_bkd_window_test_20261030' THEN
  RAISE EXCEPTION 'Dedicated window test database only';
 END IF;
END $$;
INSERT INTO raw.raw_shift(id,nama,status,extracted_at,pipeline_run_id)
VALUES (100,'MORNING',true,now(),'WINDOW_TEST'),(101,'AFTERNOON',true,now(),'WINDOW_TEST');
INSERT INTO raw.raw_jadwal(id,jenis,jam_masuk,jam_keluar,extracted_at,pipeline_run_id)
VALUES (1000,100,'07:00','14:00',now(),'WINDOW_TEST'),(1001,101,'14:00','21:00',now(),'WINDOW_TEST');
INSERT INTO curated.cur_employee_population_daily(pegawai_id,tanggal,departemen_id,is_employee_active,population_basis,source_snapshot_at)
SELECT id,DATE '2026-08-03',10,true,'AS_OF_DATE_SNAPSHOT',now() FROM generate_series(1,4) id;
INSERT INTO raw.raw_checkinout(id,pegawai_id,created_at,checktype,work_code,jadwal_id,jam_masuk_awal,jam_masuk,jam_keluar,jam_keluar_akhir,extracted_at,pipeline_run_id)
VALUES
 (1,1,'2026-08-03 06:55',1,100,1000,'06:00','07:00','14:00','15:00',now(),'WINDOW_TEST'),
 (2,1,'2026-08-03 14:10',1,101,1001,'13:00','14:00','21:00','22:00',now(),'WINDOW_TEST'),
 (3,2,'2026-08-03 07:05',1,100,1000,'06:00','07:00','14:00','15:00',now(),'WINDOW_TEST'),
 (4,2,'2026-08-03 13:55',1,101,1001,'13:00','14:00','21:00','22:00',now(),'WINDOW_TEST'),
 (5,3,'2026-08-03 05:55',1,100,1000,'06:00','07:00','14:00','15:00',now(),'WINDOW_TEST'),
 (6,4,'2026-08-03 07:10',1,100,1000,NULL,'07:00','14:00','15:00',now(),'WINDOW_TEST');
SELECT etl_control.enqueue_curated_batch('WINDOW_INITIAL',ARRAY[1,2,3,4,5,6]);
SELECT etl_control.apply_curated_batch('WINDOW_INITIAL');
DO $$ BEGIN
 IF (SELECT lateness_status FROM curated.cur_attendance_daily WHERE pegawai_id=1) <> 'ON_TIME'
 OR (SELECT lateness_status FROM curated.cur_attendance_daily WHERE pegawai_id=2) <> 'LATE'
 OR (SELECT lateness_status FROM curated.cur_attendance_daily WHERE pegawai_id=3) <> 'ON_TIME'
 OR (SELECT lateness_status FROM curated.cur_attendance_daily WHERE pegawai_id=4) <> 'UNKNOWN'
 OR (SELECT jam_keluar_akhir_sumber FROM curated.cur_event_attendance WHERE checkinout_id_sumber=1) <> time '15:00'
 THEN RAISE EXCEPTION 'Curated window integration failed'; END IF;
END $$;
SELECT 'first-shift and checkout-bound preservation passed' AS result;
