#!/usr/bin/env python3
"""Bulk test on actual employee masters, tagged restore fixtures, isolated raw/curated."""
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DB = 'staging_bkd_bulk_20261028'
SCHEMA = 'test_bulk_curated_20261028'
MARK = 'BULK_CURATED_20261028'
PROJECT = '/usr/local/tomcat/webapps/ROOT/config/projects/epresensi-staging'
RUNTIME = PROJECT + '/pipelines/validation/bulk_attendance_20261028'
LABELS = ['no_events', 'both_events', 'checkin_only', 'checkout_only', 'full_leave',
          'leave_checkin_with_checkout', 'leave_checkout_with_checkin',
          'leave_checkin_missing_checkout', 'leave_checkout_missing_checkin',
          'full_leave_with_events', 'two_shifts', 'overlapping_partial_leaves']


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


base = module('small_test', ROOT / 'tests/e2e_two_shift_20261028/run.py')
base.DB, base.OUT, base.RUNTIME = DB, OUT, RUNTIME
cmd, db, obj = base.cmd, base.db, base.obj


def sql(s):
    return db(s, target=DB)


def data(s):
    return obj(s, target=DB)


def save(name, value):
    (OUT / (name + '.json')).write_text(json.dumps(value, indent=2) + '\n')


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def setup():
    assert_true(db(f"SELECT count(*) FROM pg_database WHERE datname='{DB}'", target='postgres') == '0',
                'Target exists: inspect recorded phases, do not recreate automatically')
    candidates = obj("""WITH schedules AS (
      SELECT DISTINCT ON (s.departemen_id,s.id) s.departemen_id,s.id,j.id jid,j.jam_masuk
      FROM raw.raw_shift s JOIN raw.raw_jadwal j ON j.jenis=s.id
      WHERE s.status=true AND j.hari=trim(to_char(current_timestamp AT TIME ZONE 'Asia/Jakarta','Dy'))
        AND j.jam_keluar>j.jam_masuk
      ORDER BY s.departemen_id,s.id,j.jam_masuk,j.id
    ), pairs AS (
      SELECT departemen_id,array_agg(jid ORDER BY jam_masuk,id) ids FROM schedules
      GROUP BY departemen_id HAVING count(*)>=2
    ), people AS (
      SELECT p.id,p.departemen,min(u.id) uid,pa.ids[1] j1,pa.ids[2] j2,
        row_number() OVER(PARTITION BY p.departemen ORDER BY p.id) dept_rank
      FROM raw.raw_pegawai p JOIN pairs pa ON pa.departemen_id=p.departemen
      JOIN raw.raw_user u ON u.pegawai_id=p.id WHERE p.status IN(1,2,3,4)
      GROUP BY p.id,p.departemen,pa.ids
    ) SELECT json_agg(x) FROM (SELECT id,departemen,uid,j1,j2 FROM people
      ORDER BY dept_rank,departemen,id LIMIT 2400) x""")
    assert_true(len(candidates) == 2400, 'Need 2400 real eligible employees')
    # Validate IDs against restore before any fixture mutation.
    values = ','.join(f"({i+1},{p['id']},{p['departemen']},{p['uid']},{p['j1']},{p['j2']},{i%12})"
                      for i,p in enumerate(candidates))
    preflight = f"""WITH cohort(n,emp,dep,uid,j1,j2,scenario) AS (VALUES {values})
      SELECT count(*) FROM cohort c JOIN public.m_pegawai p ON p.id=c.emp
      JOIN public.m_user u ON u.id=c.uid AND u.pegawai_id=p.id
      JOIN public.m_jadwal a ON a.id=c.j1 JOIN public.m_jadwal b ON b.id=c.j2
      WHERE p.departemen=c.dep AND p.status IN(1,2,3,4)
      AND a.jam_keluar>a.jam_masuk AND b.jam_keluar>b.jam_masuk"""
    assert_true(db(preflight, source=True) == '2400', 'Source/raw cohort mismatch')
    cmd(['docker','exec','epresensi-staging-postgres','createdb','-U','admin_staging',DB])
    ddl = cmd(['docker','exec','epresensi-staging-postgres','pg_dump','-U','admin_staging',
               '-d','staging_bkd','--schema-only','--schema=raw','--schema=curated','--no-owner','--no-privileges'])
    installer = module('installer', ROOT / 'hop/scripts/install_curated_etl.py')
    cmd(['docker','exec','-i','epresensi-staging-postgres','psql','-X','-q','-v','ON_ERROR_STOP=1',
         '-U','admin_staging','-d',DB], ddl + b'\nCREATE SCHEMA etl_control;\n' + installer.installation_sql().encode())
    sql(f"""CREATE SCHEMA test_bulk;
      CREATE TABLE test_bulk.cohort(n integer PRIMARY KEY,emp integer UNIQUE,dep integer,
        uid integer,j1 integer,j2 integer,scenario integer);
      INSERT INTO test_bulk.cohort VALUES {values};
      CREATE TABLE test_bulk.config AS SELECT (current_timestamp AT TIME ZONE 'Asia/Jakarta')::date test_date;
      CREATE TABLE test_bulk.results(phase text PRIMARY KEY,result jsonb);
      CREATE TABLE test_bulk.row_versions AS SELECT pegawai_id,tanggal,xmin::text version
        FROM curated.cur_attendance_daily;""")
    ids = ','.join(str(p['id']) for p in candidates)
    deps = ','.join(str(x) for x in sorted({p['departemen'] for p in candidates}))
    users = ','.join(str(p['uid']) for p in candidates)
    jids = ','.join(str(x) for x in sorted({p[k] for p in candidates for k in ('j1','j2')}))
    for table,where in [('raw_pegawai',f'id IN({ids})'),('raw_departemen',f'id IN({deps})'),
      ('raw_user',f'id IN({users})'),('raw_jadwal',f'id IN({jids})'),
      ('raw_shift',f'id IN(SELECT jenis FROM raw.raw_jadwal WHERE id IN({jids}))'),
      ('raw_jenis_ijin','id=1'),('raw_tipe_ijin','id IN(SELECT tipe_id FROM raw.raw_jenis_ijin WHERE id=1)')]:
        base.copy_raw(table,where)
    # Only test-owned tables plus tagged new transactions in restore; no master updates.
    db(f"""BEGIN;
      DO $$ BEGIN IF current_database()<>'dbabsen_restore' THEN RAISE EXCEPTION 'restore only'; END IF; END $$;
      CREATE SCHEMA {SCHEMA};
      CREATE TABLE {SCHEMA}.cohort(n integer PRIMARY KEY,emp integer UNIQUE,dep integer,
        uid integer,j1 integer,j2 integer,scenario integer);
      INSERT INTO {SCHEMA}.cohort VALUES {values};
      CREATE TABLE {SCHEMA}.events(id integer PRIMARY KEY,phase integer,emp integer);
      CREATE TABLE {SCHEMA}.leaves(id integer PRIMARY KEY,emp integer);
      COMMIT;""", source=True)
    for old,new,database in [('presensi_source','bulk_restore_20261028','dbabsen_restore'),
                             ('presensi_staging','bulk_test_20261028',DB)]:
        metadata=json.loads(cmd(['docker','exec','epresensi-hop-web','cat',PROJECT+'/metadata/rdbms/'+old+'.json']))
        metadata['name']=new
        metadata['rdbms']['POSTGRESQL']['databaseName']=database
        base.put_container(PROJECT+'/metadata/rdbms/'+new+'.json',json.dumps(metadata).encode())
    cmd(['docker','exec','epresensi-hop-web','mkdir','-p',RUNTIME])
    tree=ET.parse(ROOT/'hop/pipelines/curated/curated_incremental_batch.hpl')
    tree.find('./info/name').text='bulk_curated'
    tree.find('./transform/connection').text='bulk_test_20261028'
    pipeline(tree,'bulk_curated')
    save('setup',{'database':DB,'employees':2400,'departments':len(set(p['departemen'] for p in candidates)),
       'per_scenario':200,'scenarios':LABELS,'date':sql('SELECT test_date FROM test_bulk.config'),
       'active_raw_modified':False,'source_master_modified':False})
    print('SETUP complete: 2400 actual employees',flush=True)


def pipeline(tree,name):
    ET.indent(tree)
    tree.write(OUT/(name+'.hpl'),encoding='UTF-8',xml_declaration=True)
    base.put_container(RUNTIME+'/'+name+'.hpl',(OUT/(name+'.hpl')).read_bytes())


def fixtures():
    date=sql('SELECT test_date FROM test_bulk.config')
    db(f"""BEGIN;
      WITH definitions AS (
        SELECT c.*,1 typ,1 phase,c.j1 jid FROM {SCHEMA}.cohort c WHERE scenario IN(1,2,6,9,10)
        UNION ALL SELECT c.*,2,2,c.j1 FROM {SCHEMA}.cohort c WHERE scenario IN(1,3,5,9,10)
        UNION ALL SELECT c.*,1,2,c.j2 FROM {SCHEMA}.cohort c WHERE scenario=10
        UNION ALL SELECT c.*,2,2,c.j2 FROM {SCHEMA}.cohort c WHERE scenario=10
      ), ins AS (
        INSERT INTO public.t_checkinout(pegawai_id,departemen,checktype,created_at,updated_at,
          work_code,jadwal_id,hari,jam_masuk,jam_keluar,is_manual,is_wfh,keterangan)
        SELECT d.emp,d.dep,d.typ,date '{date}'+CASE WHEN d.typ=1 THEN j.jam_masuk ELSE j.jam_keluar END,
          current_timestamp AT TIME ZONE 'Asia/Jakarta',j.jenis,j.id,j.hari,j.jam_masuk,j.jam_keluar,
          true,0,'{MARK}:phase='||d.phase
        FROM definitions d JOIN public.m_jadwal j ON j.id=d.jid
        RETURNING id,pegawai_id,keterangan)
      INSERT INTO {SCHEMA}.events SELECT id,right(keterangan,1)::integer,pegawai_id FROM ins;
      WITH definitions AS (
        SELECT c.*,CASE WHEN scenario IN(4,9) THEN 1 WHEN scenario IN(5,7,11) THEN 2 ELSE 3 END typ
        FROM {SCHEMA}.cohort c WHERE scenario IN(4,5,6,7,8,9,11)
        UNION ALL SELECT c.*,3 FROM {SCHEMA}.cohort c WHERE scenario=11
      ), ins AS (
        INSERT INTO public.t_perizinan(user_id,nama,departemen,tipe_ijin,jenis_ijin,alasan,catatan,
          approval,approval_at,created_at,tgl_ijin,tgl_ijin_sampai,pegawai_id,updated_at)
        SELECT uid,'BULK TEST FIXTURE',dep,typ,1,'{MARK}','{MARK}',true,
          current_timestamp AT TIME ZONE 'Asia/Jakarta',current_timestamp AT TIME ZONE 'Asia/Jakarta',
          date '{date}',date '{date}',emp,current_timestamp AT TIME ZONE 'Asia/Jakarta' FROM definitions
        RETURNING id,pegawai_id)
      INSERT INTO {SCHEMA}.leaves SELECT id,pegawai_id FROM ins;
      COMMIT;""",source=True)
    evidence=obj(f"""SELECT json_build_object('events',(SELECT count(*) FROM {SCHEMA}.events),
      'leaves',(SELECT count(*) FROM {SCHEMA}.leaves),
      'event_min',(SELECT min(id) FROM {SCHEMA}.events),'event_max',(SELECT max(id) FROM {SCHEMA}.events),
      'leave_min',(SELECT min(id) FROM {SCHEMA}.leaves),'leave_max',(SELECT max(id) FROM {SCHEMA}.leaves))""",source=True)
    assert_true(evidence['events']==2400 and evidence['leaves']==1600,evidence)
    save('source_fixtures',evidence)
    print('FIXTURES complete: 2400 events, 1600 leaves',flush=True)


def raw_load(entity,phase,correction=False):
    table='checkinout' if entity=='events' else 'perizinan'
    predicate=f'f.phase={phase}' if entity=='events' else 'true'
    if correction:
        predicate='f.emp IN(SELECT emp FROM '+SCHEMA+'.cohort WHERE scenario IN(4,7))'
    rows=obj(f'SELECT json_agg(id ORDER BY id) FROM {SCHEMA}.{entity} f WHERE {predicate}',source=True)
    ids=','.join(map(str,rows))
    if correction:
        # Test harness refreshes ONLY its own fixture subset; manifests publish after successful load.
        sql(f'DELETE FROM raw.raw_{table} WHERE id IN({ids})')
    name=f'raw_{table}_{phase}'
    tree=ET.ElementTree(ET.fromstring(cmd(['docker','exec','epresensi-hop-web','cat',
                       PROJECT+'/pipelines/raw/raw_'+table+'.hpl'])))
    tree.find('./info/name').text=name
    read,write=tree.findall('./transform')
    read.find('connection').text='bulk_restore_20261028'
    read.find('sql').text=f"SELECT src.*,CURRENT_TIMESTAMP AS extracted_at,'{MARK}_{phase}'::text AS pipeline_run_id FROM public.t_{table} src JOIN {SCHEMA}.{entity} f ON f.id=src.id WHERE {predicate}"
    write.find('connection').text='bulk_test_20261028'
    write.find('truncate').text='N'
    pipeline(tree,name)
    base.hop(name+'.hpl',name)
    source_hash=obj(f"SELECT json_object_agg(src.id,md5(to_jsonb(src)::text)) FROM public.t_{table} src JOIN {SCHEMA}.{entity} f ON f.id=src.id WHERE {predicate}",source=True)
    raw_hash=data(f"SELECT json_object_agg(id,md5((to_jsonb(r)-'extracted_at'-'pipeline_run_id')::text)) FROM raw.raw_{table} r WHERE id IN({ids})")
    assert_true(source_hash==raw_hash,'source/raw business column hash mismatch')
    save(name+'_verification',{'count':len(rows),'all_business_columns_match':True})
    return rows


def batch(name,events=None,leaves=None,snapshot=False):
    a=lambda ids:'ARRAY['+','.join(map(str,ids or []))+']::integer[]'
    sql(f"SELECT etl_control.enqueue_curated_batch('{name}',p_event_ids=>{a(events)},p_leave_ids=>{a(leaves)},"
        f"p_snapshot_date=>{'(SELECT test_date FROM test_bulk.config)' if snapshot else 'NULL'},p_snapshot_complete=>{'true' if snapshot else 'false'})")
    start=time.monotonic()
    base.hop('bulk_curated.hpl',name)
    record=data(f"SELECT row_to_json(b) FROM etl_control.curated_batch b WHERE batch_id='{name}'")
    assert_true(record['status']=='APPLIED',record)
    record['hop_wall_seconds']=round(time.monotonic()-start,3)
    save(name,record)
    return record['result']


def verify(phase,correction=False):
    # Independent, hand-specified scenario oracle: in/out counts, exemption sides.
    final=[(0,0,0,0),(1,1,0,0),(1,0,0,0),(0,1,0,0),(0,0,1,1),(0,1,1,0),
           (1,0,0,1),(0,0,1,0),(0,0,0,1),(1,1,1,1),(2,2,0,0),(0,0,1,1)]
    if correction:
        final[4]=(0,0,0,0)
        final[7]=(0,0,0,1)
    expected={}
    for s,(ci,co,ei,eo) in enumerate(final):
        if phase=='snapshot':ci=co=ei=eo=0
        elif phase=='batch1':
            co=0
            if s==10:ci=1
        expected[s]=(ci,co,ei,eo)
    daily=data('''SELECT json_agg(x ORDER BY emp) FROM (
      SELECT c.emp,c.scenario,d.tanggal,d.checkin_event_count ci,d.checkout_event_count co,
        d.active_employee_days active,d.checkin_days present_in,d.checkout_days present_out,
        d.excused_checkin_days ei,d.excused_checkout_days eo,d.required_checkin_days ri,
        d.required_checkout_days ro,d.required_checkin_present_days pi,d.required_checkout_present_days po,
        d.no_checkin_days ni,d.no_checkout_days no,d.leave_days ld,d.first_checkin_at,d.last_checkout_at
      FROM test_bulk.cohort c LEFT JOIN curated.cur_attendance_daily d ON d.pegawai_id=c.emp) x''')
    assert_true(len(daily)==2400,'one daily row per employee')
    totals={k:0 for k in ('active','present_in','present_out','ei','eo','ri','ro','pi','po','ni','no','ld')}
    for d in daily:
        ci,co,ei,eo=expected[d['scenario']]
        oracle={'ci':ci,'co':co,'active':1,'present_in':int(ci>0),'present_out':int(co>0),
                'ei':ei,'eo':eo,'ri':1-ei,'ro':1-eo,'pi':int(ci>0)*(1-ei),'po':int(co>0)*(1-eo),
                'ni':int(ci==0)*(1-ei),'no':int(co==0)*(1-eo),'ld':int(ei or eo)}
        assert_true(all(d[k]==v for k,v in oracle.items()),{'phase':phase,'employee':d['emp'],'actual':d,'expected':oracle})
        for k in totals:totals[k]+=d[k]
    assert_true(sql('''SELECT count(*) FROM curated.cur_attendance_daily WHERE
      active_employee_days<>required_checkin_days+excused_checkin_days OR
      active_employee_days<>required_checkout_days+excused_checkout_days OR
      required_checkin_days<>required_checkin_present_days+no_checkin_days OR
      required_checkout_days<>required_checkout_present_days+no_checkout_days''')=='0','KPI identities')
    if phase not in ('snapshot','batch1'):
        assert_true(sql('''SELECT count(*) FROM test_bulk.cohort c
          JOIN raw.raw_jadwal a ON a.id=c.j1 JOIN raw.raw_jadwal b ON b.id=c.j2
          JOIN curated.cur_attendance_event_daily d ON d.pegawai_id=c.emp
          CROSS JOIN test_bulk.config cfg WHERE c.scenario=10 AND
          (d.shift_count<>2 OR d.first_checkin_at<>cfg.test_date+least(a.jam_masuk,b.jam_masuk)
           OR d.last_checkout_at<>cfg.test_date+greatest(a.jam_keluar,b.jam_keluar))''')=='0',
          'two-shift MIN/MAX and distinct shift count')
    groups=data('''SELECT json_agg(x ORDER BY scenario) FROM (SELECT c.scenario,count(*) employees,
      sum(d.checkin_days) checkin,sum(d.checkout_days) checkout,sum(d.no_checkin_days) no_checkin,
      sum(d.no_checkout_days) no_checkout,sum(d.leave_days) leave_days
      FROM test_bulk.cohort c JOIN curated.cur_attendance_daily d ON d.pegawai_id=c.emp GROUP BY c.scenario) x''')
    result={'phase':phase,'passed':True,'checked_employee_dates':len(daily),'totals':totals,'groups':groups}
    save(phase+'_verification',result)
    encoded=json.dumps(result).replace("'","''")
    sql(f"INSERT INTO test_bulk.results VALUES('{phase}','{encoded}'::jsonb)")
    print('PASS '+phase+': '+json.dumps(totals),flush=True)


def main():
    setup()
    batch('BULK_SNAPSHOT',snapshot=True)
    verify('snapshot')
    fixtures()
    events1=raw_load('events',1)
    leaves=raw_load('leaves',1)
    batch('BULK_BATCH1',events1,leaves)
    verify('batch1')
    events2=raw_load('events',2)
    batch('BULK_BATCH2',events2)
    verify('batch2')
    sql('INSERT INTO test_bulk.row_versions SELECT pegawai_id,tanggal,xmin::text FROM curated.cur_attendance_daily')
    replay=batch('BULK_NOOP',events1+events2,leaves)
    assert_true(all(replay[k]==0 for k in ('event_changes','leave_changes','attendance_daily_changes')),replay)
    assert_true(sql('''SELECT count(*) FROM test_bulk.row_versions v JOIN curated.cur_attendance_daily d
      USING(pegawai_id,tanggal) WHERE d.xmin::text<>v.version''')=='0','no-op daily versions unchanged')
    verify('noop')
    db(f"""UPDATE public.t_perizinan p SET approval=CASE WHEN c.scenario=4 THEN false ELSE p.approval END,
       tipe_ijin=CASE WHEN c.scenario=7 THEN 3 ELSE p.tipe_ijin END
       FROM {SCHEMA}.leaves f JOIN {SCHEMA}.cohort c ON c.emp=f.emp
       WHERE p.id=f.id AND c.scenario IN(4,7) AND p.alasan='{MARK}';""",source=True)
    changed=raw_load('leaves',3,correction=True)
    update=batch('BULK_CORRECTION',leaves=changed)
    assert_true(update['leave_changes']==400 and update['affected_employee_dates']==400,update)
    assert_true(sql('''SELECT count(*) FROM test_bulk.row_versions v JOIN curated.cur_attendance_daily d
      USING(pegawai_id,tanggal) JOIN test_bulk.cohort c ON c.emp=d.pegawai_id
      WHERE c.scenario NOT IN(4,7) AND d.xmin::text<>v.version''')=='0','unaffected 2000 daily rows unchanged')
    verify('correction',True)
    final=data('''SELECT json_build_object('events',(SELECT count(*) FROM curated.cur_event_attendance),
      'event_daily',(SELECT count(*) FROM curated.cur_attendance_event_daily),
      'leaves',(SELECT count(*) FROM curated.cur_leave_daily),
      'population',(SELECT count(*) FROM curated.cur_employee_population_daily),
      'daily',(SELECT count(*) FROM curated.cur_attendance_daily),
      'ready_batches',(SELECT count(*) FROM etl_control.curated_batch WHERE status='READY'),
      'review_events',(SELECT count(*) FROM curated.cur_event_attendance WHERE perlu_review),
      'review_leaves',(SELECT count(*) FROM curated.cur_leave_daily WHERE perlu_review))''')
    assert_true(final=={'events':2400,'event_daily':1400,'leaves':1600,'population':2400,'daily':2400,
                        'ready_batches':0,'review_events':0,'review_leaves':0},final)
    save('final',final|{'passed':True,'database':DB,'source_fixtures_retained':True,
                      'active_staging_raw_changed':False,'bulk_snapshot_status_mutation_tested':False})
    print('PASS bulk test: '+json.dumps(final),flush=True)


if __name__=='__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        if exc.stderr:print(exc.stderr.decode(),flush=True)
        raise
