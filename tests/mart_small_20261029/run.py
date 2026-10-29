#!/usr/bin/env python3
"""Small downstream Hop integration. Only dedicated test DBs are writable."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
SOURCE='staging_bkd_mart_small_20261029'
TARGET='mart_bkd_small_20261029'
REFERENCE='staging_bkd_bulk_20261028'
SC='epresensi-staging-postgres'
MC='epresensi-mart-postgres'
HOP='epresensi-hop-web'
PROJECT='/usr/local/tomcat/webapps/ROOT/config/projects/epresensi-staging'
RUNTIME=PROJECT+'/pipelines/validation/mart_small_20261029'
MEASURES=['active_employee_days','checkin_days','checkout_days','no_checkin_days','no_checkout_days','leave_days','required_checkin_days','required_checkout_days','excused_checkin_days','excused_checkout_days','required_checkin_present_days','required_checkout_present_days']


def command(args, data=None, check=True):
    p=subprocess.run(args,input=data,text=True,capture_output=True)
    if check and p.returncode: raise RuntimeError(p.stderr[-5000:])
    return p


def sql(query, target=False, database=None, check=True):
    container=MC if target else SC
    database=database or (TARGET if target else SOURCE)
    return command(['docker','exec','-i',container,'sh','-c',
                    'exec psql -X -q -A -t -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"',
                    'psql',database],query,check)


def scalar(query, **kwargs): return sql(query,**kwargs).stdout.strip()
def data(query, **kwargs): return json.loads(scalar(query,**kwargs) or 'null')
def q(value): return "'"+str(value).replace("'","''")+"'"
def save(name,value): (OUT/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
def require(value,label):
    if not value: raise AssertionError(label)


def rows(table, target=False):
    return data(f"SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY pegawai_id{'_sumber' if target else ''},tanggal),'[]') FROM {table} t",target=target)


def write_runtime(path,content):
    command(['docker','exec','-i',HOP,'sh','-c','umask 077; cat > "$1"','write',path],content)


def deploy():
    command(['docker','exec',HOP,'mkdir','-p',RUNTIME])
    for alias,template,db in [('small_mart_source_20261029','presensi_staging',SOURCE),('small_mart_target_20261029','presensi_mart',TARGET)]:
        meta=json.loads(command(['docker','exec',HOP,'cat',PROJECT+'/metadata/rdbms/'+template+'.json']).stdout)
        meta['name']=alias
        meta['rdbms']['POSTGRESQL']['databaseName']=db
        write_runtime(PROJECT+'/metadata/rdbms/'+alias+'.json',json.dumps(meta))
    for path in (ROOT/'hop/pipelines/mart').glob('*.hpl'):
        xml=ET.fromstring(path.read_text())
        for c in xml.findall('transform/connection'):
            c.text={'presensi_staging':'small_mart_source_20261029','presensi_mart':'small_mart_target_20261029'}[c.text]
        ET.indent(xml)
        text=ET.tostring(xml,encoding='unicode',xml_declaration=True)
        (OUT/path.name).write_text(text)
        write_runtime(RUNTIME+'/'+path.name,text)
    xml=ET.parse(ROOT/'hop/workflows/mart/curated_to_serving.hwf').getroot()
    for f in xml.findall('actions/action/filename'): f.text=RUNTIME+'/'+Path(f.text).name
    ET.indent(xml)
    text=ET.tostring(xml,encoding='unicode',xml_declaration=True)
    (OUT/'curated_to_serving.hwf').write_text(text)
    write_runtime(RUNTIME+'/curated_to_serving.hwf',text)


def hop(label, apply_only=False, expect_failure=False):
    filename='curated_to_fact_serving_batch.hpl' if apply_only else 'curated_to_serving.hwf'
    start=time.monotonic()
    result=command(['docker','exec',HOP,'sh','-c',
                    'cd /usr/local/tomcat/webapps/ROOT && exec ./hop-run.sh -j epresensi-staging -e presensi-staging-local -r local -f "$1" -l BASIC',
                    'hop-test',RUNTIME+'/'+filename],check=False)
    (OUT/(label+'.log')).write_text(result.stdout+result.stderr)
    if not expect_failure:
        require(result.returncode==0, f'Hop failed: {label}, see log')
    save(label+'_hop',{'exit_code':result.returncode,'seconds':round(time.monotonic()-start,3),'expected_failure':expect_failure})
    return result


def columns(table):
    schema,name=table.split('.')
    return data(f"SELECT jsonb_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema={q(schema)} AND table_name={q(name)} AND is_generated='NEVER'")


def insert_json(table, items):
    cols=','.join(columns(table))
    sql(f'INSERT INTO {table} ({cols}) SELECT {cols} FROM jsonb_populate_recordset(NULL::{table},{q(json.dumps(items))}::jsonb)')


def guards():
    return {
        'reference':data("SELECT jsonb_build_object('rows',count(*),'hash',md5(string_agg(to_jsonb(d)::text,'|' ORDER BY pegawai_id,tanggal))) FROM curated.cur_attendance_daily d",database=REFERENCE),
        'active_mart':data("SELECT jsonb_build_object('fact',(SELECT count(*) FROM mart_kehadiran.fact_kehadiran_daily),'agg',(SELECT count(*) FROM serving.agg_kehadiran_departemen_harian),'batches',(SELECT count(*) FROM etl_control.mart_batch),'receipts',(SELECT count(*) FROM etl_control.mart_delivery_receipt))",target=True,database='mart_bkd'),
        'active_staging':data("SELECT jsonb_build_object('daily',(SELECT count(*) FROM curated.cur_attendance_daily),'bootstrap',(SELECT bootstrap_prepared FROM etl_control.mart_outbox_stream),'sequence',(SELECT last_sequence FROM etl_control.mart_outbox_stream),'outbox',(SELECT count(*) FROM etl_control.mart_outbox_batch))",database='staging_bkd'),
    }


def setup():
    for target,db in [(False,SOURCE),(True,TARGET)]:
        require(scalar(f'SELECT count(*) FROM pg_database WHERE datname={q(db)}',target=target,database='postgres')=='0','Database already exists; do not reset')
    save('protected_before',guards())
    sample=data("""WITH chosen AS(SELECT DISTINCT ON(scenario) scenario,emp,dep FROM test_bulk.cohort ORDER BY scenario,n)
     SELECT jsonb_agg(jsonb_build_object('scenario',c.scenario,'employee',c.emp,'department',c.dep,'daily',to_jsonb(d),'population',to_jsonb(p)) ORDER BY scenario)
     FROM chosen c JOIN curated.cur_attendance_daily d ON d.pegawai_id=c.emp
     JOIN curated.cur_employee_population_daily p USING(pegawai_id,tanggal)""",database=REFERENCE)
    require(len(sample)==12,'Exactly one row per bulk scenario')
    # Explicit expected flags from the final corrected bulk scenarios.
    expected=[(0,0,0,0),(1,1,0,0),(1,0,0,0),(0,1,0,0),(0,0,0,0),(0,1,1,0),(1,0,0,1),(0,0,0,1),(0,0,0,1),(1,1,1,1),(2,2,0,0),(0,0,1,1)]
    for row in sample:
        d=row['daily'];e=expected[row['scenario']]
        require((d['checkin_event_count'],d['checkout_event_count'],int(d['has_excused_checkin']),int(d['has_excused_checkout']))==e,'Bulk final fixture differs; stop')
    save('sample_manifest',sample)
    for container,db in [(SC,SOURCE),(MC,TARGET)]:
        command(['docker','exec',container,'sh','-c','exec createdb -U "$POSTGRES_USER" "$1"','createdb',db])
    dump=command(['docker','exec',SC,'sh','-c','exec pg_dump -U "$POSTGRES_USER" -d "$1" --schema-only --no-owner --no-privileges -t curated.cur_attendance_daily -t curated.cur_employee_population_daily','dump',REFERENCE]).stdout
    sql('CREATE SCHEMA curated; CREATE SCHEMA etl_control;\n'+dump)
    insert_json('curated.cur_employee_population_daily',[r['population'] for r in sample])
    insert_json('curated.cur_attendance_daily',[r['daily'] for r in sample])
    sql((ROOT/'sql/staging/20261028_mart_outbox.sql').read_text())
    sql((ROOT/'sql/mart/20261028_attendance_daily.sql').read_text(),target=True)
    sql((ROOT/'sql/mart/20261028_mart_incremental_etl.sql').read_text(),target=True)
    sql('CREATE SCHEMA test_small; CREATE TABLE test_small.results(phase text PRIMARY KEY,result jsonb);')
    deploy()
    for table,key in [('curated.cur_employee_population_daily','population'),('curated.cur_attendance_daily','daily')]:
        actual=rows(table)
        require(sorted(actual,key=lambda x:x['pegawai_id'])==sorted([r[key] for r in sample],key=lambda x:x['pegawai_id']),'Source copy mismatch')
    save('setup',{'source':SOURCE,'target':TARGET,'rows':12,'passed':True})


def versions():
    return data("SELECT COALESCE(jsonb_object_agg(pegawai_id_sumber::text||'/'||tanggal::text,xmin::text),'{}') FROM mart_kehadiran.fact_kehadiran_daily",target=True)


def aggregate_versions():
    return data("SELECT COALESCE(jsonb_object_agg(departemen_key::text||'/'||tanggal::text,xmin::text),'{}') FROM serving.agg_kehadiran_departemen_harian",target=True)


def verify(label, expected_totals=None):
    require(scalar('''SELECT count(*) FROM curated.cur_attendance_daily d
      LEFT JOIN curated.cur_employee_population_daily p USING(pegawai_id,tanggal)
      WHERE p.pegawai_id IS NULL OR d.departemen_id IS DISTINCT FROM p.departemen_id
      OR d.is_employee_active IS DISTINCT FROM p.is_employee_active''')=='0',
      'Daily assignment/status differs from its dated population snapshot')
    src=rows('curated.cur_attendance_daily')
    fact=rows('mart_kehadiran.fact_kehadiran_daily',True)
    expected={(r['pegawai_id'],r['tanggal']):r for r in src}
    require(len(src)==len(fact),'Fact row count mismatch')
    totals={m:0 for m in MEASURES}
    bydept={}
    for f in fact:
        key=(f['pegawai_id_sumber'],f['tanggal']);d=expected[key]
        for k,v in d.items():
            target_key={'pegawai_id':'pegawai_id_sumber','departemen_id':'departemen_id_sumber'}.get(k,k)
            if target_key in f: require(f[target_key]==v,f'{label}: {key} {k} differs')
        a=d['is_employee_active'] is True;m=d['has_masuk'];p=d['has_pulang'];ei=d['has_excused_checkin'];eo=d['has_excused_checkout'];i=d['has_valid_leave']
        oracle=list(map(int,[a,a and m,a and p,a and not ei and not m,a and not eo and not p,a and i,a and not ei,a and not eo,a and ei,a and eo,a and not ei and m,a and not eo and p]))
        for metric,value in zip(MEASURES,oracle):
            require(f[metric]==value,f'{label} oracle {key} {metric}')
            totals[metric]+=value
        partition=(f['tanggal'],f['departemen_key'])
        group=bydept.setdefault(partition,{**{m:0 for m in MEASURES},'fact_rows':0,'review_rows':0,'nonfinal_rows':0})
        for metric,value in zip(MEASURES,oracle):group[metric]+=value
        group['fact_rows']+=1;group['review_rows']+=int(f['perlu_review']);group['nonfinal_rows']+=int(not f['is_date_final'])
    agg=data("SELECT COALESCE(jsonb_agg(to_jsonb(a)),'[]') FROM serving.agg_kehadiran_departemen_harian a",target=True)
    require(len(agg)==len(bydept),'Aggregate partition count')
    for row in agg:
        e=bydept[(row['tanggal'],row['departemen_key'])]
        for k,v in e.items():require(row[k]==v,f'Aggregate {label} {k}')
    if expected_totals:require([totals[m] for m in MEASURES]==expected_totals,'Initial independent totals')
    views=data("SELECT jsonb_agg(to_jsonb(v) ORDER BY tanggal) FROM serving.v_kehadiran_instansi_harian v",target=True)
    for v in views or []:
        require(v['is_provisional'] and not v['is_data_complete'],'Provisional/complete state')
        for rate,num,den in [('checkin_rate','checkin_days','active_employee_days'),('checkout_rate','checkout_days','active_employee_days'),('required_checkin_rate','required_checkin_present_days','required_checkin_days'),('required_checkout_rate','required_checkout_present_days','required_checkout_days')]:
            require(v[rate] is None if not v[den] else abs(v[rate]-100*v[num]/v[den])<1e-8,'Rate formula')
    require(scalar('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL')=='0','Pending outbox after workflow')
    result={'phase':label,'passed':True,'fact_rows':len(fact),'aggregate_rows':len(agg),'totals':totals,'views':views}
    save(label,result)
    sql(f'INSERT INTO test_small.results VALUES({q(label)},{q(json.dumps(result))}::jsonb) ON CONFLICT(phase) DO UPDATE SET result=excluded.result')
    print('PASS',label,'rows',len(fact),flush=True)
    return result


def baseline():
    if scalar('SELECT bootstrap_prepared FROM etl_control.mart_outbox_stream')=='f':
        save('bootstrap',data('SELECT etl_control.prepare_mart_bootstrap()'))
    hop('baseline')
    verify('baseline',[12,5,5,5,3,6,9,7,3,5,4,4])
    before=versions();ab=aggregate_versions()
    hop('empty_queue')
    require(versions()==before and aggregate_versions()==ab,'Empty queue rewrote rows')
    sql("UPDATE curated.cur_attendance_daily SET source_snapshot_at=source_snapshot_at+interval '1 second'")
    # Capture ignores timestamps, and target preserves the previous source timestamp.
    require(scalar('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL')=='0','Timestamp-only changes should not enqueue')
    # Restore timestamp fixture to retain strict audit comparison.
    for r in json.loads((OUT/'sample_manifest.json').read_text()):
        sql(f"UPDATE curated.cur_attendance_daily SET source_snapshot_at={q(r['daily']['source_snapshot_at'])} WHERE pegawai_id={r['employee']}")
    hop('noop')
    require(versions()==before and aggregate_versions()==ab,'No-op rewrote rows')
    verify('noop')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['setup','deploy','baseline','verify'])
    args=parser.parse_args()
    {'setup':setup,'deploy':deploy,'baseline':baseline,'verify':lambda:verify('manual_verify')}[args.phase]()
