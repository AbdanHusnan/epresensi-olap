\set ON_ERROR_STOP on
BEGIN;
DO $$ BEGIN
 IF current_database()<>'staging_bkd_checkin_20261102' THEN RAISE EXCEPTION 'Isolated November check-in database only'; END IF;
END $$;
WITH definitions AS (
 SELECT c.*,c.j2 jid,c.n*10+2 eid FROM test_checkin.cohort c WHERE c.n%10 IN(6,7) AND c.j2 IS NOT NULL
 UNION ALL
 SELECT c.*,c.j1,c.n*10+3 FROM test_checkin.cohort c WHERE c.n%10=8 AND c.j1 IS NOT NULL
), ins AS (
 INSERT INTO raw.raw_checkinout
 (id,pegawai_id,departemen,checktype,created_at,updated_at,work_code,jadwal_id,hari,
  jam_masuk_awal,jam_masuk,jam_keluar,jam_keluar_akhir,flexible_time,is_manual,is_wfh,keterangan,extracted_at,pipeline_run_id)
 SELECT c.eid,c.emp,c.dep,1,
 DATE '2026-11-02'+CASE WHEN c.n%10=6 THEN j.jam_masuk+interval '1 second'
                       WHEN c.n%10=7 THEN j.jam_masuk-interval '1 second'
                       ELSE j.jam_masuk+interval '2 minutes' END,
 current_timestamp AT TIME ZONE 'Asia/Jakarta',j.jenis,j.id,j.hari,
 j.jam_masuk_awal,j.jam_masuk,j.jam_keluar,j.jam_keluar_akhir,j.flexible_time,false,0,
 'CHECKIN_ONLY_20261102:ADDITIONAL_CHECKIN',now(),'CHECKIN_ONLY_20261102'
 FROM definitions c JOIN raw.raw_jadwal j ON j.id=c.jid RETURNING id,pegawai_id
) INSERT INTO test_checkin.events SELECT id,pegawai_id,2 FROM ins;
SELECT etl_control.enqueue_curated_batch('CHECKIN_ONLY_20261102_LATER',
 p_event_ids=>(SELECT array_agg(id ORDER BY id) FROM test_checkin.events WHERE phase=2));
COMMIT;
