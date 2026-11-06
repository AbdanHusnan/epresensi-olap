#!/usr/bin/env python3
"""Read-only checks of November daily and monthly embedded dashboard results."""
import argparse
import base64
import json
from pathlib import Path
import requests
import fill_month as month

ROOT=Path(__file__).resolve().parents[2]
ENV=dict(line.split('=',1) for line in (ROOT/'.env.hybrid').read_text().splitlines() if line and not line.startswith('#'))
RUN=json.loads((ROOT/'hybrid-dashboard/lib/test-runs.json').read_text())[0]
APP='http://localhost:3100'
BI='http://localhost:3101'
METRICS=['active_employee_days','checkin_days','checkout_days','no_checkin_days','no_checkout_days','leave_days']


def checked(response,label):
    assert response.ok,f'{label}: HTTP {response.status_code}'
    return response.json()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day',action='append',help='Check a specific YYYY-MM-DD date (repeatable)')
    parser.add_argument('--daily-only',action='store_true',help='Skip the full-month trend until all dates are loaded')
    args=parser.parse_args()
    dates=args.day or ['2026-11-01','2026-11-16','2026-11-30']
    results=[]
    assert RUN['key']=='november-2026'
    for role in ('director','manager'):
        session=requests.Session()
        checked(session.post(APP+'/api/auth/login',headers={'Origin':APP},json={'username':role,'password':ENV['DEMO_'+role.upper()+'_PASSWORD']},timeout=30),'login')
        for day in dates:
            for section in (('overview',) if args.daily_only else ('overview','period')):
                start=RUN['startDate'] if section=='period' else day
                end=RUN['endDate'] if section=='period' else day
                if section=='period' and day!=dates[0]: continue
                dashboard=RUN[role][section]
                payload={'entityType':'dashboard','entityId':dashboard,'run':RUN['key'],'section':section,'startDate':start,'endDate':end}
                token=checked(session.post(APP+'/api/metabase-token',headers={'Origin':APP},json=payload,timeout=30),'embed token')['jwt']
                claims=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='))
                assert claims['params']['start_date']==start and claims['params']['end_date']==end
                if role=='manager': assert claims['params']['department']==int(ENV['DEMO_MANAGER_DEPARTMENT_ID'])
                meta=checked(requests.get(BI+'/api/embed/dashboard/'+token,timeout=60),'embed metadata')
                counts=[]
                charts=[]
                for card in sorted((c for c in meta['dashcards'] if c.get('card_id')),key=lambda c:(c['row'],c['col'])):
                    url=BI+f"/api/embed/dashboard/{token}/dashcard/{card['id']}/card/{card['card_id']}"
                    result=checked(requests.get(url,timeout=120),'embedded chart')
                    assert result.get('status')=='completed','Embedded query did not complete'
                    rows=result['data']['rows']
                    name=card['card']['name']
                    if section=='overview' and card['row'] in (3,6) and card['card']['display']=='scalar':
                        counts.append(rows[0][0])
                    if section=='period' and 'Daily attendance trend' in name:
                        assert len(rows)==30,'Trend does not contain all November days'
                    charts.append({'card':card['card_id'],'name':name,'rows':len(rows)})
                if section=='overview':
                    clause='' if role=='director' else ' AND departemen_id_sumber='+str(int(ENV['DEMO_MANAGER_DEPARTMENT_ID']))
                    expected=month.data('SELECT jsonb_build_array('+','.join('SUM('+m+')' for m in METRICS)+") FROM mart_kehadiran.fact_kehadiran_daily WHERE tanggal=DATE '"+day+"'"+clause,'mart')
                    assert counts==expected,f'{role} {day}: KPI counts do not match mart'
                results.append({'role':role,'section':section,'start':start,'end':end,'passed':True,'charts':charts})
                print(role,section,start,end,'PASS',flush=True)
        session.post(APP+'/api/auth/logout',headers={'Origin':APP},timeout=30)
    (month.OUT/('dashboard_verification_daily.json' if args.daily_only else 'dashboard_verification.json')).write_text(json.dumps({'passed':True,'checks':results},indent=2)+'\n')


if __name__=='__main__':main()
