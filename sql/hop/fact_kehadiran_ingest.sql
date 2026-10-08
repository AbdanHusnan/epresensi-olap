CREATE OR REPLACE FUNCTION hop_etl.ingest_fact_events() RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET work_mem='128MB' AS $$
DECLARE st hop_etl.fact_checkpoint%ROWTYPE; hi bigint; total bigint; rejected bigint;
BEGIN
 IF NOT pg_try_advisory_xact_lock(781204991) THEN RAISE EXCEPTION 'Fact loader is already running'; END IF;
 SELECT * INTO STRICT st FROM hop_etl.fact_checkpoint WHERE singleton FOR UPDATE;
 IF st.phase<>'events' THEN RETURN 0; END IF;
 hi:=least(st.last_id,st.next_id+st.batch_size-1);
 CREATE TEMP TABLE fact_event_batch ON COMMIT DROP AS
 SELECT created_at::date AS tanggal,pegawai_id,
count(*) AS n,
count(*) FILTER (WHERE checktype=1) AS n_in,
count(*) FILTER (WHERE checktype=2) AS n_out,
count(*) FILTER (WHERE checktype IS NULL OR checktype NOT IN (1,2)) AS n_other,
count(*) FILTER (WHERE is_manual IS TRUE) AS n_manual,
min(jadwal_id) AS jadwal_id_min,
max(jadwal_id) AS jadwal_id_max,
count(*) FILTER (WHERE jadwal_id IS NULL) AS jadwal_id_nulls,
min(work_code) AS work_code_min,
max(work_code) AS work_code_max,
count(*) FILTER (WHERE work_code IS NULL) AS work_code_nulls,
min(departemen) AS departemen_min,
max(departemen) AS departemen_max,
count(*) FILTER (WHERE departemen IS NULL) AS departemen_nulls,
min(is_wfh) AS is_wfh_min,
max(is_wfh) AS is_wfh_max,
count(*) FILTER (WHERE is_wfh IS NULL) AS is_wfh_nulls,
min(timezone) AS timezone_min,
max(timezone) AS timezone_max,
count(*) FILTER (WHERE timezone IS NULL) AS timezone_nulls,
min(jam_masuk) AS jam_masuk_min,
max(jam_masuk) AS jam_masuk_max,
count(*) FILTER (WHERE jam_masuk IS NULL) AS jam_masuk_nulls,
min(jam_keluar) AS jam_keluar_min,
max(jam_keluar) AS jam_keluar_max,
count(*) FILTER (WHERE jam_keluar IS NULL) AS jam_keluar_nulls,
min(created_at) FILTER (WHERE checktype=1) AS masuk_min,
max(created_at) FILTER (WHERE checktype=1) AS masuk_max,
min(created_at) FILTER (WHERE checktype=2) AS pulang_min,
max(created_at) FILTER (WHERE checktype=2) AS pulang_max,
max(updated_at) AS updated_max,
min(id) AS event_min,
max(id) AS event_max
 FROM hop_source.t_checkinout WHERE id>=st.next_id AND id<=hi
 GROUP BY created_at::date,pegawai_id;
 SELECT coalesce(sum(n),0),coalesce(sum(n) FILTER(WHERE tanggal IS NULL),0) INTO total,rejected FROM pg_temp.fact_event_batch;
 INSERT INTO hop_etl.event_day SELECT * FROM pg_temp.fact_event_batch WHERE tanggal IS NOT NULL
 ON CONFLICT(tanggal,pegawai_id) DO UPDATE SET
n=event_day.n+EXCLUDED.n,
n_in=event_day.n_in+EXCLUDED.n_in,
n_out=event_day.n_out+EXCLUDED.n_out,
n_other=event_day.n_other+EXCLUDED.n_other,
n_manual=event_day.n_manual+EXCLUDED.n_manual,
jadwal_id_min=least(event_day.jadwal_id_min,EXCLUDED.jadwal_id_min),
jadwal_id_max=greatest(event_day.jadwal_id_max,EXCLUDED.jadwal_id_max),
jadwal_id_nulls=event_day.jadwal_id_nulls+EXCLUDED.jadwal_id_nulls,
work_code_min=least(event_day.work_code_min,EXCLUDED.work_code_min),
work_code_max=greatest(event_day.work_code_max,EXCLUDED.work_code_max),
work_code_nulls=event_day.work_code_nulls+EXCLUDED.work_code_nulls,
departemen_min=least(event_day.departemen_min,EXCLUDED.departemen_min),
departemen_max=greatest(event_day.departemen_max,EXCLUDED.departemen_max),
departemen_nulls=event_day.departemen_nulls+EXCLUDED.departemen_nulls,
is_wfh_min=least(event_day.is_wfh_min,EXCLUDED.is_wfh_min),
is_wfh_max=greatest(event_day.is_wfh_max,EXCLUDED.is_wfh_max),
is_wfh_nulls=event_day.is_wfh_nulls+EXCLUDED.is_wfh_nulls,
timezone_min=least(event_day.timezone_min,EXCLUDED.timezone_min),
timezone_max=greatest(event_day.timezone_max,EXCLUDED.timezone_max),
timezone_nulls=event_day.timezone_nulls+EXCLUDED.timezone_nulls,
jam_masuk_min=least(event_day.jam_masuk_min,EXCLUDED.jam_masuk_min),
jam_masuk_max=greatest(event_day.jam_masuk_max,EXCLUDED.jam_masuk_max),
jam_masuk_nulls=event_day.jam_masuk_nulls+EXCLUDED.jam_masuk_nulls,
jam_keluar_min=least(event_day.jam_keluar_min,EXCLUDED.jam_keluar_min),
jam_keluar_max=greatest(event_day.jam_keluar_max,EXCLUDED.jam_keluar_max),
jam_keluar_nulls=event_day.jam_keluar_nulls+EXCLUDED.jam_keluar_nulls,
masuk_min=least(event_day.masuk_min,EXCLUDED.masuk_min),
masuk_max=greatest(event_day.masuk_max,EXCLUDED.masuk_max),
pulang_min=least(event_day.pulang_min,EXCLUDED.pulang_min),
pulang_max=greatest(event_day.pulang_max,EXCLUDED.pulang_max),
updated_max=greatest(event_day.updated_max,EXCLUDED.updated_max),
event_min=least(event_day.event_min,EXCLUDED.event_min),
event_max=greatest(event_day.event_max,EXCLUDED.event_max);
 IF rejected>0 THEN
  INSERT INTO hop_etl.event_rejects SELECT id,pegawai_id,'CREATED_AT_NULL' FROM hop_source.t_checkinout
  WHERE id>=st.next_id AND id<=hi AND created_at IS NULL ON CONFLICT(id) DO NOTHING;
 END IF;
 INSERT INTO hop_etl.fact_batches(start_id,end_id,event_rows,rejected_rows) VALUES(st.next_id,hi,total,rejected);
 UPDATE hop_etl.fact_checkpoint SET next_id=hi+1,event_rows=event_rows+total,
 rejected_event_rows=rejected_event_rows+rejected,changed_at=clock_timestamp(),
 phase=CASE WHEN hi>=last_id THEN 'references' ELSE 'events' END WHERE singleton;
 RETURN total;
END $$;
REVOKE ALL ON FUNCTION hop_etl.ingest_fact_events() FROM PUBLIC;
