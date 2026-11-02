\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout='5s';
DO $$ BEGIN
 IF current_database()<>'staging_bkd_gradual_20261030' THEN RAISE EXCEPTION 'Isolated November check-in database only'; END IF;
END $$;
CREATE SCHEMA test_checkin;
CREATE TABLE test_checkin.cohort AS
WITH eligible AS MATERIALIZED (
 SELECT j.id,j.jenis,j.jam_masuk,s.departemen_id
 FROM raw.raw_jadwal j JOIN raw.raw_shift s ON s.id=j.jenis
 WHERE s.status IS TRUE AND lower(trim(j.hari)) IN ('fri','jumat','jum''at')
 AND j.jam_masuk_awal<=j.jam_masuk AND j.jam_masuk<>j.jam_keluar
 AND j.jam_masuk<=time '23:50' AND j.jam_keluar_akhir IS NOT NULL
), first_ids AS (
 SELECT departemen_id,(array_agg(id ORDER BY jam_masuk,jenis,id))[1] AS j1
 FROM eligible GROUP BY departemen_id
), schedules AS (
 SELECT f.departemen_id,f.j1,
  (SELECT e.id FROM eligible e WHERE e.departemen_id=f.departemen_id AND e.jam_masuk>j.jam_masuk
   ORDER BY e.jam_masuk,e.jenis,e.id LIMIT 1) AS j2
 FROM first_ids f JOIN eligible j ON j.id=f.j1
), users AS (SELECT pegawai_id,min(id) uid FROM raw.raw_user GROUP BY pegawai_id),
numbered AS (
 SELECT row_number() OVER(ORDER BY p.departemen NULLS LAST,p.id)::integer n,
        p.id emp,p.departemen dep,u.uid,s.j1,s.j2
 FROM raw.raw_pegawai p LEFT JOIN schedules s ON s.departemen_id=p.departemen
 LEFT JOIN users u ON u.pegawai_id=p.id WHERE p.status IN(1,2,3,4)
)
SELECT *,CASE WHEN uid IS NOT NULL AND n%23=0 THEN 'EXCUSED'
              WHEN j1 IS NULL THEN 'NOT_ASSESSED'
              WHEN n%10 IN (4,5,7,9) THEN 'LATE' ELSE 'ON_TIME' END::text AS expected_status
FROM numbered;
ALTER TABLE test_checkin.cohort ADD PRIMARY KEY(emp);
CREATE UNIQUE INDEX ON test_checkin.cohort(n);
CREATE TABLE test_checkin.events(id integer PRIMARY KEY,emp integer,phase integer);
CREATE TABLE test_checkin.leave_ids(id integer PRIMARY KEY,emp integer);

-- Explicit future-test population fixture using the current extraction snapshot.
-- This does not assert that current employee status is known to hold on Nov 2.
INSERT INTO curated.cur_employee_population_daily
(pegawai_id,tanggal,departemen_id,status_sumber,is_employee_active,population_basis,source_snapshot_at,source_updated_at)
SELECT p.id,DATE '2026-10-30',p.departemen,p.status,true,'EXTRACTION_SNAPSHOT',p.extracted_at,p.updated_at
FROM raw.raw_pegawai p WHERE p.status IN(1,2,3,4);
INSERT INTO curated.cur_attendance_daily
(pegawai_id,tanggal,departemen_id,is_employee_active,population_basis,lateness_status,lateness_reason,date_assignment_policy,source_snapshot_at)
SELECT emp,DATE '2026-10-30',dep,true,'EXTRACTION_SNAPSHOT','NOT_ASSESSED','NO_CHECKIN',
       'SIMULATION_SNAPSHOT_20261030',now() FROM test_checkin.cohort;

WITH ins AS (
 INSERT INTO raw.raw_checkinout
 (id,pegawai_id,departemen,checktype,created_at,updated_at,work_code,jadwal_id,hari,
  jam_masuk_awal,jam_masuk,jam_keluar,jam_keluar_akhir,flexible_time,is_manual,is_wfh,keterangan,extracted_at,pipeline_run_id)
 SELECT c.n*10+1,c.emp,c.dep,1,
  DATE '2026-10-30'+CASE
    WHEN c.n%10=0 THEN CASE WHEN j.jam_masuk_awal>time '00:00' THEN j.jam_masuk_awal-interval '1 second' ELSE j.jam_masuk_awal END
    WHEN c.n%10=1 THEN j.jam_masuk_awal
    WHEN c.n%10=2 THEN j.jam_masuk_awal+(j.jam_masuk-j.jam_masuk_awal)/2
    WHEN c.n%10 IN(3,8) THEN j.jam_masuk
    WHEN c.n%10 IN(4,7) THEN j.jam_masuk+interval '1 second'
    WHEN c.n%10=5 THEN j.jam_masuk+interval '5 minutes'
    WHEN c.n%10=6 THEN CASE WHEN j.jam_masuk>time '00:00' THEN j.jam_masuk-interval '1 second' ELSE j.jam_masuk END
    ELSE j.jam_masuk+interval '3 minutes' END,
  current_timestamp AT TIME ZONE 'Asia/Jakarta',j.jenis,j.id,j.hari,
  j.jam_masuk_awal,j.jam_masuk,j.jam_keluar,j.jam_keluar_akhir,j.flexible_time,false,0,
  'GRADUAL_20261030_BATCH1:FIRST',now(),'GRADUAL_20261030_BATCH1'
 FROM test_checkin.cohort c JOIN raw.raw_jadwal j ON j.id=c.j1
 RETURNING id,pegawai_id
) INSERT INTO test_checkin.events SELECT id,pegawai_id,1 FROM ins;

WITH ins AS (
 INSERT INTO raw.raw_perizinan
 (id,pegawai_id,user_id,departemen,jenis_ijin,tipe_ijin,approval,tgl_ijin,tgl_ijin_sampai,
  alasan,catatan,extracted_at,pipeline_run_id)
 SELECT 900000000+c.n,c.emp,c.uid,c.dep,
  (SELECT min(id) FROM raw.raw_jenis_ijin WHERE tipe_id IN (SELECT id FROM raw.raw_tipe_ijin)),
  2,true,DATE '2026-10-30',DATE '2026-10-30','GRADUAL_20261030_BATCH1','SIMULATED CHECKIN EXEMPTION',now(),'GRADUAL_20261030_BATCH1'
 FROM test_checkin.cohort c WHERE expected_status='EXCUSED'
 RETURNING id,pegawai_id
) INSERT INTO test_checkin.leave_ids SELECT id,pegawai_id FROM ins;
COMMIT;
