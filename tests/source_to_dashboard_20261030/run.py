#!/usr/bin/env python3
"""Source-owned tagged transactions -> actual Hop raw/curated/mart -> dashboard."""
import argparse,importlib.util,json,os,subprocess,time,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
SC='epresensi-staging-postgres';MC='epresensi-mart-postgres';OC='epresensi-olap-postgres';HOP='epresensi-hop-web'
SOURCE='staging_bkd_mart_bulk_20261029';TARGET='mart_bkd_bulk_20261029';RESTORE='dbabsen_restore'
SCHEMA='test_source_dashboard_20261030';MARK='SOURCE_DASHBOARD_20261030';DAY='2026-10-30'
PROJECT='/usr/local/tomcat/webapps/ROOT/config/projects/epresensi-staging';RUNTIME=PROJECT+'/pipelines/validation/source_to_dashboard_20261030'
MEASURES=['active_employee_days','checkin_days','checkout_days','no_checkin_days','no_checkout_days','leave_days','required_checkin_days','required_checkout_days','excused_checkin_days','excused_checkout_days','required_checkin_present_days','required_checkout_present_days']
def command(args,data=None):
 p=subprocess.run(args,input=data,text=True,capture_output=True)
 if p.returncode:raise RuntimeError(p.stderr[-3000:])
 return p.stdout
def sql(q,where='stage',database=None):
 container,db={'stage':(SC,SOURCE),'mart':(MC,TARGET),'source':(OC,RESTORE)}[where]
 return command(['docker','exec','-i',container,'sh','-c','exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"','sql',database or db],q).strip()
def data(q,**kw):return json.loads(sql(q,**kw) or 'null')
def quote(v):return "'"+str(v).replace("'","''")+"'"
def save(name,v):(OUT/(name+'.json')).write_text(json.dumps(v,indent=2)+'\n')
def require(v,msg):
 if not v:raise AssertionError(msg)
def runtime(path,text):command(['docker','exec','-i',HOP,'sh','-c','umask 077;cat > "$1"','write',path],text)
def pipeline(tree,name):
 ET.indent(tree);txt=ET.tostring(tree.getroot() if hasattr(tree,'getroot') else tree,encoding='unicode',xml_declaration=True)
 (OUT/name).write_text(txt);runtime(RUNTIME+'/'+name,txt)
def hop(name):
 started=time.monotonic()
 p=subprocess.run(['docker','exec',HOP,'sh','-c','cd /usr/local/tomcat/webapps/ROOT && exec ./hop-run.sh -j epresensi-staging -e presensi-staging-local -r local -f "$1" -l BASIC','hop',RUNTIME+'/'+name],text=True,capture_output=True)
 (OUT/(name+'.log')).write_text(p.stdout+p.stderr);save(name+'_timing',{'seconds':time.monotonic()-started,'exit_code':p.returncode})
 require(p.returncode==0,'Hop failed: '+name);print('Hop completed',name,flush=True)
def guards():
 return {'active_stage':data("SELECT json_build_object('daily',(SELECT count(*) FROM curated.cur_attendance_daily),'outbox',(SELECT count(*) FROM etl_control.mart_outbox_batch),'bootstrap',(SELECT bootstrap_prepared FROM etl_control.mart_outbox_stream))",database='staging_bkd'),
 'active_mart':data("SELECT json_build_object('facts',(SELECT count(*) FROM mart_kehadiran.fact_kehadiran_daily),'batches',(SELECT count(*) FROM etl_control.mart_batch))",where='mart',database='mart_bkd'),
 'source_masters':data("SELECT json_build_object('employees',(SELECT md5(string_agg(md5(to_jsonb(p)::text),'' ORDER BY id)) FROM public.m_pegawai p),'shifts',(SELECT md5(string_agg(md5(to_jsonb(s)::text),'' ORDER BY id)) FROM public.m_shift s),'schedules',(SELECT md5(string_agg(md5(to_jsonb(j)::text),'' ORDER BY id)) FROM public.m_jadwal j))",where='source')}

def cleanup():
 require(sql("SELECT count(*) FROM mart_kehadiran.fact_kehadiran_daily",where='mart')=='82000','Expected prior 82000 test only')
 save('protected_before',guards())
 backups=ROOT/'backups/source_to_dashboard_20261030';backups.mkdir(parents=True,exist_ok=True)
 for container,db in [(SC,SOURCE),(MC,TARGET),(SC,'staging_bkd_bulk_20261028')]:
  path=backups/(db+'.dump')
  with path.open('xb') as f:
   os.chmod(path,0o600);subprocess.run(['docker','exec',container,'sh','-c','exec pg_dump -Fc -U "$POSTGRES_USER" -d "$1"','dump',db],stdout=f,check=True)
 # Only manifest-listed, exactly-tagged old synthetic transactions are deletable.
 counts=data("""SELECT json_build_object('events',(SELECT count(*) FROM public.t_checkinout s JOIN test_bulk_curated_20261028.events f USING(id) WHERE s.keterangan LIKE 'BULK_CURATED_20261028:%'),'leaves',(SELECT count(*) FROM public.t_perizinan s JOIN test_bulk_curated_20261028.leaves f USING(id) WHERE s.alasan='BULK_CURATED_20261028'))""",where='source')
 require(counts=={'events':2400,'leaves':1600},'Old fixture manifest/marker mismatch')
 manifest=data("SELECT json_build_object('events',(SELECT json_agg(id ORDER BY id) FROM test_bulk_curated_20261028.events),'leaves',(SELECT json_agg(id ORDER BY id) FROM test_bulk_curated_20261028.leaves))",where='source');save('deleted_source_manifest',manifest)
 deleted=data("""BEGIN;SET LOCAL lock_timeout='5s';
 WITH e AS(DELETE FROM public.t_checkinout s USING test_bulk_curated_20261028.events f WHERE s.id=f.id AND s.keterangan LIKE 'BULK_CURATED_20261028:%' RETURNING s.id),
 l AS(DELETE FROM public.t_perizinan s USING test_bulk_curated_20261028.leaves f WHERE s.id=f.id AND s.alasan='BULK_CURATED_20261028' RETURNING s.id)
 SELECT json_build_object('events',(SELECT count(*) FROM e),'leaves',(SELECT count(*) FROM l));
 DROP SCHEMA test_bulk_curated_20261028 CASCADE;COMMIT;""",where='source')
 require(deleted==counts,'Delete count mismatch')
 # These three databases hold the previous bulk test and its 82000-row expansion.
 for where,db in [('stage',SOURCE),('mart',TARGET),('stage','staging_bkd_bulk_20261028')]:
  sql('DROP DATABASE '+db+' WITH (FORCE)',where=where,database='postgres')
 for where,db in [('stage',SOURCE),('mart',TARGET)]:sql('CREATE DATABASE '+db,where=where,database='postgres')
 save('cleanup',{'deleted_source_rows':deleted,'deleted_test_databases':[SOURCE,TARGET,'staging_bkd_bulk_20261028'],'new_empty_databases':[SOURCE,TARGET],'backups':str(backups)})
 print('Previous bulk source fixtures and downstream records removed',flush=True)

def setup():
 require(sql("SELECT (current_timestamp AT TIME ZONE 'Asia/Jakarta')::date",where='source')==DAY,'Snapshot must use today')
 require(sql("SELECT count(*) FROM information_schema.schemata WHERE schema_name='raw'")=='0','Target must be empty')
 sql(f"""BEGIN;CREATE SCHEMA {SCHEMA};
 CREATE TABLE {SCHEMA}.cohort AS
 WITH schedules AS(SELECT s.departemen_id,array_agg(j.id ORDER BY j.jam_masuk,s.id,j.id) ids
 FROM public.m_shift s JOIN public.m_jadwal j ON j.jenis=s.id
 WHERE s.status=true AND j.hari=trim(to_char(DATE '{DAY}','Dy')) AND j.jam_keluar>j.jam_masuk
 GROUP BY s.departemen_id),users AS(SELECT pegawai_id,min(id) uid FROM public.m_user GROUP BY pegawai_id),
 eligible AS(SELECT p.id emp,p.departemen dep,u.uid,j.ids,row_number() OVER(PARTITION BY p.departemen ORDER BY p.id) dep_rank
 FROM public.m_pegawai p JOIN schedules j ON j.departemen_id=p.departemen JOIN users u ON u.pegawai_id=p.id WHERE p.status IN(1,2,3,4)),
 chosen AS(SELECT * FROM eligible ORDER BY dep_rank,dep,emp LIMIT 82000)
 SELECT row_number() OVER(ORDER BY dep_rank,dep,emp)::int n,emp,dep,uid,ids[1] j1,ids[2] j2 FROM chosen;
 ALTER TABLE {SCHEMA}.cohort ADD PRIMARY KEY(emp);
 CREATE UNIQUE INDEX ON {SCHEMA}.cohort(n);
 CREATE TABLE {SCHEMA}.events(id integer PRIMARY KEY,emp integer);
 CREATE TABLE {SCHEMA}.leaves(id integer PRIMARY KEY,emp integer);
 COMMIT;""",where='source')
 cohort=data(f"SELECT json_agg(c ORDER BY n) FROM {SCHEMA}.cohort c",where='source');require(0<len(cohort)<=82000,'Invalid cohort')
 save('cohort_summary',{'employees':len(cohort),'departments':len({r['dep'] for r in cohort}),'with_second_schedule':sum(r['j2'] is not None for r in cohort),'date':DAY,'basis':'Real active source employees with user and same-day Friday department schedule; subset population'})
 ddl=command(['docker','exec',SC,'sh','-c','exec pg_dump -U "$POSTGRES_USER" -d staging_bkd --schema-only --schema=raw --schema=curated --no-owner --no-privileges'])
 sql(ddl+'\nCREATE SCHEMA etl_control;')
 spec=importlib.util.spec_from_file_location('installer',ROOT/'hop/scripts/install_curated_etl.py');ins=importlib.util.module_from_spec(spec);spec.loader.exec_module(ins);sql(ins.installation_sql())
 sql((ROOT/'sql/staging/20261028_mart_outbox.sql').read_text())
 sql((ROOT/'sql/mart/20261028_attendance_daily.sql').read_text(),where='mart');sql((ROOT/'sql/mart/20261028_mart_incremental_etl.sql').read_text(),where='mart')
 sql('CREATE SCHEMA test_source;CREATE TABLE test_source.cohort(n integer,emp integer PRIMARY KEY,dep integer,uid integer,j1 integer,j2 integer);INSERT INTO test_source.cohort SELECT * FROM json_populate_recordset(NULL::test_source.cohort,'+quote(json.dumps(cohort))+'::json);')
 command(['docker','exec',HOP,'mkdir','-p',RUNTIME])
 for old,alias,db in [('presensi_source','source_e2e_restore',RESTORE),('presensi_staging','source_e2e_stage',SOURCE),('presensi_mart','source_e2e_mart',TARGET)]:
  meta=json.loads(command(['docker','exec',HOP,'cat',PROJECT+'/metadata/rdbms/'+old+'.json']));meta['name']=alias;meta['rdbms']['POSTGRESQL']['databaseName']=db;runtime(PROJECT+'/metadata/rdbms/'+alias+'.json',json.dumps(meta))
 tree=ET.parse(ROOT/'hop/pipelines/curated/curated_incremental_batch.hpl');tree.find('./transform/connection').text='source_e2e_stage';pipeline(tree,'curated.hpl')
 for p in (ROOT/'hop/pipelines/mart').glob('*.hpl'):
  tree=ET.parse(p)
  for c in tree.findall('./transform/connection'):c.text={'presensi_staging':'source_e2e_stage','presensi_mart':'source_e2e_mart'}[c.text]
  pipeline(tree,p.name)
 tree=ET.parse(ROOT/'hop/workflows/mart/curated_to_serving.hwf')
 for f in tree.findall('./actions/action/filename'):f.text=RUNTIME+'/'+Path(f.text).name
 pipeline(tree,'mart.hwf');print('Setup complete',len(cohort),'real source employees',flush=True)

def fixtures():
 require(sql(f'SELECT count(*) FROM {SCHEMA}.events',where='source')=='0','Fixtures already exist')
 started=time.monotonic()
 # 88% both, 3% in-only, 1% out-only, 1% absent, 3% full leave,
 # 2% exempt-in with checkout, 2% exempt-out with checkin. Every 20th
 # both-event employee uses a second actual schedule when available.
 sql(f"""BEGIN;SET LOCAL statement_timeout='600s';
 WITH definitions AS(
 SELECT c.*,j1 jid,1 typ FROM {SCHEMA}.cohort c WHERE (n-1)%100<91 OR (n-1)%100>=98
 UNION ALL SELECT c.*,j1,2 FROM {SCHEMA}.cohort c WHERE (n-1)%100<88 OR (n-1)%100=91 OR (n-1)%100 IN(96,97)
 UNION ALL SELECT c.*,j2,1 FROM {SCHEMA}.cohort c WHERE (n-1)%100<88 AND n%20=0 AND j2 IS NOT NULL
 UNION ALL SELECT c.*,j2,2 FROM {SCHEMA}.cohort c WHERE (n-1)%100<88 AND n%20=0 AND j2 IS NOT NULL),ins AS(
 INSERT INTO public.t_checkinout(pegawai_id,departemen,checktype,created_at,updated_at,work_code,jadwal_id,hari,jam_masuk,jam_keluar,is_manual,is_wfh,keterangan)
 SELECT d.emp,d.dep,d.typ,DATE '{DAY}'+CASE WHEN typ=1 THEN j.jam_masuk ELSE j.jam_keluar END,current_timestamp AT TIME ZONE 'Asia/Jakarta',j.jenis,j.id,j.hari,j.jam_masuk,j.jam_keluar,false,0,'{MARK}'
 FROM definitions d JOIN public.m_jadwal j ON j.id=d.jid RETURNING id,pegawai_id)
 INSERT INTO {SCHEMA}.events SELECT id,pegawai_id FROM ins;
 WITH ins AS(
 INSERT INTO public.t_perizinan(user_id,nama,departemen,tipe_ijin,jenis_ijin,alasan,catatan,approval,approval_at,created_at,tgl_ijin,tgl_ijin_sampai,pegawai_id,updated_at)
 SELECT uid,'SOURCE PIPELINE TEST',dep,CASE WHEN (n-1)%100<96 THEN 1 WHEN (n-1)%100<98 THEN 2 ELSE 3 END,1,'{MARK}','{MARK}',true,current_timestamp AT TIME ZONE 'Asia/Jakarta',current_timestamp AT TIME ZONE 'Asia/Jakarta',DATE '{DAY}',DATE '{DAY}',emp,current_timestamp AT TIME ZONE 'Asia/Jakarta'
 FROM {SCHEMA}.cohort WHERE (n-1)%100>=93 RETURNING id,pegawai_id)
 INSERT INTO {SCHEMA}.leaves SELECT id,pegawai_id FROM ins;COMMIT;""",where='source')
 save('fixtures',{'seconds':time.monotonic()-started,**data(f"SELECT json_build_object('employees',(SELECT count(*) FROM {SCHEMA}.cohort),'events',(SELECT count(*) FROM {SCHEMA}.events),'leaves',(SELECT count(*) FROM {SCHEMA}.leaves),'event_min',(SELECT min(id) FROM {SCHEMA}.events),'event_max',(SELECT max(id) FROM {SCHEMA}.events))",where='source')});print('Tagged source fixtures created',flush=True)

TABLES={'pegawai':f'public.m_pegawai src JOIN {SCHEMA}.cohort c ON c.emp=src.id','departemen':f'public.m_departemen src WHERE src.id IN(SELECT dep FROM {SCHEMA}.cohort)','jadwal':f'public.m_jadwal src WHERE src.id IN(SELECT j1 FROM {SCHEMA}.cohort UNION SELECT j2 FROM {SCHEMA}.cohort)','shift':f'public.m_shift src WHERE src.id IN(SELECT jenis FROM public.m_jadwal WHERE id IN(SELECT j1 FROM {SCHEMA}.cohort UNION SELECT j2 FROM {SCHEMA}.cohort))','user':f'public.m_user src JOIN {SCHEMA}.cohort c ON c.uid=src.id','jenis_ijin':'public.m_jenis_ijin src WHERE src.id=1','tipe_ijin':'public.m_tipe_ijin src WHERE src.id IN(SELECT tipe_id FROM public.m_jenis_ijin WHERE id=1)','checkinout':f'public.t_checkinout src JOIN {SCHEMA}.events f ON f.id=src.id','perizinan':f'public.t_perizinan src JOIN {SCHEMA}.leaves f ON f.id=src.id'}
def raw():
 require((OUT/'fixtures.json').exists(),'Fixture creation did not complete')
 require(int(sql(f'SELECT count(*) FROM {SCHEMA}.events',where='source'))>0,'No committed source fixtures')
 for name,fromsql in TABLES.items():
  already_loaded=int(sql(f'SELECT count(*) FROM raw.raw_{name}'))>0
  projection='src.id,src.pegawai_id' if name=='user' else 'src.*'
  tree=ET.ElementTree(ET.fromstring(command(['docker','exec',HOP,'cat',PROJECT+'/pipelines/raw/raw_'+name+'.hpl'])))
  rd,wr=tree.findall('./transform');rd.find('connection').text='source_e2e_restore';rd.find('sql').text=f"SELECT {projection},CURRENT_TIMESTAMP AS extracted_at,'{MARK}'::text AS pipeline_run_id FROM {fromsql}";wr.find('connection').text='source_e2e_stage';wr.find('truncate').text='N'
  tree.find('./info/name').text='source_raw_'+name;filename='raw_'+name+'.hpl';pipeline(tree,filename)
  if not already_loaded:hop(filename)
  expression="jsonb_build_object('id',src.id,'pegawai_id',src.pegawai_id)" if name=='user' else 'to_jsonb(src)'
  a=data(f"SELECT json_build_object('rows',count(*),'hash',md5(string_agg(md5({expression}::text),'' ORDER BY src.id))) FROM {fromsql}",where='source')
  expression="jsonb_build_object('id',r.id,'pegawai_id',r.pegawai_id)" if name=='user' else "to_jsonb(r)-'extracted_at'-'pipeline_run_id'"
  b=data(f"SELECT json_build_object('rows',count(*),'hash',md5(string_agg(md5(({expression})::text),'' ORDER BY id))) FROM raw.raw_{name} r")
  require(a==b,'Source/raw mismatch '+name);save('raw_'+name+'_verification',{'passed':True,**a,'projection':'id and pegawai_id only; credentials not copied' if name=='user' else 'all business fields'})

def curated():
 if sql('SELECT count(*) FROM etl_control.curated_batch')=='0':
  batch_id=sql(f"SELECT etl_control.enqueue_curated_batch('{MARK}',p_event_ids=>(SELECT array_agg(id ORDER BY id) FROM raw.raw_checkinout),p_leave_ids=>(SELECT array_agg(id ORDER BY id) FROM raw.raw_perizinan),p_snapshot_date=>DATE '{DAY}',p_snapshot_complete=>true)")
 else:batch_id=sql(f"SELECT batch_id FROM etl_control.curated_batch WHERE batch_id='{MARK}' AND status='READY'")
 require(batch_id==MARK,'Unexpected manifest state')
 save('manifest',{'batch_id':batch_id})
 hop('curated.hpl');record=data(f"SELECT to_jsonb(b) FROM etl_control.curated_batch b WHERE batch_id='{MARK}'");save('curated_result',record);require(record['status']=='APPLIED','Curated not applied')

def mart():
 require(sql('SELECT bootstrap_prepared FROM etl_control.mart_outbox_stream')=='f','Bootstrap already prepared')
 save('bootstrap',data('SELECT etl_control.prepare_mart_bootstrap()'));hop('mart.hwf')
 require(sql('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL')=='0','Pending delivery')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['cleanup','setup','fixtures','raw','curated','mart']);a=p.parse_args();globals()[a.phase]()
