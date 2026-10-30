"""Read-only business-data reconciliation for the authorized single-day test."""
import datetime,importlib.util,json,time
from pathlib import Path
OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('load',OUT/'load.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);t=m.t

def verify(label):
    src_cols=t.data("SELECT jsonb_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='curated' AND table_name='cur_attendance_daily'")
    dst_cols=t.data("SELECT jsonb_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='mart_kehadiran' AND table_name='fact_kehadiran_daily'",target=True)
    mapping={'pegawai_id':'pegawai_id_sumber','departemen_id':'departemen_id_sumber'}
    common=[c for c in src_cols if mapping.get(c,c) in dst_cols]
    hashes=[]
    for target,table,idcol in [(False,'curated.cur_attendance_daily','pegawai_id'),(True,'mart_kehadiran.fact_kehadiran_daily','pegawai_id_sumber')]:
        cols=','.join(mapping.get(c,c) if target else c for c in common)
        hashes.append(t.data(f"SELECT jsonb_agg(to_jsonb(x) ORDER BY tanggal) FROM (SELECT tanggal,count(*) AS rows,md5(string_agg(md5(jsonb_build_array({cols})::text),'' ORDER BY {idcol})) AS hash FROM {table} GROUP BY tanggal) x",target=target))
    t.require(hashes[0]==hashes[1],'Source/fact daily fingerprints differ')
    t.require(t.scalar('''SELECT count(*) FROM curated.cur_attendance_daily d LEFT JOIN curated.cur_employee_population_daily p USING(pegawai_id,tanggal) WHERE p.pegawai_id IS NULL OR d.departemen_id IS DISTINCT FROM p.departemen_id OR d.is_employee_active IS DISTINCT FROM p.is_employee_active''')=='0','Population mismatch')
    # All metric expectations independently derived from raw Boolean flags.
    a='is_employee_active IS TRUE'
    predicates=[a,f'({a}) AND has_masuk',f'({a}) AND has_pulang',f'({a}) AND NOT has_excused_checkin AND NOT has_masuk',f'({a}) AND NOT has_excused_checkout AND NOT has_pulang',f'({a}) AND has_valid_leave',f'({a}) AND NOT has_excused_checkin',f'({a}) AND NOT has_excused_checkout',f'({a}) AND has_excused_checkin',f'({a}) AND has_excused_checkout',f'({a}) AND NOT has_excused_checkin AND has_masuk',f'({a}) AND NOT has_excused_checkout AND has_pulang']
    expected=t.data("SELECT jsonb_agg(to_jsonb(x) ORDER BY tanggal,departemen_id_sumber) FROM (SELECT tanggal,departemen_id AS departemen_id_sumber,"+','.join(f'SUM(CASE WHEN {p} THEN 1 ELSE 0 END) AS {metric}' for metric,p in zip(t.MEASURES,predicates))+",count(*) AS fact_rows,count(*) FILTER(WHERE perlu_review) AS review_rows,count(*) FILTER(WHERE NOT is_date_final) AS nonfinal_rows FROM curated.cur_attendance_daily GROUP BY tanggal,departemen_id) x")
    actual=t.data('SELECT jsonb_agg(to_jsonb(x) ORDER BY tanggal,departemen_id_sumber) FROM (SELECT a.tanggal,d.departemen_id_sumber,'+','.join('a.'+c for c in t.MEASURES)+',a.fact_rows,a.review_rows,a.nonfinal_rows FROM serving.agg_kehadiran_departemen_harian a JOIN mart_kehadiran.dim_departemen d USING(departemen_key)) x',target=True)
    t.require(expected==actual,'Independent aggregate oracle mismatch')
    t.require(t.scalar("""SELECT count(*) FROM mart_kehadiran.fact_kehadiran_daily f JOIN mart_kehadiran.dim_pegawai p USING(pegawai_key) JOIN mart_kehadiran.dim_departemen d USING(departemen_key) WHERE f.pegawai_id_sumber IS DISTINCT FROM p.pegawai_id_sumber OR f.departemen_id_sumber IS DISTINCT FROM d.departemen_id_sumber OR NOT(f.tanggal>=p.valid_from AND (p.valid_to IS NULL OR f.tanggal<p.valid_to)) OR NOT(f.tanggal>=d.valid_from AND (d.valid_to IS NULL OR f.tanggal<d.valid_to))""",target=True)=='0','Dimension mismatch')
    views=t.data('SELECT jsonb_agg(to_jsonb(v)) FROM serving.v_kehadiran_departemen_harian v',target=True)
    for row in views:
        t.require(row['is_provisional'] and not row['is_data_complete'],'Publication status mismatch')
        for name,num,den in [('checkin_rate','checkin_days','active_employee_days'),('checkout_rate','checkout_days','active_employee_days'),('required_checkin_rate','required_checkin_present_days','required_checkin_days'),('required_checkout_rate','required_checkout_present_days','required_checkout_days')]:
            t.require(row[name] is None if row[den]==0 else abs(row[name]-100*row[num]/row[den])<1e-8,'Ratio mismatch')
    pending=t.scalar('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL');t.require(pending=='0','Pending outbox')
    state=t.data("SELECT jsonb_build_object('batches',(SELECT count(*) FROM etl_control.mart_batch),'receipts',(SELECT count(*) FROM etl_control.mart_delivery_receipt),'not_applied',(SELECT count(*) FROM etl_control.mart_batch WHERE status<>'APPLIED'),'last_sequence',(SELECT last_sequence FROM etl_control.mart_delivery_cursor))",target=True)
    seq=int(t.scalar('SELECT last_sequence FROM etl_control.mart_outbox_stream'))
    t.require(state['batches']==state['receipts']==state['last_sequence']==seq and state['not_applied']==0,'Delivery state mismatch')
    t.require(t.scalar("SELECT count(*) FROM (SELECT to_jsonb(d)-'fixture_n' AS r FROM test_load_82000.daily d EXCEPT SELECT to_jsonb(c) FROM curated.cur_attendance_daily c WHERE tanggal='2026-10-28' AND pegawai_id<1000000000) x")=='0','Original curated changed')
    t.require(t.guards()==json.loads((OUT/'protected_before.json').read_text()),'Protected data changed')
    result={'passed':True,'date_hashes':hashes[0],'compared_fields':common,'facts':sum(x['rows'] for x in hashes[0]),'partitions':len(expected),'control':state,'pending':0,'source_fact_fingerprints_equal':True,'independent_boolean_aggregate_oracle':True,'dimension_mismatches':0,'original_curated_unchanged':True,'protected_unchanged':True}
    t.save(label+'_reconciliation',result);print('PASS',label,result['facts'],'facts',len(expected),'partitions',flush=True)

if __name__=='__main__':verify('final')
