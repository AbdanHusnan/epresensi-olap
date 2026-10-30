"""Read-only HTTP checks for prototype sessions and signed Metabase department scope."""
import base64,csv,hashlib,hmac,io,json,time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[2]
env=dict(l.split('=',1) for l in (ROOT/'.env.hybrid').read_text().splitlines() if l and not l.startswith('#'))
APP='http://localhost:3100';BI='http://localhost:3101';HEAD={'Origin':APP}
reference=json.loads(Path(__file__).with_name('source_daily_http.json').read_text())['references']
manager_count=reference['manager'][0]
checks=[]
def ok(condition,name):
    assert condition,name
    checks.append(name);print('PASS:',name,flush=True)
def mint(payload):
    enc=lambda v:base64.urlsafe_b64encode(json.dumps(v,separators=(',',':')).encode()).decode().rstrip('=')
    v=enc({'alg':'HS256','typ':'JWT'})+'.'+enc(payload)
    return v+'.'+base64.urlsafe_b64encode(hmac.new(env['METABASE_EMBEDDING_SECRET'].encode(),v.encode(),hashlib.sha256).digest()).decode().rstrip('=')
for path in ['/','/analytical','/operational']:
    r=requests.get(APP+path,timeout=30);ok(r.url==APP+'/login',f'anonymous {path} redirects to login')
r=requests.post(APP+'/api/metabase-token',headers=HEAD,json={'entityType':'dashboard','entityId':1},timeout=30);ok(r.status_code==401,'anonymous token request denied')
r=requests.post(APP+'/api/auth/login',headers={'Origin':'http://other.invalid'},json={'username':'manager','password':'wrong'},timeout=30);ok(r.status_code==403,'cross-origin login denied')
for role,dashboard,expected in [('director',2,reference['director']),('manager',1,reference['manager'])]:
    s=requests.Session()
    r=s.post(APP+'/api/auth/login',headers=HEAD,json={'username':role,'password':'wrong'},timeout=30);ok(r.status_code==401,role+' wrong password denied')
    password=env['DEMO_'+role.upper()+'_PASSWORD']
    r=s.post(APP+'/api/auth/login',headers=HEAD,json={'username':role,'password':password},timeout=30);ok(r.status_code==200,role+' signs in')
    own='/analytical' if role=='director' else '/operational';other='/operational' if role=='director' else '/analytical'
    ok(s.get(APP+other,timeout=30).url==APP+own,role+' cannot open the other role page')
    r=s.post(APP+'/api/metabase-token',headers=HEAD,json={'entityType':'dashboard','entityId':3-dashboard},timeout=30);ok(r.status_code==403,role+' cannot mint other dashboard token')
    r=s.post(APP+'/api/metabase-token',headers=HEAD,json={'entityType':'dashboard','entityId':dashboard,'department':30187,'role':'director'},timeout=30);r.raise_for_status();token=r.json()['jwt']
    payload=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='))
    ok(payload['resource']=={'dashboard':dashboard} and payload['params']==({'department':30114} if role=='manager' else {}),role+' token scope derived from server account')
    meta=requests.get(BI+'/api/embed/dashboard/'+token,timeout=60);meta.raise_for_status();meta=meta.json()
    if role=='manager':ok('department' not in [p['slug'] for p in meta['parameters']],'manager department widget is locked')
    cards=sorted([c for c in meta['dashcards'] if c.get('card_id')],key=lambda c:(c['row'],c['col']));values=[]
    params={'start_date':'2026-10-30','end_date':'2026-10-30'}
    if role=='director':params['department']=None
    for c in cards:
        url=BI+f"/api/embed/dashboard/{token}/dashcard/{c['id']}/card/{c['card_id']}"
        r=requests.get(url,params={'parameters':json.dumps(params)},timeout=90);r.raise_for_status();result=r.json()
        ok(result.get('status')=='completed',role+f" chart {c['card_id']} completes")
        if c['card']['display']=='scalar':values.append(result['data']['rows'][0][0])
        if role=='manager':
            attack=requests.get(url,params={'parameters':json.dumps({**params,'department':30187})},timeout=60)
            ok(attack.status_code in [400,403],f"manager chart {c['card_id']} rejects department override")
            if 'Employee daily records' in c['card']['name']:
                rows=result['data']['rows'];ok(len(rows)==manager_count and all(x[2]==30114 for x in rows),'manager employee rows stay in assigned department')
                export=requests.get(url+'/csv',params={'parameters':json.dumps(params)},timeout=90);export.raise_for_status()
                exported=list(csv.DictReader(io.StringIO(export.text.lstrip('\ufeff'))));ok(len(exported)==manager_count and all(x['Department ID']=='30114' for x in exported),'manager CSV export stays in assigned department')
                bad_export=requests.get(url+'/csv',params={'parameters':json.dumps({**params,'department':30187})},timeout=60);ok(bad_export.status_code in [400,403],'manager export rejects department override')
    ok(values==expected,role+' six KPI values match reference SQL')
    original=s.cookies.get('attendance_session');parts=original.split('.');parts[2]=('A' if parts[2][0]!='A' else 'B')+parts[2][1:]
    tampered=requests.post(APP+'/api/metabase-token',headers={**HEAD,'Cookie':'attendance_session='+'.'.join(parts)},json={'entityType':'dashboard','entityId':dashboard},timeout=30);ok(tampered.status_code==401,'tampered '+role+' session denied')
    r=s.post(APP+'/api/auth/logout',headers=HEAD,timeout=30);ok(r.status_code==200 and s.get(APP+own,timeout=30).url==APP+'/login',role+' logout clears access')
expired=mint({'resource':{'dashboard':1},'params':{'department':30114},'exp':int(time.time())-60})
r=requests.get(BI+'/api/embed/dashboard/'+expired,timeout=60);ok(r.status_code in [400,401,403],'expired embed token rejected')
missing=mint({'resource':{'dashboard':1},'params':{},'exp':int(time.time())+60})
r=requests.get(BI+'/api/embed/dashboard/'+missing,timeout=60)
if r.ok:
    card=next(c for c in r.json()['dashcards'] if c.get('card_id'))
    r=requests.get(BI+f"/api/embed/dashboard/{missing}/dashcard/{card['id']}/card/{card['card_id']}",params={'parameters':json.dumps({'start_date':'2026-10-30','end_date':'2026-10-30'})},timeout=60)
ok(r.status_code in [400,401,403],'missing department scope cannot query data')
Path(__file__).with_name('website_security_results.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2)+'\n')
