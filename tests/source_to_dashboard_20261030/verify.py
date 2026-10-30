"""Independent source-transaction oracle and full downstream reconciliation."""
import json
import run as r

def verify():
 cols=['pegawai_id','tanggal','departemen_id','is_employee_active','checkin_event_count','checkout_event_count','first_checkin_at','last_checkout_at','has_masuk','has_pulang','has_valid_leave','has_full_day_leave','has_partial_day_leave','has_excused_checkin','has_excused_checkout']+r.MEASURES
 source=f"""WITH ev AS(SELECT e.pegawai_id,count(*) FILTER(WHERE e.checktype=1)::integer ni,count(*) FILTER(WHERE e.checktype=2)::integer no,
 min(e.created_at) FILTER(WHERE e.checktype=1) first_in,max(e.created_at) FILTER(WHERE e.checktype=2) last_out
 FROM public.t_checkinout e JOIN {r.SCHEMA}.events f ON f.id=e.id GROUP BY e.pegawai_id),
 lv AS(SELECT l.pegawai_id,bool_or(l.tipe_ijin=1) full_leave,bool_or(l.tipe_ijin IN(2,3)) partial_leave,bool_or(l.tipe_ijin IN(1,2)) ei,bool_or(l.tipe_ijin IN(1,3)) eo
 FROM public.t_perizinan l JOIN {r.SCHEMA}.leaves f ON f.id=l.id WHERE l.approval=true AND DATE '{r.DAY}' BETWEEN l.tgl_ijin AND l.tgl_ijin_sampai GROUP BY l.pegawai_id),
 flags AS(SELECT c.emp AS pegawai_id,DATE '{r.DAY}' AS tanggal,c.dep AS departemen_id,true AS is_employee_active,
 coalesce(e.ni,0) AS checkin_event_count,coalesce(e.no,0) AS checkout_event_count,e.first_in AS first_checkin_at,e.last_out AS last_checkout_at,
 coalesce(e.ni,0)>0 AS has_masuk,coalesce(e.no,0)>0 AS has_pulang,l.pegawai_id IS NOT NULL AS has_valid_leave,
 coalesce(l.full_leave,false) AS has_full_day_leave,coalesce(l.partial_leave,false) AS has_partial_day_leave,
 coalesce(l.ei,false) AS has_excused_checkin,coalesce(l.eo,false) AS has_excused_checkout FROM {r.SCHEMA}.cohort c LEFT JOIN ev e ON e.pegawai_id=c.emp LEFT JOIN lv l ON l.pegawai_id=c.emp),
 expected AS(SELECT *,1 AS active_employee_days,has_masuk::int AS checkin_days,has_pulang::int AS checkout_days,
 (NOT has_masuk AND NOT has_excused_checkin)::int AS no_checkin_days,(NOT has_pulang AND NOT has_excused_checkout)::int AS no_checkout_days,
 has_valid_leave::int AS leave_days,(NOT has_excused_checkin)::int AS required_checkin_days,(NOT has_excused_checkout)::int AS required_checkout_days,
 has_excused_checkin::int AS excused_checkin_days,has_excused_checkout::int AS excused_checkout_days,
 (has_masuk AND NOT has_excused_checkin)::int AS required_checkin_present_days,(has_pulang AND NOT has_excused_checkout)::int AS required_checkout_present_days FROM flags) """
 def digest(query,columns,idcol,where):
  return r.data(query+f"SELECT json_build_object('rows',count(*),'hash',md5(string_agg(md5(jsonb_build_array({','.join(columns)})::text),'' ORDER BY {idcol}))) FROM "+('expected' if query else 'curated.cur_attendance_daily'),where=where)
 expected=digest(source,cols,'pegawai_id','source');actual=digest('',cols,'pegawai_id','stage');r.require(expected==actual,'Source oracle/curated mismatch')
 # The fixture itself must match the intended mix, independent of actual source aggregation.
 mix=r.data(f"SELECT json_build_object('employees',count(*),'checkin',count(*) FILTER(WHERE (n-1)%100<91 OR (n-1)%100>=98),'checkout',count(*) FILTER(WHERE (n-1)%100<88 OR (n-1)%100=91 OR (n-1)%100 IN(96,97)),'leave',count(*) FILTER(WHERE (n-1)%100>=93)) FROM {r.SCHEMA}.cohort",where='source')
 totals=r.data('SELECT json_build_object('+','.join(r.quote(m)+',SUM('+m+')' for m in r.MEASURES)+') FROM curated.cur_attendance_daily')
 r.require([totals['active_employee_days'],totals['checkin_days'],totals['checkout_days'],totals['leave_days']]==[mix['employees'],mix['checkin'],mix['checkout'],mix['leave']],'Fixture mix mismatch')
 src_cols=r.data("SELECT json_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='curated' AND table_name='cur_attendance_daily'")
 dst_cols=r.data("SELECT json_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='mart_kehadiran' AND table_name='fact_kehadiran_daily'",where='mart')
 mapping={'pegawai_id':'pegawai_id_sumber','departemen_id':'departemen_id_sumber'};common=[c for c in src_cols if mapping.get(c,c) in dst_cols]
 a=r.data("SELECT json_build_object('rows',count(*),'hash',md5(string_agg(md5(jsonb_build_array("+','.join(common)+")::text),'' ORDER BY pegawai_id,tanggal))) FROM curated.cur_attendance_daily")
 b=r.data("SELECT json_build_object('rows',count(*),'hash',md5(string_agg(md5(jsonb_build_array("+','.join(mapping.get(c,c) for c in common)+")::text),'' ORDER BY pegawai_id_sumber,tanggal))) FROM mart_kehadiran.fact_kehadiran_daily",where='mart');r.require(a==b,'Curated/fact mismatch')
 sums=','.join(f'SUM({m}) AS {m}' for m in r.MEASURES)
 a=r.data(source+f'SELECT json_agg(x ORDER BY departemen_id) FROM (SELECT departemen_id,{sums} FROM expected GROUP BY departemen_id) x',where='source')
 b=r.data('SELECT json_agg(x ORDER BY departemen_id) FROM (SELECT departemen_id_sumber AS departemen_id,'+','.join(r.MEASURES)+' FROM serving.v_kehadiran_departemen_harian) x',where='mart');r.require(a==b,'Source oracle/serving department mismatch')
 ratios=r.data('SELECT json_agg(v) FROM serving.v_kehadiran_departemen_harian v',where='mart')
 for row in ratios:
  r.require(row['is_provisional'] and not row['is_data_complete'],'Invalid publication claim')
  for name,num,den in [('checkin_rate','checkin_days','active_employee_days'),('checkout_rate','checkout_days','active_employee_days'),('required_checkin_rate','required_checkin_present_days','required_checkin_days'),('required_checkout_rate','required_checkout_present_days','required_checkout_days')]:r.require(row[name] is None if row[den]==0 else abs(row[name]-100*row[num]/row[den])<1e-8,'Ratio mismatch')
 r.require(r.sql("SELECT count(*) FROM mart_kehadiran.fact_kehadiran_daily f JOIN mart_kehadiran.dim_pegawai p USING(pegawai_key) JOIN mart_kehadiran.dim_departemen d USING(departemen_key) WHERE f.pegawai_id_sumber IS DISTINCT FROM p.pegawai_id_sumber OR f.departemen_id_sumber IS DISTINCT FROM d.departemen_id_sumber OR NOT(f.tanggal>=p.valid_from AND (p.valid_to IS NULL OR f.tanggal<p.valid_to)) OR NOT(f.tanggal>=d.valid_from AND (d.valid_to IS NULL OR f.tanggal<d.valid_to))",where='mart')=='0','Dimension mismatch')
 r.require(r.sql('SELECT count(*) FROM curated.cur_attendance_daily d JOIN curated.cur_employee_population_daily p USING(pegawai_id,tanggal) WHERE d.departemen_id IS DISTINCT FROM p.departemen_id OR d.is_employee_active IS DISTINCT FROM p.is_employee_active')=='0','Population assignment mismatch')
 r.require(r.sql('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL')=='0','Pending mart queue')
 state=r.data("SELECT json_build_object('batches',(SELECT count(*) FROM etl_control.mart_batch),'receipts',(SELECT count(*) FROM etl_control.mart_delivery_receipt),'applied',(SELECT count(*) FROM etl_control.mart_batch WHERE status='APPLIED'))",where='mart');r.require(state=={'batches':1,'receipts':1,'applied':1},'Receipt mismatch')
 r.require(r.guards()==json.loads((r.OUT/'protected_before.json').read_text()),'Source masters or active databases changed')
 r.require(r.sql('SELECT count(*) FROM mart_kehadiran.fact_kehadiran_daily WHERE pegawai_id_sumber>=1000000000',where='mart')=='0','Old synthetic employee records remain')
 missing=r.sql('SELECT count(*) FROM test_source.cohort c LEFT JOIN curated.cur_attendance_daily d ON d.pegawai_id=c.emp WHERE d.pegawai_id IS NULL');r.require(missing=='0','Cohort missing')
 result={'passed':True,'source_oracle':expected,'curated_fact_shared_fields':len(common),'employees':mix['employees'],'departments':len(ratios),'totals':totals,'control':state,'date':r.DAY,'pending':0,'source_masters_unchanged':True,'active_databases_unchanged':True,'old_synthetic_employee_rows':0}
 r.save('verification',result);print(json.dumps(result,indent=2))
if __name__=='__main__':verify()
