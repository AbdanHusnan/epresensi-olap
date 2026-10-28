#!/usr/bin/env python3
"""Small actual-employee test. Source fixture writes are explicitly tagged.
Never truncate/backfill active raw; existing master comes only from active raw.
Phases are explicit and can be resumed after inspecting each durable result.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
DB='staging_bkd_e2e_two_shift_20261028'
PROJECT='/usr/local/tomcat/webapps/ROOT/config/projects/epresensi-staging'
RUNTIME=PROJECT+'/pipelines/validation/e2e_two_shift_20261028'
A,B=57342,32532
MARK='E2E_CURATED_TWO_SHIFT_20261028'

def cmd(args,input=None):
    return subprocess.run(args,input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout

def db(sql, target='staging_bkd', source=False):
    if source:
        command=['docker','exec','-i','epresensi-olap-postgres','sh','-c',
          'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d dbabsen_restore']
    else:
        command=['docker','exec','-i','epresensi-staging-postgres','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','admin_staging','-d',target]
    return cmd(command,sql.encode()).decode().strip()

def obj(sql,**kw):return json.loads(db(sql,**kw))
def result(name,value):
    (OUT/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
    print(name+': '+json.dumps(value),flush=True)

def copy_raw(table,where):
    # Binary COPY preserves all business columns, and never writes local PII files.
    data=cmd(['docker','exec','epresensi-staging-postgres','psql','-X','-q','-v','ON_ERROR_STOP=1','-U','admin_staging','-d','staging_bkd','-c',
       f'COPY (SELECT * FROM raw.{table} WHERE {where}) TO STDOUT WITH (FORMAT binary)'])
    cmd(['docker','exec','-i','epresensi-staging-postgres','psql','-X','-q','-v','ON_ERROR_STOP=1','-U','admin_staging','-d',DB,'-c',
       f'COPY raw.{table} FROM STDIN WITH (FORMAT binary)'],data)

def put_container(path,data):
    cmd(['docker','exec','-i','epresensi-hop-web','tee',path],data)

def install_connections():
    # Credentials remain in container/memory; never exported into the repository/log.
    for old,new,database in [('presensi_source','e2e_restore_20261028','dbabsen_restore'),
                             ('presensi_staging','e2e_raw_20261028','staging_bkd'),
                             ('presensi_staging','e2e_curated_20261028',DB)]:
        v=json.loads(cmd(['docker','exec','epresensi-hop-web','cat',PROJECT+'/metadata/rdbms/'+old+'.json']))
        v['name']=new;v['rdbms']['POSTGRESQL']['databaseName']=database
        put_container(PROJECT+'/metadata/rdbms/'+new+'.json',json.dumps(v).encode())
    cmd(['docker','exec','epresensi-hop-web','mkdir','-p',RUNTIME])
    p=ET.parse(ROOT/'hop/pipelines/curated/curated_incremental_batch.hpl')
    p.find('./info/name').text='curated_two_shift_test'
    p.find('./transform/connection').text='e2e_curated_20261028'
    ET.indent(p)
    p.write(OUT/'curated_two_shift_test.hpl',encoding='UTF-8',xml_declaration=True)
    put_container(RUNTIME+'/curated_two_shift_test.hpl',(OUT/'curated_two_shift_test.hpl').read_bytes())

def hop(file,log):
    command=['docker','exec','epresensi-hop-web','sh','-c',
     'cd /usr/local/tomcat/webapps/ROOT && exec ./hop-run.sh -j epresensi-staging -e presensi-staging-local -r local -f '+RUNTIME+'/'+file+' -l BASIC']
    with (OUT/(log+'.log')).open('wb') as f:
        subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True)
    print('Hop PASS: '+log,flush=True)

def batch(name,ids=None,snapshot=False):
    if not int(db(f"SELECT count(*) FROM etl_control.curated_batch WHERE batch_id='{name}'",target=DB)):
        arr='ARRAY['+','.join(map(str,ids or []))+']::integer[]'
        snap="(current_timestamp AT TIME ZONE 'Asia/Jakarta')::date" if snapshot else 'NULL'
        db(f"SELECT etl_control.enqueue_curated_batch('{name}',p_event_ids=>{arr},p_snapshot_date=>{snap},p_snapshot_complete=>{'true' if snapshot else 'false'})",target=DB)
    hop('curated_two_shift_test.hpl',name)
    r=obj(f"SELECT row_to_json(b) FROM etl_control.curated_batch b WHERE batch_id='{name}'",target=DB)
    assert r['status']=='APPLIED',r
    return r['result']

def summary(name,expected):
    r=obj('''SELECT json_build_object('rows',count(*),'active',sum(active_employee_days),
     'checkin',sum(checkin_days),'no_checkin',sum(no_checkin_days),'checkout',sum(checkout_days),
     'no_checkout',sum(no_checkout_days),'leave',sum(leave_days))
     FROM curated.cur_attendance_daily''',target=DB)
    assert r==expected,(name,r,expected)
    daily=obj('''SELECT json_agg(x ORDER BY pegawai_id) FROM
     (SELECT pegawai_id,tanggal,checkin_event_count,checkout_event_count,first_checkin_at,last_checkout_at,
      active_employee_days,checkin_days,checkout_days,no_checkin_days,no_checkout_days,is_date_final
      FROM curated.cur_attendance_daily) x''',target=DB)
    result(name,{'kpi':r,'daily':daily})

BASE={'rows':2,'active':2,'checkin':0,'no_checkin':2,'checkout':0,'no_checkout':2,'leave':0}

def setup():
    assert db(f"SELECT count(*) FROM pg_database WHERE datname='{DB}'",target='postgres')=='0','Target already exists; resume subsequent phase instead'
    assert db('SELECT count(*) FROM raw.raw_pegawai WHERE id IN(57342,32532) AND status IN(1,2,3,4) AND departemen=36545')=='2'
    assert db('SELECT count(*) FROM public.m_pegawai WHERE id=57342 AND status IN(1,2,3,4)',source=True)=='1'
    cmd(['docker','exec','epresensi-staging-postgres','createdb','-U','admin_staging',DB])
    ddl=cmd(['docker','exec','epresensi-staging-postgres','pg_dump','-U','admin_staging','-d','staging_bkd','--schema-only','--schema=raw','--schema=curated','--no-owner','--no-privileges'])
    cmd(['docker','exec','-i','epresensi-staging-postgres','psql','-X','-q','-v','ON_ERROR_STOP=1','-U','admin_staging','-d',DB],
        ddl+b'\nCREATE SCHEMA etl_control;\n'+(ROOT/'sql/staging/20261028_curated_incremental_etl.sql').read_bytes())
    for t,w in [('raw_pegawai','id IN(57342,32532)'),('raw_departemen','id=36545'),
                ('raw_jadwal','id IN(125519,125526)'),('raw_shift','id IN(22731,22732)')]:copy_raw(t,w)
    install_connections()
    result('setup',{'database':DB,'pegawai_event':A,'pegawai_control':B,'departemen':36545,
      'shift_ids':[22731,22732],'schedule_ids':[125519,125526],
      'existing_raw_evidence_ids':[168205076,168207135,168208636,168212299],
      'scope':'Two existing employees and references copied from backfilled raw. No source master mutation.'})

def snapshot():
    result('snapshot_batch',batch('E2E_V2_POPULATION',snapshot=True))
    summary('snapshot_result',BASE)

def source_events(phase):
    rows={1:[('morning_in',1,125519,'07:00')],
          2:[('afternoon_in',1,125526,'14:00'),('morning_out',2,125519,'14:05'),('afternoon_out',2,125526,'21:00')]}[phase]
    sql="""BEGIN;
    DO $$ BEGIN IF current_database()<>'dbabsen_restore' THEN RAISE EXCEPTION 'Restore only'; END IF; END $$;
    CREATE SCHEMA IF NOT EXISTS test_curated_v2_20261028;
    CREATE TABLE IF NOT EXISTS test_curated_v2_20261028.events(
     label text PRIMARY KEY, phase integer NOT NULL,event_id integer UNIQUE NOT NULL,
     pegawai_id integer NOT NULL,created_by_test_at timestamptz NOT NULL DEFAULT now());
    """
    for label,typ,jid,t in rows:
        sql+=f"""
        WITH ins AS (
        INSERT INTO public.t_checkinout
        (pegawai_id,departemen,checktype,created_at,updated_at,work_code,jadwal_id,hari,
         jam_masuk,jam_keluar,is_manual,is_wfh,keterangan)
        SELECT p.id,p.departemen,{typ},(current_timestamp AT TIME ZONE 'Asia/Jakarta')::date+time '{t}',
         current_timestamp AT TIME ZONE 'Asia/Jakarta',j.jenis,j.id,j.hari,j.jam_masuk,j.jam_keluar,
         true,0,'{MARK}:{label}'
        FROM public.m_pegawai p CROSS JOIN public.m_jadwal j
        WHERE p.id={A} AND j.id={jid} AND p.status IN(1,2,3,4)
          AND j.hari=CASE extract(isodow FROM current_timestamp AT TIME ZONE 'Asia/Jakarta')
           WHEN 1 THEN 'Mon' WHEN 2 THEN 'Tue' WHEN 3 THEN 'Wed' WHEN 4 THEN 'Thu'
           WHEN 5 THEN 'Fri' WHEN 6 THEN 'Sat' WHEN 7 THEN 'Sun' END
          AND NOT EXISTS(SELECT 1 FROM test_curated_v2_20261028.events WHERE label='{label}')
        RETURNING id,pegawai_id)
        INSERT INTO test_curated_v2_20261028.events(label,phase,event_id,pegawai_id)
        SELECT '{label}',{phase},id,pegawai_id FROM ins;
        """
    sql+='COMMIT;'
    db(sql,source=True)
    ids=obj(f'SELECT json_agg(event_id ORDER BY event_id) FROM test_curated_v2_20261028.events WHERE phase={phase}',source=True)
    assert len(ids)==len(rows),(phase,ids)
    result(f'phase{phase}_source',{'event_ids':ids,'phase':phase,'fixture_marker':MARK})
    return ids

def raw_hop(phase,ids):
    in_ids=','.join(map(str,ids))
    present=obj(f'SELECT COALESCE(json_agg(id),\'[]\'::json) FROM raw.raw_checkinout WHERE id IN({in_ids})')
    missing=sorted(set(ids)-set(present))
    if missing:
        raw=cmd(['docker','exec','epresensi-hop-web','cat',PROJECT+'/pipelines/raw/raw_checkinout.hpl'])
        p=ET.ElementTree(ET.fromstring(raw));name=f'raw_fixture_phase{phase}'
        p.find('./info/name').text=name
        p.find('./info/description').text='Append only recorded fixture event IDs. No truncation and no historical extraction.'
        transforms=p.findall('./transform');read,write=transforms
        read.find('connection').text='e2e_restore_20261028'
        read.find('sql').text=f"SELECT src.*,CURRENT_TIMESTAMP AS extracted_at,'{MARK}_PHASE{phase}'::text AS pipeline_run_id FROM public.t_checkinout src JOIN test_curated_v2_20261028.events f ON f.event_id=src.id WHERE src.id IN({','.join(map(str,missing))})"
        write.find('connection').text='e2e_raw_20261028';write.find('truncate').text='N'
        write.find('description').text='Append only new fixture IDs; raw backfill is preserved.'
        ET.indent(p);p.write(OUT/(name+'.hpl'),encoding='UTF-8',xml_declaration=True)
        put_container(RUNTIME+'/'+name+'.hpl',(OUT/(name+'.hpl')).read_bytes())
        hop(name+'.hpl',name)
    source_hash=obj(f"SELECT json_object_agg(id,md5(to_jsonb(c)::text)) FROM public.t_checkinout c WHERE id IN({in_ids})",source=True)
    raw_hash=obj(f"SELECT json_object_agg(id,md5((to_jsonb(c)-'extracted_at'-'pipeline_run_id')::text)) FROM raw.raw_checkinout c WHERE id IN({in_ids})")
    assert source_hash==raw_hash,(source_hash,raw_hash)
    result(f'phase{phase}_raw_verification',{'count':len(ids),'all_business_columns_match':True,'hashes':raw_hash})
    exists=obj(f"SELECT COALESCE(json_agg(id),'[]'::json) FROM raw.raw_checkinout WHERE id IN({in_ids})",target=DB)
    new=sorted(set(ids)-set(exists))
    if new:copy_raw('raw_checkinout','id IN('+','.join(map(str,new))+')')

def phase(n):
    ids=source_events(n);raw_hop(n,ids)
    result(f'phase{n}_curated_batch',batch(f'E2E_V2_EVENTS_{n}',ids))
    expected=BASE|{'checkin':1,'no_checkin':1}
    if n==2:expected|={'checkout':1,'no_checkout':1}
    summary(f'phase{n}_result',expected)
    a=obj(f'SELECT row_to_json(d) FROM curated.cur_attendance_event_daily d WHERE pegawai_id={A}',target=DB)
    assert a['checkin_event_count']==(1 if n==1 else 2)
    assert a['checkout_event_count']==(0 if n==1 else 2)
    assert a['first_checkin_at'].endswith('07:00:00')
    if n==2:assert a['last_checkout_at'].endswith('21:00:00') and a['shift_count']==2

def noop():
    before=db('SELECT md5(string_agg(pegawai_id::text||tanggal::text||xmin::text,\'|\' ORDER BY pegawai_id,tanggal)) FROM curated.cur_attendance_daily',target=DB)
    ids=obj('SELECT json_agg(event_id ORDER BY event_id) FROM test_curated_v2_20261028.events',source=True)
    r=batch('E2E_V2_NOOP',ids)
    after=db('SELECT md5(string_agg(pegawai_id::text||tanggal::text||xmin::text,\'|\' ORDER BY pegawai_id,tanggal)) FROM curated.cur_attendance_daily',target=DB)
    assert before==after and r['attendance_daily_changes']==0 and r['event_changes']==0
    result('noop_result',{'same_row_versions':True,'batch':r})

def verify():
    summary('final_result',BASE|{'checkin':1,'no_checkin':1,'checkout':1,'no_checkout':1})
    r=obj('''SELECT json_build_object('event_rows',(SELECT count(*) FROM curated.cur_event_attendance),
    'event_daily_rows',(SELECT count(*) FROM curated.cur_attendance_event_daily),
    'population_rows',(SELECT count(*) FROM curated.cur_employee_population_daily),
    'daily_rows',(SELECT count(*) FROM curated.cur_attendance_daily),
    'ready_batches',(SELECT count(*) FROM etl_control.curated_batch WHERE status='READY'))''',target=DB)
    assert r=={'event_rows':4,'event_daily_rows':1,'population_rows':2,'daily_rows':2,'ready_batches':0},r
    result('verification',r|{'source_master_changed':False,'raw_backfill_repeated':False,'source_fixture_events_retained':4})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['setup','snapshot','batch1','batch2','noop','verify']);a=p.parse_args()
    try:
        {'setup':setup,'snapshot':snapshot,'batch1':lambda:phase(1),'batch2':lambda:phase(2),'noop':noop,'verify':verify}[a.phase]()
    except subprocess.CalledProcessError as exc:
        print('Command failed:',exc.cmd,flush=True)
        if exc.stderr:print(exc.stderr.decode(),flush=True)
        raise
