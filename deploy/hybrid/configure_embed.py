"""Enable signed Metabase guest embeds and provision local prototype login settings."""
import json
from pathlib import Path
import secrets
import requests
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'.env.hybrid'
env=dict(l.split('=',1) for l in p.read_text().splitlines() if l and not l.startswith('#'))
s=requests.Session();base='http://127.0.0.1:3101/api'
def api(method,path,payload=None):
    r=s.request(method,base+path,json=payload,timeout=90)
    if not r.ok:raise SystemExit(f'Metabase {method} {path} failed with HTTP {r.status_code}; response suppressed.')
    return r.json() if r.content else None
s.headers['X-Metabase-Session']=api('POST','/session',{'username':env['BI_ADMIN_EMAIL'],'password':env['BI_ADMIN_PASSWORD']})['id']
settings={x['key']:x.get('value') for x in api('GET','/setting')}
additions={
    'APP_SESSION_SECRET':secrets.token_hex(32),
    'METABASE_EMBEDDING_SECRET':settings.get('embedding-secret-key') or secrets.token_hex(32),
    'METABASE_ANALYTICAL_DASHBOARD_ID':'2',
    'METABASE_OPERATIONAL_DASHBOARD_ID':'1',
    'DEMO_DIRECTOR_PASSWORD':secrets.token_urlsafe(14),
    'DEMO_MANAGER_PASSWORD':secrets.token_urlsafe(14),
    'DEMO_MANAGER_DEPARTMENT_ID':'30114',
}
with p.open('a') as f:
    for key,value in additions.items():
        if key not in env:f.write(f'{key}={value}\n');env[key]=value
p.chmod(0o600)
api('PUT','/setting/embedding-secret-key',{'value':env['METABASE_EMBEDDING_SECRET']})
for key in ['enable-embedding-static','enable-embedding-simple']:
    api('PUT','/setting/'+key,{'value':True})
origins=set((settings.get('embedding-app-origins-sdk') or '').split())
origins.update(['http://localhost:3100','http://127.0.0.1:3100'])
api('PUT','/setting/embedding-app-origins-sdk',{'value':' '.join(sorted(origins))})
for role,key in [('manager','METABASE_OPERATIONAL_DASHBOARD_ID'),('director','METABASE_ANALYTICAL_DASHBOARD_ID')]:
    dashboard_id=int(env[key]);dashboard=api('GET',f'/dashboard/{dashboard_id}')
    if role=='manager':
        for card in dashboard['dashcards']:
            if card.get('card_id') and not any(m['parameter_id']=='department' for m in card.get('parameter_mappings',[])):
                raise SystemExit('Operational card has no department mapping; refusing to enable embedding.')
    api('PUT',f'/dashboard/{dashboard_id}',{'enable_embedding':True,'embedding_params':{'start_date':'enabled','end_date':'enabled','department':'locked' if role=='manager' else 'enabled'}})
    print(f'{role}: dashboard {dashboard_id} guest embedding configured.')
print('Prototype app settings preserved in .env.hybrid. No attendance data changed.')
