CREATE OR REPLACE FUNCTION hop_etl.classify_fact(
 approved_count integer,leave_needs_review boolean,event_count bigint,
 pair_valid boolean,schedule_valid boolean,nonworking boolean,
 mode_valid boolean,has_manual boolean,flexible boolean,
 department_valid boolean,day_closed boolean)
RETURNS TABLE(status_usulan text,alasan_review text[])
LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path=pg_catalog AS $$
 SELECT CASE WHEN approved_count>0 THEN 'IZIN' WHEN pair_valid THEN 'HADIR' END,
 array_remove(ARRAY[
 CASE WHEN event_count=0 THEN 'POPULASI_DAN_KEWAJIBAN_HISTORIS_BELUM_TERVERIFIKASI' END,
 CASE WHEN NOT schedule_valid THEN 'JADWAL_ATAU_HISTORI_BELUM_TERVERIFIKASI' END,
 CASE WHEN nonworking THEN 'HARI_NONWAJIB_PERLU_KEPUTUSAN_PENYIMPANAN' END,
 CASE WHEN event_count>0 AND NOT pair_valid THEN 'PASANGAN_EVENT_BELUM_FINAL' END,
 CASE WHEN event_count>0 AND NOT mode_valid THEN 'MODE_KERJA_ATAU_TIMEZONE_TIDAK_KONSISTEN' END,
 CASE WHEN has_manual THEN 'PRESENSI_MANUAL_BELUM_TERVERIFIKASI' END,
 CASE WHEN flexible THEN 'ATURAN_FLEKSIBEL_BELUM_FINAL' END,
 CASE WHEN NOT department_valid THEN 'DEPARTEMEN_TRANSAKSI_MASTER_TIDAK_KONSISTEN' END,
 CASE WHEN leave_needs_review OR approved_count>1 THEN 'IDENTITAS_CAKUPAN_ATAU_JENIS_IZIN_PERLU_REVIEW' END,
 CASE WHEN day_closed IS NOT TRUE THEN 'CAKUPAN_HARI_SUMBER_BELUM_TERVERIFIKASI' END
 ],NULL)::text[];
$$;
REVOKE ALL ON FUNCTION hop_etl.classify_fact(integer,boolean,bigint,boolean,boolean,boolean,boolean,boolean,boolean,boolean,boolean) FROM PUBLIC;

CREATE OR REPLACE FUNCTION hop_etl.build_fact_day(p_day date) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET work_mem='128MB' SET jit=off AS $$
DECLARE affected bigint; last_day date; nfinal bigint; nevents bigint;
BEGIN
 SELECT last_date INTO STRICT last_day FROM hop_etl.fact_checkpoint WHERE singleton;
 IF NOT EXISTS(SELECT 1 FROM public.dim_calendar WHERE tanggal=p_day) THEN RAISE EXCEPTION 'Missing calendar date %',p_day; END IF;
 IF EXISTS(SELECT 1 FROM hop_etl.event_day e LEFT JOIN public.dim_pegawai p ON p.pegawai_id_sumber=e.pegawai_id WHERE e.tanggal=p_day AND p.pegawai_key IS NULL) THEN RAISE EXCEPTION 'Missing employee dimension on %',p_day; END IF;
 WITH leave_daily AS (
  SELECT coalesce(pegawai_id,user_pegawai_id) AS pegawai_id,
   count(*) FILTER(WHERE approval IS TRUE)::integer AS approved_count,
   string_agg(id::text,',' ORDER BY id) FILTER(WHERE approval IS TRUE) AS ids,
   bool_or(approval IS TRUE AND (pegawai_id IS DISTINCT FROM user_pegawai_id OR approval_at IS NULL
    OR periode IS NULL OR setengah_hari IS DISTINCT FROM false OR tipe_id=3 OR tipe_id IS NULL OR nama_jenis ILIKE '%lupa%')) AS needs_review,
   max(updated_at) AS updated_at
  FROM hop_etl.leave_source WHERE periode @> p_day OR (periode IS NULL AND awal=p_day)
  GROUP BY coalesce(pegawai_id,user_pegawai_id)
 ), off_daily AS (
  SELECT DISTINCT pegawai_id FROM hop_etl.off_source WHERE tanggal=p_day AND pegawai_id IS NOT NULL
 ), base AS (
  SELECT p.pegawai_id,p.pegawai_key,p.departemen_id,p.departemen_key,
   e.n, e.n_in, e.n_out, e.n_other, e.n_manual, e.jadwal_id_min, e.jadwal_id_max, e.jadwal_id_nulls, e.work_code_min, e.work_code_max, e.work_code_nulls, e.departemen_min, e.departemen_max, e.departemen_nulls, e.is_wfh_min, e.is_wfh_max, e.is_wfh_nulls, e.timezone_min, e.timezone_max, e.timezone_nulls, e.jam_masuk_min, e.jam_masuk_max, e.jam_masuk_nulls, e.jam_keluar_min, e.jam_keluar_max, e.jam_keluar_nulls, e.masuk_min, e.masuk_max, e.pulang_min, e.pulang_max, e.updated_max, e.event_min, e.event_max, coalesce(e.n,0) AS event_count,
   s.shift_key,s.jadwal_id_sumber,
   coalesce(i.approved_count,0) AS approved_count,i.ids AS izin_ids,coalesce(i.needs_review,false) AS leave_review,
   greatest(e.updated_max,i.updated_at) AS last_updated,
   o.pegawai_id IS NOT NULL AS off_individual,
   c.is_weekend OR c.is_hari_libur OR o.pegawai_id IS NOT NULL AS nonworking,
   coalesce(e.n_in=1 AND e.n_out=1 AND e.n_other=0 AND e.pulang_min>=e.masuk_min,false) AS pair_valid,
   coalesce(s.shift_key IS NOT NULL AND s.is_reguler AND s.hari_iso=c.hari_iso
    AND e.jadwal_id_min=e.jadwal_id_max AND e.jadwal_id_nulls=0
    AND e.work_code_min=e.work_code_max AND e.work_code_min=s.shift_id_sumber AND e.work_code_nulls=0
    AND e.jam_masuk_nulls=0 AND e.jam_keluar_nulls=0
    AND e.jam_masuk_min=e.jam_masuk_max AND e.jam_keluar_min=e.jam_keluar_max
    AND e.jam_masuk_min=s.jam_masuk AND e.jam_keluar_min=s.jam_keluar
    AND e.jam_keluar_min>e.jam_masuk_min,false) AS schedule_valid,
   coalesce(e.is_wfh_min=e.is_wfh_max AND e.is_wfh_min IN (0,1) AND e.is_wfh_nulls=0
    AND e.timezone_min='Asia/Jakarta' AND e.timezone_max='Asia/Jakarta' AND e.timezone_nulls=0,false) AS mode_valid,
   coalesce(e.departemen_min=e.departemen_max AND e.departemen_min=p.departemen_id_sumber AND e.departemen_nulls=0,false) AS department_valid,
   s.is_flexible IS DISTINCT FROM false AS flexible,
   p_day<last_day AND p_day<=(SELECT max(tanggal) FROM hop_etl.calendar_snapshot WHERE is_hari_libur) AS day_closed
  FROM hop_etl.employee_snapshot p CROSS JOIN hop_etl.calendar_snapshot c
  LEFT JOIN hop_etl.event_day e ON e.pegawai_id=p.pegawai_id_sumber AND e.tanggal=p_day
  LEFT JOIN hop_etl.shift_snapshot s ON s.jadwal_id_sumber=e.jadwal_id_min AND e.jadwal_id_min=e.jadwal_id_max
  LEFT JOIN leave_daily i ON i.pegawai_id=p.pegawai_id_sumber
  LEFT JOIN off_daily o ON o.pegawai_id=p.pegawai_id_sumber
  WHERE c.tanggal=p_day AND (e.n IS NOT NULL OR i.pegawai_id IS NOT NULL OR o.pegawai_id IS NOT NULL)
 ), classified AS (
  SELECT b.*,r.status_usulan,r.alasan_review,cardinality(r.alasan_review)=0 AS final
  FROM base b CROSS JOIN LATERAL hop_etl.classify_fact(b.approved_count,b.leave_review,b.event_count,
   b.pair_valid,b.schedule_valid,b.nonworking,b.mode_valid,coalesce(b.n_manual,0)>0,b.flexible,b.department_valid,b.day_closed) r
 ), projected AS (
  SELECT pegawai_id,p_day AS tanggal,departemen_id,
   CASE WHEN nonworking THEN false WHEN schedule_valid THEN true ELSE NULL END AS is_expected_workday,
   off_individual AS is_libur_shift,
   CASE WHEN n_in=1 THEN masuk_min END AS waktu_masuk,
   CASE WHEN n_out=1 THEN pulang_min END AS waktu_pulang,
   coalesce(n_in,0)>0 AS has_masuk,coalesce(n_out,0)>0 AS has_pulang,
   approved_count>0 AS has_valid_leave,
   CASE WHEN final THEN status_usulan END AS status_kehadiran,
   CASE WHEN final AND status_usulan='HADIR' THEN is_wfh_min=1 END AS is_wfh,
   CASE WHEN final AND status_usulan='HADIR' THEN is_wfh_min=0 END AS is_wfo,
   CASE WHEN final AND status_usulan='HADIR' THEN masuk_min>p_day+jam_masuk_min END AS is_terlambat,
   pair_valid AS is_complete_attendance,event_count::integer AS jumlah_event,last_updated AS source_updated_at,
   pegawai_key,departemen_key,
   CASE WHEN jadwal_id_nulls=0 AND jadwal_id_min=jadwal_id_max THEN shift_key END AS shift_key,
   CASE WHEN jadwal_id_nulls=0 AND jadwal_id_min=jadwal_id_max THEN jadwal_id_sumber END AS jadwal_id_sumber,
   izin_ids AS izin_id_sumber,
   CASE WHEN schedule_valid THEN p_day+jam_masuk_min END AS jadwal_mulai,
   CASE WHEN schedule_valid THEN p_day+jam_keluar_min END AS jadwal_selesai,
   CASE WHEN final AND status_usulan='HADIR' THEN CASE is_wfh_min WHEN 1 THEN 'WFH' WHEN 0 THEN 'WFO' END END AS mode_kerja,
   CASE WHEN final AND status_usulan='HADIR' THEN greatest(0,extract(epoch FROM masuk_min-(p_day+jam_masuk_min))/60) END AS durasi_terlambat,
   status_usulan,NOT final AS perlu_review,alasan_review,final AS is_kpi_final,
   event_min AS source_event_min_id,event_max AS source_event_max_id,'hop-v1-review'::text AS rule_version
  FROM classified
 )
 INSERT INTO public.fact_kehadiran (
 pegawai_id,tanggal,departemen_id,is_expected_workday,is_libur_shift,waktu_masuk,waktu_pulang,
 has_masuk,has_pulang,has_valid_leave,status_kehadiran,is_wfh,is_wfo,is_terlambat,
 is_complete_attendance,jumlah_event,source_updated_at,pegawai_key,departemen_key,shift_key,
 jadwal_id_sumber,izin_id_sumber,jadwal_mulai,jadwal_selesai,mode_kerja,durasi_terlambat,
 status_usulan,perlu_review,alasan_review,is_kpi_final,source_event_min_id,source_event_max_id,rule_version)
 SELECT * FROM projected
 ON CONFLICT(pegawai_id,tanggal) DO NOTHING;
 -- Initial frozen-source backfill: completed dates are immutable checkpoints. Revisions require an explicit new run.
 GET DIAGNOSTICS affected=ROW_COUNT;
 SELECT count(*) FILTER(WHERE is_kpi_final),coalesce(sum(jumlah_event),0) INTO nfinal,nevents FROM public.fact_kehadiran WHERE tanggal=p_day;
 INSERT INTO hop_etl.fact_days(tanggal,rows_written,final_rows,review_rows,event_rows)
 SELECT p_day,count(*),nfinal,count(*)-nfinal,nevents FROM public.fact_kehadiran WHERE tanggal=p_day
 ON CONFLICT(tanggal) DO NOTHING;
 RETURN affected;
END $$;
REVOKE ALL ON FUNCTION hop_etl.build_fact_day(date) FROM PUBLIC;
