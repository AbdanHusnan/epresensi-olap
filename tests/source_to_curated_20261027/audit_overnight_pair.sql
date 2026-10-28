-- Sampel 500.000 ID terbaru, disaring Agustus 2026; bukan cakupan populasi penuh.
-- Kandidat lintas malam, bukan aturan pairing produksi. Tidak mengekspor identitas pegawai.
BEGIN READ ONLY;
SET LOCAL statement_timeout='8min';
SET LOCAL work_mem='64MB';
SET LOCAL enable_nestloop=off;
SET LOCAL jit=off;
WITH recent AS MATERIALIZED (
 SELECT pegawai_id,departemen,created_at,checktype,jadwal_id,work_code,jam_masuk,jam_keluar,hari
 FROM t_checkinout ORDER BY id DESC LIMIT 500000
), e AS MATERIALIZED (
 SELECT t.pegawai_id,t.departemen,t.created_at,t.checktype,t.jadwal_id,t.work_code,
 t.jam_masuk,t.jam_keluar,t.hari,j.jenis shift_id,s.nama shift_name,
 j.hari master_day,j.jam_masuk master_in,j.jam_keluar master_out
 FROM recent t JOIN m_jadwal j ON j.id=t.jadwal_id JOIN m_shift s ON s.id=j.jenis
 WHERE t.created_at >= timestamp '2026-08-01' AND t.created_at < timestamp '2026-09-01'
 AND t.checktype IN (1,2)
), g AS MATERIALIZED (
 SELECT pegawai_id,departemen,shift_id,created_at::date d,max(shift_name) shift_name,
 count(*) FILTER(WHERE checktype=1) n_in,count(*) FILTER(WHERE checktype=2) n_out,
 min(created_at) FILTER(WHERE checktype=1) tin,min(created_at) FILTER(WHERE checktype=2) tout,
 min(jadwal_id) FILTER(WHERE checktype=1) jin,min(jadwal_id) FILTER(WHERE checktype=2) jout,
 bool_or(coalesce(jam_keluar,master_out)<coalesce(jam_masuk,master_in)) overnight,
 jsonb_agg(jsonb_build_object('at',created_at,'type',checktype,'schedule',jadwal_id,'work_code',work_code,
 'in',jam_masuk,'out',jam_keluar,'day',hari,'master_day',master_day) ORDER BY created_at) events
 FROM e GROUP BY pegawai_id,departemen,shift_id,created_at::date
), pairs AS MATERIALIZED (
 SELECT a.pegawai_id,a.departemen,a.shift_id,a.shift_name,a.d,a.tin,b.tout,a.jin,b.jout,
 a.events first_day,b.events next_day
 FROM g a JOIN g b ON a.pegawai_id=b.pegawai_id AND a.departemen=b.departemen AND a.shift_id=b.shift_id AND b.d=a.d+1
 WHERE a.d < date '2026-08-31' AND a.overnight AND a.n_in=1 AND b.n_out=1
 AND b.tout>a.tin AND b.tout-a.tin<=interval '24 hours'
)
SELECT 'summary',jsonb_build_object('candidate_pairs',count(*),'different_daily_schedule_id',count(*) FILTER(WHERE jin<>jout),'departments',count(DISTINCT departemen)) FROM pairs
UNION ALL SELECT 'sample',jsonb_build_object('department',departemen,'shift_id',shift_id,'shift',shift_name,'start_date',d,
 'in',tin,'out',tout,'in_schedule',jin,'out_schedule',jout,'first_day',first_day,'next_day',next_day)
FROM (SELECT * FROM pairs ORDER BY (jin<>jout) DESC,d,departemen,shift_id,pegawai_id LIMIT 3) x;
COMMIT;
