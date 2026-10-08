CREATE TABLE IF NOT EXISTS hop_etl.reference_snapshot (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),leave_rows bigint NOT NULL,
 off_rows bigint NOT NULL,finished_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE OR REPLACE FUNCTION hop_etl.load_fact_references() RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET work_mem='128MB' AS $$
DECLARE n bigint; m bigint;
BEGIN
 IF EXISTS(SELECT 1 FROM hop_etl.reference_snapshot WHERE singleton) THEN RETURN 0; END IF;
 IF NOT pg_try_advisory_xact_lock(781204992) THEN RAISE EXCEPTION 'Reference snapshot already running'; END IF;
 INSERT INTO hop_etl.employee_snapshot SELECT pegawai_id,pegawai_id_sumber,pegawai_key,departemen_id,departemen_id_sumber,departemen_key FROM public.dim_pegawai ON CONFLICT DO NOTHING;
 INSERT INTO hop_etl.shift_snapshot SELECT * FROM public.dim_shift ON CONFLICT DO NOTHING;
 INSERT INTO hop_etl.calendar_snapshot SELECT * FROM public.dim_calendar ON CONFLICT DO NOTHING;
 INSERT INTO hop_etl.leave_source(id,pegawai_id,user_pegawai_id,departemen,approval,approval_at,awal,akhir,jenis_ijin,setengah_hari,tipe_id,nama_jenis,updated_at)
 SELECT i.id,i.pegawai_id,u.pegawai_id,i.departemen,i.approval,i.approval_at,i.tgl_ijin,i.tgl_ijin_sampai,i.jenis_ijin,j.setengah_hari,j.tipe_id,j.nama,i.updated_at
 FROM hop_source.t_perizinan i LEFT JOIN hop_source.m_user u ON u.id=i.user_id LEFT JOIN hop_source.m_jenis_ijin j ON j.id=i.jenis_ijin
 ON CONFLICT(id) DO NOTHING;
 GET DIAGNOSTICS n=ROW_COUNT;
 INSERT INTO hop_etl.off_source SELECT id,pegawai_id,tanggal,updated_at FROM hop_source.t_libur_shift ON CONFLICT(id) DO NOTHING;
 GET DIAGNOSTICS m=ROW_COUNT;
 INSERT INTO hop_etl.reference_snapshot(singleton,leave_rows,off_rows) VALUES(true,n,m);
 ANALYZE hop_etl.leave_source;
 ANALYZE hop_etl.off_source;
 RETURN n+m;
END $$;
REVOKE ALL ON FUNCTION hop_etl.load_fact_references() FROM PUBLIC;

CREATE OR REPLACE FUNCTION hop_etl.fact_step() RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET work_mem='128MB' AS $$
DECLARE st hop_etl.fact_checkpoint%ROWTYPE; d date; i integer; affected bigint:=0; n bigint;
BEGIN
 IF NOT pg_try_advisory_xact_lock(781204991) THEN RAISE EXCEPTION 'Fact loader already running'; END IF;
 SELECT * INTO STRICT st FROM hop_etl.fact_checkpoint WHERE singleton FOR UPDATE;
 IF st.phase='events' THEN RETURN hop_etl.ingest_fact_events(); END IF;
 IF st.phase='references' THEN
  PERFORM hop_etl.load_fact_references();
  SELECT min(tanggal),max(tanggal) INTO st.first_date,st.last_date FROM hop_etl.event_day;
  IF st.first_date IS NULL THEN RAISE EXCEPTION 'No dated source events'; END IF;
  SELECT count(*) INTO n FROM public.dim_calendar WHERE tanggal BETWEEN st.first_date AND st.last_date;
  IF n<>st.last_date-st.first_date+1 THEN RAISE EXCEPTION 'Calendar must cover % through % before facts',st.first_date,st.last_date; END IF;
  UPDATE hop_etl.fact_checkpoint SET first_date=st.first_date,last_date=st.last_date,next_date=st.first_date,phase='days',changed_at=clock_timestamp() WHERE singleton;
  ANALYZE hop_etl.event_day;
  RETURN 0;
 END IF;
 IF st.phase='days' THEN
  d:=st.next_date;
  FOR i IN 1..st.days_per_step LOOP
   EXIT WHEN d>st.last_date;
   affected:=affected+hop_etl.build_fact_day(d);
   d:=d+1;
  END LOOP;
  IF d>st.last_date THEN
   IF (SELECT count(*) FROM hop_etl.fact_days)<>st.last_date-st.first_date+1
    OR (SELECT coalesce(sum(event_rows),0) FROM hop_etl.fact_days)+st.rejected_event_rows<>st.event_rows
    OR (SELECT count(*) FROM hop_etl.event_rejects)<>st.rejected_event_rows
    OR (SELECT coalesce(sum(rows_written),0) FROM hop_etl.fact_days)<>st.fact_rows+affected THEN
    RAISE EXCEPTION 'Final reconciliation failed; KPI publication blocked';
   END IF;
  END IF;
  UPDATE hop_etl.fact_checkpoint SET next_date=d,fact_rows=fact_rows+affected,
   phase=CASE WHEN d>last_date THEN 'done' ELSE 'days' END,changed_at=clock_timestamp() WHERE singleton;
 END IF;
 RETURN affected;
END $$;
REVOKE ALL ON FUNCTION hop_etl.fact_step() FROM PUBLIC;
