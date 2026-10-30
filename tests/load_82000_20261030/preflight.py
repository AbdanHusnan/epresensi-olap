"""Read-only inventory; writes only local evidence. No bootstrap or load."""
import importlib.util,json,time,concurrent.futures,statistics
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('harness',ROOT/'tests/mart_small_20261029/run.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
env=dict(l.split('=',1) for l in (ROOT/'.env.hybrid').read_text().splitlines() if l and not l.startswith('#'))
result={'configured_dashboard_database':env.get('MART_DATABASE'),'protected':t.guards()}
result['mart']=t.data("""SELECT jsonb_build_object('database',current_database(),'facts',count(*),'employees',count(DISTINCT pegawai_id_sumber),'first_date',min(tanggal),'last_date',max(tanggal),'departments',count(DISTINCT departemen_id_sumber),'bytes',pg_database_size(current_database())) FROM mart_kehadiran.fact_kehadiran_daily""",target=True,database='mart_bkd_bulk_20261029')
result['curated']=t.data("""SELECT jsonb_build_object('database',current_database(),'rows',count(*),'employees',count(DISTINCT pegawai_id),'first_date',min(tanggal),'last_date',max(tanggal)) FROM curated.cur_attendance_daily""",database='staging_bkd_mart_bulk_20261029')
s=requests.Session(); base='http://127.0.0.1:3101'
r=s.post(base+'/api/session',json={'username':env['BI_ADMIN_EMAIL'],'password':env['BI_ADMIN_PASSWORD']},timeout=30);r.raise_for_status();s.headers['X-Metabase-Session']=r.json()['id']
r=s.get(base+'/api/database',timeout=30);r.raise_for_status()
result['metabase_sources']=[{'id':d['id'],'name':d['name'],'database':d.get('details',{}).get('dbname')} for d in r.json()['data']]
result['sql_baseline']={}
for name,sql in [('institution',"SELECT * FROM serving.v_kehadiran_instansi_harian WHERE tanggal='2026-10-28'"),('departments',"SELECT * FROM serving.v_kehadiran_departemen_harian WHERE tanggal='2026-10-28' ORDER BY checkin_days DESC"),('employee_detail',"SELECT * FROM mart_kehadiran.fact_kehadiran_daily WHERE tanggal='2026-10-28' AND departemen_id_sumber=30114 ORDER BY tanggal,pegawai_id_sumber LIMIT 1000")]:
    runs=[t.data('BEGIN READ ONLY; SET LOCAL statement_timeout=30000; EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+sql+'; COMMIT;',target=True,database='mart_bkd_bulk_20261029')[0] for _ in range(5)]
    result['sql_baseline'][name]={'execution_ms':[x['Execution Time'] for x in runs],'last_plan':runs[-1]}
# Baseline end-to-end HTTP chart requests using actual application-issued guest tokens.
result['dashboard_baseline']=[]
for role,dashboard in [('director',2),('manager',1)]:
    app=requests.Session(); origin='http://localhost:3100'
    r=app.post(origin+'/api/auth/login',headers={'Origin':origin},json={'username':role,'password':env['DEMO_'+role.upper()+'_PASSWORD']},timeout=30);r.raise_for_status()
    r=app.post(origin+'/api/metabase-token',headers={'Origin':origin},json={'entityType':'dashboard','entityId':dashboard},timeout=30);r.raise_for_status();token=r.json()['jwt']
    r=requests.get(base+'/api/embed/dashboard/'+token,timeout=30);r.raise_for_status();cards=[c for c in r.json()['dashcards'] if c.get('card_id')]
    samples=[]
    def query(c):
        start=time.monotonic()
        r=requests.get(base+f"/api/embed/dashboard/{token}/dashcard/{c['id']}/card/{c['card_id']}",params={'parameters':json.dumps({'start_date':'2026-10-28','end_date':'2026-10-28'})},timeout=45)
        body=r.json();return {'card_id':c['card_id'],'http_status':r.status_code,'status':body.get('status'),'seconds':time.monotonic()-start,'cached':body.get('cached'),'row_count':len(body.get('data',{}).get('rows',[]))}
    for repeat in range(3):
        start=time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool: records=list(pool.map(query,cards))
        samples.append({'seconds':time.monotonic()-start,'cards':records})
    result['dashboard_baseline'].append({'role':role,'chart_concurrency':3,'runs':samples})
    app.post(origin+'/api/auth/logout',headers={'Origin':origin},timeout=30)
s.delete(base+'/api/session',timeout=30)
result['protected_unchanged']=result['protected']==t.guards()
(OUT/'preflight.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['sql_baseline','dashboard_baseline','protected']},indent=2))
for k,v in result['sql_baseline'].items():print(k,'SQL ms',v['execution_ms'])
for d in result['dashboard_baseline']:print(d['role'],'nine-chart HTTP seconds',[round(x['seconds'],3) for x in d['runs']], 'failures',sum(c['status']!='completed' for x in d['runs'] for c in x['cards']))
