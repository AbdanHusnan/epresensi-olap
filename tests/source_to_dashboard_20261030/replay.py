import run as r

def fp():
 return {label:r.sql(q,where=where) for label,q,where in [('daily',"SELECT md5(string_agg(md5(to_jsonb(d)::text||d.xmin::text),'' ORDER BY pegawai_id,tanggal)) FROM curated.cur_attendance_daily d",'stage'),('fact',"SELECT md5(string_agg(md5(to_jsonb(f)::text||f.xmin::text),'' ORDER BY pegawai_id_sumber,tanggal)) FROM mart_kehadiran.fact_kehadiran_daily f",'mart'),('aggregate',"SELECT md5(string_agg(md5(to_jsonb(a)::text||a.xmin::text),'' ORDER BY tanggal,departemen_key)) FROM serving.agg_kehadiran_departemen_harian a",'mart')]}
before=fp();label=r.MARK+'_REPLAY'
r.sql(f"SELECT etl_control.enqueue_curated_batch('{label}',p_event_ids=>(SELECT array_agg(id ORDER BY id) FROM raw.raw_checkinout),p_leave_ids=>(SELECT array_agg(id ORDER BY id) FROM raw.raw_perizinan),p_snapshot_date=>DATE '{r.DAY}',p_snapshot_complete=>true)")
# Save initial phase logs before invoking identical entry points.
for name in ['curated.hpl','mart.hwf']:
 for suffix in ['.log','_timing.json']:
  p=r.OUT/(name+suffix);p.rename(r.OUT/('initial_'+name+suffix))
r.hop('curated.hpl');r.require(fp()==before,'Replay changed row versions');r.require(r.sql('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL')=='0','No-op emitted changes')
r.hop('mart.hwf');r.require(fp()==before,'Empty mart queue changed data')
r.save('replay',{'passed':True,'before':before,'after':fp(),'result':r.data(f"SELECT result FROM etl_control.curated_batch WHERE batch_id='{label}'"),'pending':0,'receipts':int(r.sql('SELECT count(*) FROM etl_control.mart_delivery_receipt',where='mart'))})
print('PASS replay: source IDs redelivered without rewriting daily/fact/aggregate rows')
