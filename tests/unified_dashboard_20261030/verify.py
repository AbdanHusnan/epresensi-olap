"""Read-only checks for daily/period separation and name-based department lookup."""
import base64
import json
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
ENV=dict(l.split('=',1) for l in (ROOT/'.env.hybrid').read_text().splitlines() if l and not l.startswith('#'))
RUNS=json.loads((ROOT/'hybrid-dashboard/lib/test-runs.json').read_text())
APP='http://localhost:3100';BI='http://localhost:3101';HEAD={'Origin':APP}


def checked(response):
    assert response.ok,'HTTP '+str(response.status_code)
    return response.json()


def token(session,run,role,section,**filters):
    body={'entityType':'dashboard','entityId':run[role][section],'run':run['key'],'section':section,**filters}
    jwt=checked(session.post(APP+'/api/metabase-token',headers=HEAD,json=body,timeout=30))['jwt']
    claims=json.loads(base64.urlsafe_b64decode(jwt.split('.')[1]+'==='))
    start=filters.get('startDate',run['startDate']);end=filters.get('endDate',run['endDate'] if section=='period' else start)
    assert claims['params']['start_date']==start and claims['params']['end_date']==end
    if role=='manager':assert claims['params']['department']==int(ENV['DEMO_MANAGER_DEPARTMENT_ID'])
    return jwt


def charts(jwt):
    meta=checked(requests.get(BI+'/api/embed/dashboard/'+jwt,timeout=60));out=[]
    for dc in sorted(meta['dashcards'],key=lambda c:(c['row'],c['col'])):
        if not dc.get('card_id'):continue
        result=checked(requests.get(BI+f"/api/embed/dashboard/{jwt}/dashcard/{dc['id']}/card/{dc['card_id']}",timeout=120))
        assert result.get('status')=='completed',dc['card']['name']
        out.append((dc,result['data']['rows']))
    return out


results=[]
assert requests.get(APP+'/api/departments',params={'run':RUNS[0]['key']},timeout=30).status_code==401
for role in ('director','manager'):
    s=requests.Session();checked(s.post(APP+'/api/auth/login',headers=HEAD,json={'username':role,'password':ENV['DEMO_'+role.upper()+'_PASSWORD']},timeout=30))
    for run in RUNS:
        daily=charts(token(s,run,role,'overview'))
        assert not any('Daily attendance trend' in dc['card']['name'] for dc,_ in daily)
        totals=[rows[0][0] for dc,rows in daily if dc['card']['display']=='scalar'];assert len(totals)==6
        if role=='director':
            expected={'oct30-31-gradual':[82119,72260,0,3570],'oct30-original':[72259,67205,65761,5054],'nov02-checkin':[82119,72249,0,3570]}[run['key']]
            assert [totals[i] for i in (0,1,2,5)]==expected
        period=charts(token(s,run,role,'period'))
        assert not any(dc['card']['display']=='scalar' for dc,_ in period)
        trend=[rows for dc,rows in period if 'Daily attendance trend' in dc['card']['name']];assert len(trend)==1 and len(trend[0])==1
        details=charts(token(s,run,role,'tables'))
        if role=='director':
            assert len(details)==3 and 'Department summary' in details[0][0]['card']['name']
            assert sum('Departments ranked' in dc['card']['name'] for dc,_ in details)==2
            assert not any('Employee daily' in dc['card']['name'] for dc,_ in daily+period+details)
        else:
            assert len(details)==1 and 'Employee daily' in details[0][0]['card']['name']
        for dc,rows in details:
            if 'Employee daily' in dc['card']['name']:assert all(str(row[2])[:10]==run['startDate'] for row in rows)
        names=checked(s.get(APP+'/api/departments',params={'run':run['key'],'q':'tata usaha' if role=='director' else ''},timeout=30))['departments']
        assert names
        if role=='director':assert all('tata usaha' in item['name'].lower() for item in names)
        else:assert all(item['id']==int(ENV['DEMO_MANAGER_DEPARTMENT_ID']) for item in names)
        # Daily dates are enforced server-side for both card and table embeds.
        for section in ('overview','tables'):
            invalid=s.post(APP+'/api/metabase-token',headers=HEAD,json={'entityType':'dashboard','entityId':run[role][section],'run':run['key'],'section':section,'startDate':'2026-10-30','endDate':'2026-10-31'},timeout=30)
            assert invalid.status_code==400
        # A period token can span both dates, without changing the daily token scope.
        token(s,run,role,'period',startDate='2026-10-30',endDate='2026-10-31')
        token(s,run,role,'overview')
        results.append({'role':role,'run':run['key'],'passed':True,'daily_metrics':totals,'daily_range_rejected':True,'period_range_accepted':True,'department_name_search':True,'role_appropriate_table':True})
        print(role,run['key'],'PASS',flush=True)
    if role=='manager':
        run=RUNS[0]
        token(s,run,role,'period',department='30187') # Signed scope remains the assigned department.
        denied=s.post(APP+'/api/metabase-token',headers=HEAD,json={'entityType':'dashboard','entityId':run['director']['period'],'run':run['key'],'section':'period'},timeout=30)
        assert denied.status_code==403
(OUT/'http_verification.json').write_text(json.dumps({'passed':True,'results':results},indent=2)+'\n')
