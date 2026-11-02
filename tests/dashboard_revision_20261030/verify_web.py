"""Read-only regression checks for test history, table search, and role isolation."""
import base64
import json
from pathlib import Path
import requests
import run_batches as t

ROOT=t.ROOT
ENV=dict(l.split('=',1) for l in (ROOT/'.env.hybrid').read_text().splitlines() if l and not l.startswith('#'))
RUNS=json.loads((ROOT/'hybrid-dashboard/lib/test-runs.json').read_text())
APP='http://localhost:3100';BI='http://localhost:3101'
DATABASES={'oct30-31-gradual':'mart_bkd_gradual_20261030','oct30-original':'mart_bkd_bulk_20261029','nov02-checkin':'mart_bkd_checkin_20261102'}
METRICS=['active_employee_days','checkin_days','checkout_days','no_checkin_days','no_checkout_days','leave_days']
results=[]


def checked(response):
    if not response.ok: raise AssertionError('HTTP '+str(response.status_code))
    return response.json()


def get_token(session,run,role,section,search='',**filters):
    payload={'entityType':'dashboard','entityId':run[role][section],'run':run['key'],'section':section,'search':search,**filters}
    token=checked(session.post(APP+'/api/metabase-token',headers={'Origin':APP},json=payload,timeout=30))['jwt']
    claims=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='))
    assert claims['params']['start_date']==filters.get('startDate',run['startDate']) and claims['params']['end_date']==filters.get('endDate',run['endDate'])
    if role=='manager':assert claims['params']['department']==int(ENV['DEMO_MANAGER_DEPARTMENT_ID'])
    if section=='overview':assert 'search' not in claims['params']
    else:assert claims['params']['search']==(search or [])
    return token


def cards(token):
    meta=checked(requests.get(BI+'/api/embed/dashboard/'+token,timeout=60))
    out=[]
    for dc in sorted(meta['dashcards'],key=lambda x:(x['row'],x['col'])):
        if not dc.get('card_id'):continue
        assert 'Lateness assessment coverage' not in dc['card']['name']
        result=checked(requests.get(BI+f"/api/embed/dashboard/{token}/dashcard/{dc['id']}/card/{dc['card_id']}",timeout=120))
        assert result.get('status')=='completed',dc['card']['name']
        out.append((dc,result['data']['rows']))
    return out


for role in ('director','manager'):
    session=requests.Session()
    checked(session.post(APP+'/api/auth/login',headers={'Origin':APP},json={'username':role,'password':ENV['DEMO_'+role.upper()+'_PASSWORD']},timeout=30))
    for run in RUNS:
        overview=cards(get_token(session,run,role,'overview'))
        scalars=[rows[0][0] for dc,rows in overview if dc['card']['display']=='scalar']
        where=f"tanggal BETWEEN DATE '{run['startDate']}' AND DATE '{run['endDate']}'"
        if role=='manager':where+=' AND departemen_id_sumber='+ENV['DEMO_MANAGER_DEPARTMENT_ID']
        expected=t.base.data('SELECT jsonb_build_array('+','.join('SUM('+m+')' for m in METRICS)+') FROM mart_kehadiran.fact_kehadiran_daily WHERE '+where,target='mart',database=DATABASES[run['key']])
        assert scalars==expected,(role,run['key'],scalars,expected)
        if role=='director':
            known={'oct30-original':[72259,67205,65761,5054],'nov02-checkin':[82119,72249,0,3570],'oct30-31-gradual':[82119,72260,0,3570]}
            assert [scalars[i] for i in (0,1,2,5)]==known[run['key']],'Preserved baseline totals changed'
        for dc,rows in overview:
            if 'Departments ranked' in dc['card']['name']:
                assert dc['card']['display']=='table'
                assert all(len(row)==6 and row[4]>0 and abs(float(row[5])-round(100*row[3]/row[4],2))<0.011 for row in rows)
            if 'Daily attendance trend' in dc['card']['name']:
                assert len(rows)==1,'Only one date is loaded in each test at this checkpoint'
        details=cards(get_token(session,run,role,'tables'))
        searched=cards(get_token(session,run,role,'tables','ZZZ_NO_MATCH_7be298'))
        assert all(not rows for _,rows in searched),'Table search did not filter results'
        # A search supplied to the overview is ignored by the signer. Its data
        # must stay byte-for-byte equal to the pre-search result.
        after=cards(get_token(session,run,role,'overview','ZZZ_NO_MATCH_7be298'))
        assert [r for _,r in overview]==[r for _,r in after],'Search changed overview data'
        if role=='manager':
            for dc,rows in details:
                assert all(row[3]==int(ENV['DEMO_MANAGER_DEPARTMENT_ID']) for row in rows)
            attack=session.post(APP+'/api/metabase-token',headers={'Origin':APP},json={'entityType':'dashboard','entityId':run['director']['overview'],'run':run['key'],'section':'overview'},timeout=30)
            assert attack.status_code==403,'Manager accessed director dashboard'
            tok=get_token(session,run,role,'tables');meta=checked(requests.get(BI+'/api/embed/dashboard/'+tok,timeout=60));dc=next(c for c in meta['dashcards'] if c.get('card_id'))
            attack=requests.get(BI+f"/api/embed/dashboard/{tok}/dashcard/{dc['id']}/card/{dc['card_id']}",params={'parameters':json.dumps({'department':30187})},timeout=60)
            assert attack.status_code in (400,403),'Locked department override accepted'
        results.append({'role':role,'run':run['key'],'passed':True,'metrics':scalars,'overview_cards':len(overview),'detail_tables':len(details),'table_search_isolated':True})
        print(role,run['key'],'PASS',flush=True)
    run=RUNS[0]
    if role=='director':
        scoped=cards(get_token(session,run,role,'overview',department='30114'))
        scoped_totals=[rows[0][0] for dc,rows in scoped if dc['card']['display']=='scalar']
        expected=t.base.data('SELECT jsonb_build_array('+','.join('SUM('+m+')' for m in METRICS)+") FROM mart_kehadiran.fact_kehadiran_daily WHERE tanggal=DATE '2026-10-30' AND departemen_id_sumber=30114",target='mart')
        assert scoped_totals==expected,'Shared department filter failed'
    empty=cards(get_token(session,run,role,'overview',startDate='2026-10-31',endDate='2026-10-31'))
    assert all(rows==[[None]] for dc,rows in empty if dc['card']['display']=='scalar'),'Unloaded day displayed as zero'
    assert all(not rows for dc,rows in empty if 'Daily attendance trend' in dc['card']['name']),'Unloaded trend invented a date'
    bad=session.post(APP+'/api/metabase-token',headers={'Origin':APP},json={'entityType':'dashboard','entityId':RUNS[0][role]['overview'],'run':'untrusted'},timeout=30)
    assert bad.status_code==400
( Path(__file__).parent/'web_verification.json').write_text(json.dumps({'passed':True,'checks':results},indent=2)+'\n')
