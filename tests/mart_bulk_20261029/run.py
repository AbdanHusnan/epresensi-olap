#!/usr/bin/env python3
"""Existing bulk curated data -> isolated mart + serving through actual Hop."""
import argparse
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('small_harness',ROOT/'tests/mart_small_20261029/run.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
t.OUT=OUT
t.SOURCE='staging_bkd_mart_bulk_20261029'
t.TARGET='mart_bkd_bulk_20261029'
t.RUNTIME=t.PROJECT+'/pipelines/validation/mart_bulk_20261029'
EXPECTED=[2400,1000,1000,1000,600,1200,1800,1400,600,1000,800,800]


def deploy():
    t.command(['docker','exec',t.HOP,'mkdir','-p',t.RUNTIME])
    connections={'presensi_staging':'bulk_mart_source_20261029','presensi_mart':'bulk_mart_target_20261029'}
    for template,alias in connections.items():
        meta=json.loads(t.command(['docker','exec',t.HOP,'cat',t.PROJECT+'/metadata/rdbms/'+template+'.json']).stdout)
        meta['name']=alias
        meta['rdbms']['POSTGRESQL']['databaseName']=t.SOURCE if template=='presensi_staging' else t.TARGET
        t.write_runtime(t.PROJECT+'/metadata/rdbms/'+alias+'.json',json.dumps(meta))
    for path in (ROOT/'hop/pipelines/mart').glob('*.hpl'):
        xml=ET.parse(path).getroot()
        for c in xml.findall('transform/connection'):c.text=connections[c.text]
        ET.indent(xml);text=ET.tostring(xml,encoding='unicode',xml_declaration=True)
        (OUT/path.name).write_text(text);t.write_runtime(t.RUNTIME+'/'+path.name,text)
    xml=ET.parse(ROOT/'hop/workflows/mart/curated_to_serving.hwf').getroot()
    for f in xml.findall('actions/action/filename'):f.text=t.RUNTIME+'/'+Path(f.text).name
    ET.indent(xml);text=ET.tostring(xml,encoding='unicode',xml_declaration=True)
    (OUT/'curated_to_serving.hwf').write_text(text);t.write_runtime(t.RUNTIME+'/curated_to_serving.hwf',text)


def setup():
    for target,db in [(False,t.SOURCE),(True,t.TARGET)]:
        t.require(t.scalar(f'SELECT count(*) FROM pg_database WHERE datname={t.q(db)}',target=target,database='postgres')=='0','Existing test database: do not reset')
    protected=t.guards();t.save('protected_before',protected)
    inspection=json.loads((ROOT/'tests/bulk_attendance_20261028/pre_downstream_inspection_20261029.json').read_text())
    t.require(protected['reference']['hash']==inspection['daily_hash'],'Reference changed since inspection')
    sample=t.data("""SELECT jsonb_agg(jsonb_build_object('scenario',c.scenario,'daily',to_jsonb(d),'population',to_jsonb(p)) ORDER BY c.emp)
    FROM test_bulk.cohort c JOIN curated.cur_attendance_daily d ON d.pegawai_id=c.emp
    JOIN curated.cur_employee_population_daily p USING(pegawai_id,tanggal)""",database=t.REFERENCE)
    t.require(len(sample)==2400,'Expected 2400 existing employee days')
    oracle=[(0,0,0,0),(1,1,0,0),(1,0,0,0),(0,1,0,0),(0,0,0,0),(0,1,1,0),(1,0,0,1),(0,0,0,1),(0,0,0,1),(1,1,1,1),(2,2,0,0),(0,0,1,1)]
    for r in sample:
        d=r['daily'];expected=oracle[r['scenario']]
        t.require((d['checkin_event_count'],d['checkout_event_count'],int(d['has_excused_checkin']),int(d['has_excused_checkout']))==expected,'Scenario mismatch')
    for container,db in [(t.SC,t.SOURCE),(t.MC,t.TARGET)]:
        t.command(['docker','exec',container,'sh','-c','exec createdb -U "$POSTGRES_USER" "$1"','createdb',db])
    dump=t.command(['docker','exec',t.SC,'sh','-c','exec pg_dump -U "$POSTGRES_USER" -d "$1" --schema-only --no-owner --no-privileges -t curated.cur_attendance_daily -t curated.cur_employee_population_daily','dump',t.REFERENCE]).stdout
    t.sql('CREATE SCHEMA curated; CREATE SCHEMA etl_control;\n'+dump)
    for table,key in [('curated.cur_employee_population_daily','population'),('curated.cur_attendance_daily','daily')]:
        t.insert_json(table,[r[key] for r in sample])
        actual=t.rows(table)
        t.require(actual==sorted([r[key] for r in sample],key=lambda d:(d['pegawai_id'],d['tanggal'])),'Copied data differs from reference')
    t.sql((ROOT/'sql/staging/20261028_mart_outbox.sql').read_text())
    t.sql((ROOT/'sql/mart/20261028_attendance_daily.sql').read_text(),target=True)
    t.sql((ROOT/'sql/mart/20261028_mart_incremental_etl.sql').read_text(),target=True)
    t.sql('CREATE SCHEMA test_small; CREATE TABLE test_small.results(phase text PRIMARY KEY,result jsonb);')
    deploy()
    t.save('setup',{'source':t.SOURCE,'target':t.TARGET,'reference':t.REFERENCE,'rows':2400,'scenarios':12,'rows_per_scenario':200,'departments':len({r['daily']['departemen_id'] for r in sample}),'data_changed':False,'copy_verified':True})
    print('PASS setup: all 2400 existing curated rows copied without alteration',flush=True)


def verification(label):
    result=t.verify(label,EXPECTED)
    t.require(result['fact_rows']==2400 and result['aggregate_rows']==757,'Unexpected fact/aggregate cardinality')
    # Validate surrogate keys against their business identities and effective dates.
    mismatches=t.scalar("""SELECT count(*) FROM mart_kehadiran.fact_kehadiran_daily f
      JOIN mart_kehadiran.dim_pegawai p USING(pegawai_key)
      JOIN mart_kehadiran.dim_departemen d USING(departemen_key)
      WHERE f.pegawai_id_sumber IS DISTINCT FROM p.pegawai_id_sumber
      OR f.departemen_id_sumber IS DISTINCT FROM d.departemen_id_sumber
      OR NOT (f.tanggal>=p.valid_from AND (p.valid_to IS NULL OR f.tanggal<p.valid_to))
      OR NOT (f.tanggal>=d.valid_from AND (d.valid_to IS NULL OR f.tanggal<d.valid_to))""",target=True)
    t.require(mismatches=='0','Dimension identity or effective interval mismatch')
    # Independent department GROUP BY from curated business IDs, not fact keys.
    metrics=','.join(f'SUM({m}) AS {m}' for m in t.MEASURES)
    expected=t.data(f'SELECT jsonb_agg(to_jsonb(x) ORDER BY tanggal,departemen_id) FROM (SELECT tanggal,departemen_id,{metrics} FROM curated.cur_attendance_daily GROUP BY tanggal,departemen_id) x')
    actual=t.data('SELECT jsonb_agg(to_jsonb(x) ORDER BY tanggal,departemen_id) FROM (SELECT tanggal,departemen_id_sumber AS departemen_id,'+','.join(t.MEASURES)+' FROM serving.v_kehadiran_departemen_harian) x',target=True)
    t.require(expected==actual,'Per-department source/serving mismatch')
    t.save(label+'_departments',{'checked':len(expected),'mismatches':0,'totals':actual})
    # Check each percentage on every department, including zero-denominator partitions.
    rates=t.data('SELECT jsonb_agg(to_jsonb(v)) FROM serving.v_kehadiran_departemen_harian v',target=True)
    for row in rates:
        for name,num,den in [('checkin_rate','checkin_days','active_employee_days'),('checkout_rate','checkout_days','active_employee_days'),('required_checkin_rate','required_checkin_present_days','required_checkin_days'),('required_checkout_rate','required_checkout_present_days','required_checkout_days')]:
            value=row[name]
            t.require(value is None if row[den]==0 else abs(value-100*row[num]/row[den])<1e-8,'Department ratio mismatch')
    return result


def load():
    if t.scalar('SELECT bootstrap_prepared FROM etl_control.mart_outbox_stream')=='f':
        t.save('bootstrap',t.data('SELECT etl_control.prepare_mart_bootstrap()'))
    t.hop('bulk_load')
    verification('bulk_load')
    t.save('versions_after_load',{'fact':t.versions(),'aggregate':t.aggregate_versions()})
    # Existing no-op case: no new fixture, mutation, or scenario introduced.
    before=t.versions();agg=t.aggregate_versions()
    t.hop('empty_queue')
    t.require(t.versions()==before and t.aggregate_versions()==agg,'Empty queue rewrote target')
    t.require(t.guards()==json.loads((OUT/'protected_before.json').read_text()),'Protected reference or active database changed')
    t.save('protected_after',t.guards())
    state=t.data("SELECT jsonb_build_object('batches',(SELECT count(*) FROM etl_control.mart_batch),'receipts',(SELECT count(*) FROM etl_control.mart_delivery_receipt),'not_applied',(SELECT count(*) FROM etl_control.mart_batch WHERE status<>'APPLIED'),'last_sequence',(SELECT last_sequence FROM etl_control.mart_delivery_cursor))",target=True)
    pending=int(t.scalar('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL'))
    t.require(state['batches']==state['receipts']==state['last_sequence']==1 and state['not_applied']==pending==0,'Delivery checkpoint mismatch')
    plans={}
    for name,query in [('institution',"SELECT * FROM serving.v_kehadiran_instansi_harian WHERE tanggal='2026-10-28'"),('departments',"SELECT * FROM serving.v_kehadiran_departemen_harian WHERE tanggal='2026-10-28' ORDER BY checkin_days DESC")]:
        plans[name]=t.data('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+query,target=True)
    t.save('query_plans',plans)
    t.save('summary',{'passed':True,'source':t.SOURCE,'target':t.TARGET,'reference':t.REFERENCE,'fact_rows':2400,'aggregate_rows':757,'scenarios':12,'new_scenarios_created':False,'totals':dict(zip(t.MEASURES,EXPECTED)),'control':state,'pending':pending,'noop_rows_unchanged':True,'protected_databases_unchanged':True,'hop_load':json.loads((OUT/'bulk_load_hop.json').read_text()),'hop_noop':json.loads((OUT/'empty_queue_hop.json').read_text()),'query_execution_ms':{k:v[0]['Execution Time'] for k,v in plans.items()},'all_results_provisional':True})
    print('PASS bulk curated -> fact -> serving; 2400 facts, 757 aggregates, zero pending',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['setup','load','verify','deploy']);a=parser.parse_args()
    {'setup':setup,'load':load,'verify':lambda:verification('manual_verify'),'deploy':deploy}[a.phase]()
