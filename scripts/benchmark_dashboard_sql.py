"""Replay captured chart contexts as query-only requests, then EXPLAIN ANALYZE.

No persistent data/schema changes: optional mart comparison uses a session temp
 table rolled back at exit. Run after the browser benchmark to avoid contention.
"""
import argparse
import http.cookiejar
import json
from pathlib import Path
import time
import urllib.request
from dotenv import dotenv_values
from etl.connectors.olap import get_olap_connection


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',default='/tmp/olap-dashboard-benchmark.json')
    parser.add_argument('--output',default='/tmp/olap-dashboard-sql.json')
    args=parser.parse_args()
    captured=json.loads(Path(args.input).read_text())
    cfg=dotenv_values('.env.dashboard')
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    token=None
    csrf=None
    def api(path,body=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        if csrf:headers['X-CSRFToken']=csrf
        with opener.open(urllib.request.Request('http://127.0.0.1:8090'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=60) as response:
            return json.load(response)
    token=api('/api/v1/security/login',{'username':cfg['SUPERSET_ADMIN_USERNAME'],'password':cfg['SUPERSET_ADMIN_PASSWORD'],'provider':'db','refresh':False})['access_token']
    csrf=api('/api/v1/security/csrf_token/')['result']
    contexts=[]
    for run in captured['results']:
        if run['run']!=1:continue
        for request in run['records']:
            if request.get('payload') and '/chart/data' in request['path']:
                chart_id=request['payload'].get('form_data',{}).get('slice_id')
                representative = (
                    (run['key']=='overview' and request['phase']=='initial' and chart_id in (None,1,5,7))
                    or (run['key']=='overview' and request['phase']=='filter' and chart_id==1)
                    or (run['key'] in ('departments','lateness') and request['phase']=='initial' and chart_id is not None)
                )
                if not representative:continue
                body={**request['payload'],'result_type':'query','result_format':'json'}
                result=api('/api/v1/chart/data',body)
                for item in result.get('result',[]):
                    if item.get('query'):
                        contexts.append({'dashboard':run['key'],'chartId':chart_id,'phase':request['phase'],'query':item['query'],'httpMs':request.get('durationMs')})
    Path(args.output).write_text(json.dumps({'queries':contexts},indent=2))
    print('Captured SQL contexts',len(contexts),flush=True)
    with get_olap_connection() as conn:
        conn.execute("SET LOCAL statement_timeout='60s'")
        conn.execute("SET LOCAL lock_timeout='3s'")
        start=time.perf_counter()
        conn.execute('CREATE TEMP TABLE benchmark_department_mart ON COMMIT DROP AS SELECT * FROM analytics.attendance_department_daily')
        build_ms=(time.perf_counter()-start)*1000
        conn.execute('ANALYZE benchmark_department_mart')
        mart_rows=conn.execute('SELECT count(*) FROM benchmark_department_mart').fetchone()[0]
        for index,item in enumerate(contexts):
            query=item['query'].strip().rstrip(';')
            if not query.upper().startswith('SELECT '):raise ValueError('Only SELECT query contexts are allowed')
            measurements=[]
            for _ in range(3):
                plan=conn.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+query).fetchone()[0][0]
                measurements.append({'executionMs':plan['Execution Time'],'planningMs':plan['Planning Time'],'plan':plan['Plan']})
            item['view']=measurements
            if 'analytics.attendance_department_daily' in query:
                mart_query=query.replace('analytics.attendance_department_daily','pg_temp.benchmark_department_mart')
                baseline=conn.execute(query).fetchall()
                precomputed=conn.execute(mart_query).fetchall()
                item['equivalent']=sorted(map(repr,baseline))==sorted(map(repr,precomputed))
                if not item['equivalent']:raise ValueError('Mart result differs from original query')
                item['tempMart']=[]
                for _ in range(3):
                    plan=conn.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+mart_query).fetchone()[0][0]
                    item['tempMart'].append({'executionMs':plan['Execution Time'],'planningMs':plan['Planning Time'],'plan':plan['Plan']})
            Path(args.output).write_text(json.dumps({'martBuildMs':build_ms,'martRows':mart_rows,'queries':contexts},indent=2))
            print(index+1,item['dashboard'],item['phase'],'view ms',[x['executionMs'] for x in measurements],'mart ms',[x['executionMs'] for x in item.get('tempMart',[])],flush=True)
        conn.rollback()

if __name__=='__main__':main()
