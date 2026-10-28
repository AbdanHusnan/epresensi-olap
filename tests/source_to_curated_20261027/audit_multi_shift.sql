-- known_owners_match: BOOL_AND ignores NULL owners; shared shifts can be included. Not strict ownership equality.
-- Eksplorasi read-only pada dbabsen_restore. Tanggal kalender belum tanggal kerja.
BEGIN READ ONLY;
SET LOCAL statement_timeout='8min';
SET LOCAL work_mem='64MB';
WITH e AS MATERIALIZED (
 SELECT t.pegawai_id,t.departemen,t.created_at,t.checktype,t.jadwal_id,t.work_code,
 t.jam_masuk,t.jam_keluar,t.hari,t.timezone,t.is_manual,t.approval_at,
 s.id shift_id,s.nama shift_name,s.departemen_id shift_department,
 j.hari master_day,j.jam_masuk master_in,j.jam_keluar master_out
 FROM public.t_checkinout t
 LEFT JOIN public.m_jadwal j ON j.id=t.jadwal_id
 LEFT JOIN public.m_shift s ON s.id=j.jenis
 WHERE t.created_at >= timestamp '2026-08-01' AND t.created_at < timestamp '2026-09-01'
 AND t.checktype IN (1,2)
), sessions AS MATERIALIZED (
 SELECT pegawai_id,departemen,created_at::date calendar_day,shift_id,
 max(shift_name) shift_name,max(shift_department) shift_department,
 count(*) FILTER(WHERE checktype=1) n_in,count(*) FILTER(WHERE checktype=2) n_out,
 min(created_at) FILTER(WHERE checktype=1) first_in,max(created_at) FILTER(WHERE checktype=2) last_out,
 bool_or(coalesce(jam_keluar,master_out)<coalesce(jam_masuk,master_in)) overnight,
 bool_and(is_manual IS FALSE OR (is_manual IS TRUE AND approval_at IS NOT NULL)) manual_gate,
 jsonb_agg(jsonb_build_object('at',created_at,'type',checktype,'schedule',jadwal_id,
 'work_code',work_code,'in',jam_masuk,'out',jam_keluar,'day',hari,'master_day',master_day,
 'timezone',timezone,'manual',is_manual,'has_approval_at',approval_at IS NOT NULL) ORDER BY created_at) events
 FROM e WHERE shift_id IS NOT NULL
 GROUP BY pegawai_id,departemen,created_at::date,shift_id
), days AS MATERIALIZED (
 SELECT pegawai_id,departemen,calendar_day,count(*) shifts,
 count(*) FILTER(WHERE n_in>0) shifts_with_in,
 count(*) FILTER(WHERE n_in>0 AND n_out>0 AND first_in<last_out) shifts_with_ordered_both,
 bool_and(shift_department=departemen) known_owners_match,
 bool_or(overnight) overnight,bool_and(manual_gate) manual_gate,
 jsonb_agg(jsonb_build_object('shift_id',shift_id,'name',shift_name,'owner',shift_department,'n_in',n_in,'n_out',n_out,'events',events) ORDER BY first_in NULLS LAST,shift_id) detail
 FROM sessions GROUP BY pegawai_id,departemen,calendar_day HAVING count(*)>1
), sample AS (
 SELECT row_number() OVER(ORDER BY calendar_day,departemen,pegawai_id) sample_no,
 departemen,calendar_day,shifts,shifts_with_in,shifts_with_ordered_both,overnight,detail
 FROM (SELECT * FROM days WHERE shifts_with_ordered_both>=2 AND known_owners_match AND manual_gate
 ORDER BY overnight DESC,calendar_day,departemen,pegawai_id LIMIT 5) x
)
SELECT 'summary' section,jsonb_build_object(
 'period','2026-08-01 <= created_at < 2026-09-01',
 'events',(SELECT count(*) FROM e),
 'unresolved_shift_events',(SELECT count(*) FROM e WHERE shift_id IS NULL),
 'work_code_mismatch',(SELECT count(*) FROM e WHERE shift_id IS NOT NULL AND work_code IS DISTINCT FROM shift_id),
 'employee_department_calendar_days_multi_shift',count(*),
 'two_shifts_with_checkin',count(*) FILTER(WHERE shifts_with_in>=2),
 'two_shifts_ordered_in_out',count(*) FILTER(WHERE shifts_with_ordered_both>=2),
 'two_shifts_ordered_in_out_known_owners_match',count(*) FILTER(WHERE shifts_with_ordered_both>=2 AND known_owners_match),
 'two_shifts_ordered_in_out_known_owners_match_manual_gate',count(*) FILTER(WHERE shifts_with_ordered_both>=2 AND known_owners_match AND manual_gate),
 'departments_two_shifts_ordered_known_owners_match',count(DISTINCT departemen) FILTER(WHERE shifts_with_ordered_both>=2 AND known_owners_match),
 'multi_with_overnight',count(*) FILTER(WHERE overnight)) result FROM days
UNION ALL SELECT 'sample',to_jsonb(sample) FROM sample
UNION ALL SELECT 'department',jsonb_build_object('id',x.departemen,'name',d.nama_departemen,'employee_days',x.n)
FROM (SELECT departemen,count(*) n FROM days WHERE shifts_with_ordered_both>=2 AND known_owners_match GROUP BY departemen ORDER BY count(*) DESC LIMIT 10) x
LEFT JOIN m_departemen d ON d.id=x.departemen;
COMMIT;
