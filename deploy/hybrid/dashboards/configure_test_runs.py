"""Provision immutable datasource bindings and separate daily/detail/period embeds.

Never repoints an existing database connection. Writes a public, secret-free
website registry only after every dashboard has been provisioned successfully.
"""
import copy
import json
from pathlib import Path
import re
import requests
import subprocess

ROOT = Path(__file__).resolve().parents[3]
ENV = dict(l.split('=',1) for l in (ROOT/'.env.hybrid').read_text().splitlines() if l and not l.startswith('#'))
S = requests.Session()
BASE = 'http://127.0.0.1:3101/api'


def api(method, path, payload=None):
    response = S.request(method, BASE+path, json=payload, timeout=120)
    if not response.ok: raise RuntimeError(f'{method} {path}: HTTP {response.status_code}')
    return response.json() if response.content else None


def native(card):
    query = card['dataset_query']
    if 'native' in query: return query['native']['query'], query['native']['template-tags']
    stage = query['stages'][0]
    return stage['native'], {tag['name']:tag for tag in stage['template-tags']}


def ranking(late):
    if late:
        name, numerator, denominator, rate = 'Late employees', "v.is_employee_active AND NOT v.has_excused_checkin AND v.lateness_status='LATE'", "v.is_employee_active AND NOT v.has_excused_checkin AND v.lateness_status IN ('LATE','ON_TIME')", 'Late %'
        source = "FROM serving.v_lateness_employee_daily v WHERE v.tanggal >= {{start_date}} AND v.tanggal <= {{end_date}} [[AND v.departemen_id_sumber = {{department}}]]"
        employee, dep, label = 'v.pegawai_id_sumber', 'v.departemen_id_sumber', "COALESCE(MAX(v.nama_departemen),'UNKNOWN')"
        den_label = 'Assessed employees'
    else:
        name, numerator, denominator, rate = 'Employees with izin', 'f.active_employee_days=1 AND f.leave_days=1', 'f.active_employee_days=1', 'Izin %'
        source = "FROM mart_kehadiran.fact_kehadiran_daily f JOIN mart_kehadiran.dim_departemen d USING (departemen_key) WHERE f.tanggal >= {{start_date}} AND f.tanggal <= {{end_date}} [[AND f.departemen_id_sumber = {{department}}]]"
        employee, dep, label = 'f.pegawai_id_sumber', 'f.departemen_id_sumber', "COALESCE(MAX(d.nama),'UNKNOWN')"
        den_label = 'Active employees'
    return f'''WITH counts AS (
 SELECT {dep} AS department_id, {label} AS department,
 COUNT(DISTINCT {employee}) FILTER (WHERE {numerator}) AS affected,
 COUNT(DISTINCT {employee}) FILTER (WHERE {denominator}) AS eligible
 {source} GROUP BY {dep}
), rates AS (SELECT *, ROUND(100.0*affected/NULLIF(eligible,0),2) AS rate FROM counts WHERE eligible>0)
SELECT ROW_NUMBER() OVER (ORDER BY rate DESC,affected DESC,eligible DESC,department,department_id NULLS LAST) AS "Rank",
 department AS "Department",department_id AS "Department ID",affected AS "{name}",eligible AS "{den_label}",rate AS "{rate}"
FROM rates ORDER BY rate DESC,affected DESC,eligible DESC,department,department_id NULLS LAST LIMIT 10''', rate


def main():
    S.headers['X-Metabase-Session'] = api('POST','/session',{'username':ENV['BI_ADMIN_EMAIL'],'password':ENV['BI_ADMIN_PASSWORD']})['id']
    databases = api('GET','/database')['data']
    connection = copy.deepcopy(next(d for d in databases if d['name']=='Attendance mart (read only)'))
    templates = {role:api('GET',f'/dashboard/{ENV[key]}') for role,key in [('director','METABASE_ANALYTICAL_DASHBOARD_ID'),('manager','METABASE_OPERATIONAL_DASHBOARD_ID')]}
    # Persist source definitions once: regeneration must not clone our own split layouts.
    snapshot = ROOT/'deploy/hybrid/dashboards/test-run-templates.json'
    if snapshot.exists(): templates=json.loads(snapshot.read_text())
    else:
        templates = {role:{key:value for key,value in d.items() if key in ('collection_id','parameters','dashcards')} for role,d in templates.items()}
        for d in templates.values():
            for c in d['dashcards']:
                if c.get('card'):
                    c['card'] = {key:value for key,value in c['card'].items() if key in ('id','name','description','display','dataset_query','visualization_settings')}
        snapshot.write_text(json.dumps(templates,indent=2)+'\n')
    existing_cards=api('GET','/card')
    dashboards=api('GET','/dashboard'); dashboards=dashboards.get('data',[]) if isinstance(dashboards,dict) else dashboards
    runs = [
      {'key':'oct30-31-gradual','label':'30–31 October 2026 · gradual test','startDate':'2026-10-30','endDate':'2026-10-31','database':'mart_bkd_gradual_20261030','note':'Batch 1 of 4: 30 October morning check-ins. Awaiting review before afternoon checkouts. 31 October has not been loaded; missing dates are not zero.'},
      {'key':'oct30-original','label':'30 October 2026 · original test','startDate':'2026-10-30','endDate':'2026-10-30','database':'mart_bkd_bulk_20261029','note':'Preserved original test: 72,259 employees in the Friday-schedule cohort. Lateness is unavailable where the original event lacked window evidence.'},
      {'key':'nov02-checkin','label':'2 November 2026 · check-in test','startDate':'2026-11-02','endDate':'2026-11-02','database':'mart_bkd_checkin_20261102','note':'Preserved check-in-only test: 82,119 currently active employees. Zero checkouts.'},
    ]
    registry=[]
    department_options={}
    for run in runs:
        source=next((d for d in databases if d['details'].get('dbname')==run['database']),None)
        if not source:
            details={**connection['details'],'dbname':run['database'],'password':ENV['METABASE_MART_PASSWORD']}
            source=api('POST','/database',{'name':'Attendance test · '+run['key'],'engine':'postgres','details':details,'is_full_sync':False})
            databases.append(source)
        # No existing connection is mutated, even when default test changes.
        query = "SELECT COALESCE(jsonb_agg(jsonb_build_object('id',id,'name',name) ORDER BY name,id),'[]'::jsonb) FROM (SELECT f.departemen_id_sumber AS id,COALESCE(MAX(d.nama),'Unnamed department') AS name FROM mart_kehadiran.fact_kehadiran_daily f JOIN mart_kehadiran.dim_departemen d USING(departemen_key) WHERE f.departemen_id_sumber IS NOT NULL GROUP BY f.departemen_id_sumber) x"
        result = subprocess.run(['docker','exec','-i','epresensi-mart-postgres','sh','-c','exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"','sql',run['database']], input=query, text=True, capture_output=True, check=True)
        department_options[run['key']] = json.loads(result.stdout)
        item={k:v for k,v in run.items() if k!='database'}
        for role,template in templates.items():
            item[role]={}
            for section in ('overview','tables','period'):
                name=f"Attendance {run['key']} · {role} · {section}"
                old=next((d for d in dashboards if d['name']==name),None)
                params=copy.deepcopy(template['parameters'])
                for p in params:
                    p.pop('default',None)
                params=[p for p in params if p['id']!='search' or section=='tables']
                embedding={'start_date':'locked','end_date':'locked','department':'locked'}
                if section=='tables': embedding['search']='locked'
                payload={'name':name,'collection_id':template['collection_id'],'description':run['note'],'parameters':params,'enable_embedding':True,'embedding_params':embedding}
                dash=api('PUT',f"/dashboard/{old['id']}",payload) if old else api('POST','/dashboard',payload)
                api('PUT',f"/dashboard/{dash['id']}",{'enable_embedding':True,'embedding_params':embedding})
                current=api('GET',f"/dashboard/{dash['id']}")['dashcards']
                placed=[]
                originals=sorted(template['dashcards'],key=lambda c:(c['row'],c['col']))
                if section=='tables' and role=='director':
                    originals.sort(key=lambda c:(0 if 'Department summary' in (c.get('card') or {}).get('name','') else 1,c['row'],c['col']))
                for dc in originals:
                    original=dc.get('card')
                    if not original or not original.get('name') or 'Lateness assessment coverage' in original['name']: continue
                    if role=='director' and 'Employee daily records' in original['name']: continue
                    detail=any(x in original['name'] for x in ('Employee daily records','Department summary'))
                    period_card=any(x in original['name'] for x in ('Daily attendance trend','Data coverage'))
                    ranked='Departments ranked' in original['name']
                    if section=='tables' and not (detail or ranked): continue
                    if section=='overview' and (detail or period_card or ranked): continue
                    if section=='period' and not period_card: continue
                    query,tags=native(original)
                    if role=='director' and detail:
                        query=re.sub(r'\[\[AND[^\[\]]*\{\{search\}\}[^\[\]]*\]\]', "[[AND COALESCE(d.nama,'') ILIKE '%' || {{search}} || '%']]",query,flags=re.S)
                    tags=copy.deepcopy(tags)
                    for key in ('start_date','end_date'): tags[key].pop('default',None)
                    if not detail:
                        query=re.sub(r'\[\[AND[^\[\]]*\{\{search\}\}[^\[\]]*\]\]', '', query, flags=re.S)
                        tags.pop('search',None)
                    card_name=f"{run['key']} · {original['name']}"
                    display=original['display'];settings=copy.deepcopy(original.get('visualization_settings',{}));title=dc.get('visualization_settings',{}).get('card.title',original['name'].split(' | ')[-1])
                    if 'Departments ranked' in original['name']:
                        late='first-shift lateness' in original['name'];query,rate=ranking(late);display='table'
                        settings={'table.pivot':False,'table.column_widths':[52,440,110,145,155,90],'column_settings':{json.dumps(['name','Department ID'],separators=(',',':')):{'number_separators':'.','decimals':0},json.dumps(['name',rate],separators=(',',':')):{'decimals':2,'suffix':'%'}}}
                        title='Top 10 departments · '+('first-shift lateness' if late else 'employees with izin')
                    if 'Daily attendance trend' in original['name']:
                        # Ordinal date buckets and explicit points retain a visible one-day checkpoint.
                        settings.update({'graph.show_points':True,'graph.show_values':True,'graph.x_axis.scale':'ordinal','graph.missing_value':'nothing'})
                    cp={'name':card_name,'collection_id':template['collection_id'],'display':display,'description':original.get('description','')+' Rankings show distinct people over the period; ties use affected count then denominator. Search applies only to detail tables.',
                        'dataset_query':{'database':source['id'],'type':'native','native':{'query':query,'template-tags':tags}},'visualization_settings':settings}
                    existing=next((c for c in existing_cards if c['name']==card_name),None)
                    card=api('PUT',f"/card/{existing['id']}",cp) if existing else api('POST','/card',cp)
                    prior=next((c for c in current if c.get('card_id')==card['id']),None)
                    if section=='period': row=sum(c['size_y'] for c in placed);height=7 if 'Daily attendance trend' in original['name'] else 4
                    elif section=='tables': row=sum(c['size_y'] for c in placed);height=11 if ranked else 14
                    elif 'Departments ranked' in original['name']: row=14+sum(c['size_y'] for c in placed if c['row']>=14);height=11
                    elif 'Data coverage' in original['name']: row=36;height=4
                    else: row=dc['row'];height=dc['size_y']
                    if section!='period': title=title.replace(' (employee-days)','').replace('Department summary — employee-days','Department summary — daily employees')
                    placed.append({'id':prior['id'] if prior else -(len(placed)+1),'card_id':card['id'],'row':row,'col':dc['col'] if row<9 else 0,'size_x':dc['size_x'],'size_y':height,'visualization_settings':{'card.title':title},'parameter_mappings':[{'parameter_id':k,'card_id':card['id'],'target':['variable',['template-tag',k]]} for k in tags if any(p['id']==k for p in params)]})
                api('PUT',f"/dashboard/{dash['id']}",{'dashcards':placed})
                item[role][section]=dash['id']
                print(run['key'],role,section,dash['id'],flush=True)
        registry.append(item)
    (ROOT/'hybrid-dashboard/lib/department-options.json').write_text(json.dumps(department_options,ensure_ascii=False,separators=(',',':'))+'\n')
    (ROOT/'hybrid-dashboard/lib/test-runs.json').write_text(json.dumps(registry,indent=2)+'\n')


if __name__=='__main__': main()
