"""Bounded HTTP benchmark using actual website tokens and existing nine-chart dashboards."""
import concurrent.futures,importlib.util,json,math,time,threading
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
import run as r
from types import SimpleNamespace
t=SimpleNamespace(MEASURES=r.MEASURES,save=r.save,data=lambda q,target=False:r.data(q,where='mart' if target else 'stage'))
env=dict(l.split('=',1) for l in (ROOT/'.env.hybrid').read_text().splitlines() if l and not l.startswith('#'))
APP='http://localhost:3100';BI='http://localhost:3101';METRICS=t.MEASURES[:6]
def stats(values):
    v=sorted(values)
    return {'count':len(v),'p50':v[math.ceil(len(v)*.5)-1],'p95':v[math.ceil(len(v)*.95)-1],'max':max(v)} if v else {}
def run(start_date,end_date,label,levels=(1,5,10)):
    references={}
    for role in ['director','manager']:
        clause=' AND departemen_id_sumber=30114' if role=='manager' else ''
        references[role]=t.data("SELECT jsonb_build_array("+','.join(f'SUM({x})' for x in METRICS)+f") FROM serving.v_kehadiran_departemen_harian WHERE tanggal BETWEEN '{start_date}' AND '{end_date}'"+clause,target=True)
    department_count=t.data(f"SELECT count(DISTINCT departemen_id_sumber) FROM serving.v_kehadiran_departemen_harian WHERE tanggal BETWEEN '{start_date}' AND '{end_date}'",target=True)
    params={'start_date':start_date,'end_date':end_date}
    output={'label':label,'period':params,'references':references,'stages':[]}
    def visit(index):
        role='director' if index%2==0 else 'manager';dashboard=2 if role=='director' else 1
        app=requests.Session();started=time.monotonic();errors=[];records=[]
        try:
            r=app.post(APP+'/api/auth/login',headers={'Origin':APP},json={'username':role,'password':env['DEMO_'+role.upper()+'_PASSWORD']},timeout=30);r.raise_for_status()
            r=app.post(APP+'/api/metabase-token',headers={'Origin':APP},json={'entityType':'dashboard','entityId':dashboard},timeout=30);r.raise_for_status();token=r.json()['jwt']
            r=requests.get(BI+'/api/embed/dashboard/'+token,timeout=45);r.raise_for_status()
            cards=sorted([c for c in r.json()['dashcards'] if c.get('card_id')],key=lambda c:(c['row'],c['col']))
            def chart(c):
                begin=time.monotonic()
                r=requests.get(BI+f"/api/embed/dashboard/{token}/dashcard/{c['id']}/card/{c['card_id']}",params={'parameters':json.dumps(params)},timeout=45)
                body=r.json();rows=body.get('data',{}).get('rows',[])
                rec={'card_id':c['card_id'],'seconds':time.monotonic()-begin,'http_status':r.status_code,'status':body.get('status'),'cached':body.get('cached'),'rows':len(rows)}
                if c['card']['display']=='scalar':rec['value']=rows[0][0] if rows else None
                if role=='director' and 'Department summary' in c['card']['name']:rec['departments_complete']=len(rows)==department_count
                if role=='manager' and 'Employee daily records' in c['card']['name']:rec['scope_ok']=all(x[2]==30114 for x in rows) and len(rows)<=1000
                return rec
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:records=list(pool.map(chart,cards))
            if len(cards)!=9:errors.append('wrong_chart_count')
            if any(c['status']!='completed' or not 200<=c['http_status']<300 for c in records):errors.append('chart_failure')
            if [c['value'] for c in records if 'value' in c]!=references[role]:errors.append('kpi_mismatch')
            if any(c.get('scope_ok') is False for c in records):errors.append('department_scope_mismatch')
            if any(c.get('departments_complete') is False for c in records):errors.append('department_table_truncated')
        except Exception as e:errors.append(type(e).__name__)
        finally:
            try:app.post(APP+'/api/auth/logout',headers={'Origin':APP},timeout=15)
            except Exception:pass
            app.close()
        return {'role':role,'seconds':time.monotonic()-started,'errors':errors,'cards':records}
    for concurrency in levels:
        records=[];begin=time.monotonic()
        # Four waves, equal role distribution overall; no artificial think time.
        for wave in range(4):
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:records.extend(pool.map(visit,range(wave*concurrency,(wave+1)*concurrency)))
        elapsed=time.monotonic()-begin
        stage={'users':concurrency,'chart_fanout_per_user':3,'elapsed_seconds':elapsed,'visits_per_second':len(records)/elapsed,'dashboard_seconds':stats([x['seconds'] for x in records]),'chart_seconds':stats([c['seconds'] for x in records for c in x['cards']]),'errors':sum(bool(x['errors']) for x in records),'cached_chart_responses':sum(c.get('cached') is True for x in records for c in x['cards']),'visits':records}
        output['stages'].append(stage);t.save(label+'_http',output)
        print(label,concurrency,'users',stage['dashboard_seconds'],'errors',stage['errors'],flush=True)
        if stage['errors'] or stage['dashboard_seconds']['p95']>15:break
    return output
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--start',default='2026-10-30');p.add_argument('--end',default='2026-10-30');p.add_argument('--label',default='source_daily');p.add_argument('--users',default='1,5,10');a=p.parse_args();run(a.start,a.end,a.label,tuple(map(int,a.users.split(','))))
