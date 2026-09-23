"""Stage, validate, and switch this instance's four dashboards to physical marts.

Existing datasets/views are retained. Snapshot enables --rollback after a cutover.
"""
import argparse
from copy import deepcopy
from collections import Counter
import json
from pathlib import Path
from etl.connectors.olap import get_olap_connection
from scripts.superset_api import SupersetAPI

BACKUP=Path('backups/superset-before-marts.json')
COMPOSITION={6,7,12,13}
LATENESS={20}


def replacement_context(context, dataset_id):
    value=deepcopy(context)
    value['datasource']={'id':dataset_id,'type':'table'}
    if isinstance(value.get('form_data'),dict):
        value['form_data']['datasource']=f'{dataset_id}__table'
    return value


def restore(api, backup):
    for key,value in backup['charts'].items():api.request(f'/api/v1/chart/{key}',value,'PUT')
    for key,value in backup['dashboards'].items():api.request(f'/api/v1/dashboard/{key}',value,'PUT')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--rollback',action='store_true')
    parser.add_argument('--benchmark-input',default='deploy/superset/mart-migration-contexts.json')
    args=parser.parse_args()
    if not args.apply and not args.rollback:
        print('Preview: stage four datasets, compare captured chart queries, then update chart and native-filter references. Use --apply or --rollback.');return
    api=SupersetAPI()
    if args.rollback:
        restore(api,json.loads(BACKUP.read_text()));print('Restored pre-mart chart/filter definitions; marts retained.');return
    dashboards={i:api.request(f'/api/v1/dashboard/{i}')['result'] for i in range(1,5)}
    chart_ids=set()
    for i in dashboards:
        chart_ids.update(x['id'] for x in api.request(f'/api/v1/dashboard/{i}/charts')['result'])
    charts={i:api.request(f'/api/v1/chart/{i}')['result'] for i in chart_ids}
    backup={'charts':{i:{k:c.get(k) for k in ('datasource_id','datasource_type','params','query_context','cache_timeout')} for i,c in charts.items()},
            'dashboards':{i:{'json_metadata':d['json_metadata']} for i,d in dashboards.items()}}
    if not BACKUP.exists():
        BACKUP.parent.mkdir(exist_ok=True);BACKUP.write_text(json.dumps(backup,indent=2))
    old=api.request('/api/v1/dataset/2')['result']
    existing=api.request('/api/v1/dataset/?q=(page_size:100)')['result']
    names={'department':'mart_attendance_department_daily','composition':'mart_attendance_composition_daily','lateness':'mart_attendance_lateness_daily','filter':'dashboard_departments'}
    ids={}
    for kind,name in names.items():
        found=next((d for d in existing if d['table_name']==name and d.get('schema')=='analytics' and d['database']['id']==old['database']['id']),None)
        did=found['id'] if found else api.request('/api/v1/dataset/',{'database':old['database']['id'],'schema':'analytics','table_name':name})['id']
        details=api.request(f'/api/v1/dataset/{did}')['result']
        metrics=[]
        if kind=='department':
            metrics=[{k:m[k] for k in ('metric_name','expression','verbose_name','d3format','metric_type') if m.get(k) is not None} for m in old['metrics']]
        elif kind in ('composition','lateness'):
            metrics=[{'metric_name':'count','expression':'SUM(employee_days)' if kind=='composition' else 'SUM(late_days)','verbose_name':'Pegawai-hari','metric_type':'sum'}]
        # Reuse IDs when refreshing existing metrics; do not duplicate saved names.
        metric_ids={m['metric_name']:m['id'] for m in details['metrics']}
        for metric in metrics:
            if metric['metric_name'] in metric_ids:metric['id']=metric_ids[metric['metric_name']]
        body={'cache_timeout':-1,'description':'Pre-aggregated OLAP mart. Atomically refreshed with ETL; targets unset. Chart cache bypassed to read the latest committed generation.'}
        if kind!='filter':body.update(main_dttm_col='tanggal',metrics=metrics)
        api.request(f'/api/v1/dataset/{did}',body,'PUT');ids[kind]=did
    def destination(cid):
        return ids['composition'] if cid in COMPOSITION else ids['lateness'] if cid in LATENESS else ids['department']

    captured=json.loads(Path(args.benchmark_input).read_text())
    validations=[]
    with get_olap_connection() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute("SET LOCAL statement_timeout='60s'")
        for run in captured['results']:
            if run['run']!=1:continue
            for request in run['records']:
                context=request.get('payload')
                if not context:continue
                cid=context.get('form_data',{}).get('slice_id')
                proposed=replacement_context(context,destination(cid) if cid is not None else ids['filter'])
                before=api.request('/api/v1/chart/data',{**context,'result_type':'query','result_format':'json'})['result']
                after=api.request('/api/v1/chart/data',{**proposed,'result_type':'query','result_format':'json'})['result']
                if len(before)!=len(after):raise ValueError('Query count differs')
                for a,b in zip(before,after):
                    qa,qb=a['query'],b['query']
                    if not qa.lstrip().upper().startswith('SELECT ') or not qb.lstrip().upper().startswith('SELECT '):raise ValueError('Expected SELECT query')
                    left=conn.execute(qa).fetchall();right=conn.execute(qb).fetchall()
                    if Counter(left)!=Counter(right):
                        raise ValueError(f'Chart {cid} {run["key"]}/{request["phase"]} differs')
                    validations.append({'dashboard':run['key'],'chart_id':cid,'phase':request['phase'],'rows':len(left),'equal':True})
                print('Validated',run['key'],cid,request['phase'],flush=True)
    Path('docs/dashboard-mart-validation.json').write_text(json.dumps({'datasets':ids,'queries':validations},indent=2))
    # API does not support atomic multi-chart writes: restore snapshots if any write fails.
    try:
        for cid,chart in charts.items():
            did=destination(cid);params=json.loads(chart['params']);params['datasource']=f'{did}__table'
            body={'datasource_id':did,'datasource_type':'table','params':json.dumps(params),'cache_timeout':-1}
            if chart.get('query_context'):
                body['query_context']=json.dumps(replacement_context(json.loads(chart['query_context']),did))
            api.request(f'/api/v1/chart/{cid}',body,'PUT')
        for did,dashboard in dashboards.items():
            metadata=json.loads(dashboard['json_metadata'])
            for f in metadata.get('native_filter_configuration',[]):
                for target in f.get('targets',[]):
                    if target.get('column',{}).get('name')=='nama_departemen':target['datasetId']=ids['filter']
                    elif target.get('datasetId') in (1,2):target['datasetId']=ids['department']
            api.request(f'/api/v1/dashboard/{did}',{'json_metadata':json.dumps(metadata)},'PUT')
        for cid in charts:
            saved=api.request(f'/api/v1/chart/{cid}')['result']
            # This Superset version serializes chart cache_timeout as a string.
            if int(saved['datasource_id'])!=destination(cid) or int(saved['cache_timeout'])!=-1:
                raise RuntimeError(f'Chart {cid} cutover verification failed')
    except BaseException:
        restore(api,backup)
        raise
    print(json.dumps({'datasets':ids,'charts_switched':len(charts),'validated_queries':len(validations)}))

if __name__=='__main__':main()
