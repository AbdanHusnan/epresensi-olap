"""Create/update the four-baseline comparison's Metabase dashboards. No mart writes."""
import json
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[3]
env=dict(l.split('=',1) for l in (ROOT/'.env.hybrid').read_text().splitlines() if l and not l.startswith('#'))
s=requests.Session(); BASE='http://127.0.0.1:3101'
def api(method,path,body=None):
 r=s.request(method,BASE+'/api'+path,json=body,timeout=120)
 if not r.ok: raise RuntimeError(f'{method} {path}: {r.status_code} {r.text[:500]}')
 return r.json() if r.content else None
s.headers['X-Metabase-Session']=api('POST','/session',{'username':env['BI_ADMIN_EMAIL'],'password':env['BI_ADMIN_PASSWORD']})['id']
source=next(d for d in api('GET','/database')['data'] if d['name']=='Attendance mart (read only)')
assert source['details']['dbname']==env.get('MART_DATABASE','mart_bkd')
test_date=env.get('DASHBOARD_TEST_DATE','2026-10-30')
# The source-based cohort spans 3829 departments; retain the employee SQL LIMIT 1000.
api('PUT','/setting/unaggregated-query-row-limit',{'value':5000})
collections=api('GET','/collection')
collection=next((c for c in collections if c['name']=='Attendance comparison — TEST'),None) or api('POST','/collection',{'name':'Attendance comparison — TEST','description':'Provisional bulk test data, 30 October 2026. GUI comparison only; filters are not authorization.'})
metrics=[('active_employee_days','Pegawai Aktif'),('checkin_days','Absen Masuk'),('checkout_days','Absen Pulang'),('no_checkin_days','Tidak Absen Masuk'),('no_checkout_days','Tidak Absen Pulang'),('leave_days','Pegawai Izin')]
# Search belongs to the two detail tables only. Overview totals and trends keep
# the full authorized date/department scope.
where='''f.tanggal >= {{start_date}} AND f.tanggal <= {{end_date}}
[[AND f.departemen_id_sumber = {{department}}]]
[[AND (CAST(f.pegawai_id_sumber AS text) ILIKE '%' || {{search}} || '%'
        OR COALESCE(p.nama,'') ILIKE '%' || {{search}} || '%'
        OR CAST(f.departemen_id_sumber AS text) ILIKE '%' || {{search}} || '%'
        OR COALESCE(d.nama,'') ILIKE '%' || {{search}} || '%')]]'''
base_from='''FROM mart_kehadiran.fact_kehadiran_daily f
JOIN mart_kehadiran.dim_pegawai p USING(pegawai_key)
JOIN mart_kehadiran.dim_departemen d USING(departemen_key)
LEFT JOIN serving.attendance_date_state s USING(tanggal)'''
existing_cards=api('GET','/card'); existing_dash=api('GET','/dashboard'); existing_dash=existing_dash.get('data',[]) if isinstance(existing_dash,dict) else existing_dash
out={}
for role in ['Operational','Organization']:
 tags={k:{'id':k,'name':k,'display-name':label,'type':typ,'required':req,**({'default':default} if default is not None else {})} for k,label,typ,req,default in [('start_date','Start date','date',True,test_date),('end_date','End date','date',True,test_date),('department','Department source ID','number',False,30114 if role=='Operational' else None),('search','Employee or department','text',False,None)]}
 params=[{'id':k,'name':v['display-name'],'slug':k,'type':'date/single' if k not in ('department','search') else ('number/=' if k=='department' else 'string/contains'),**({'default':v['default']} if 'default' in v else {})} for k,v in tags.items()]
 title=f'{role} Attendance — TEST'
 d=next((d for d in existing_dash if d['name']==title),None)
 payload={'name':title,'description':f'TEST DATA — Provisional. Available: {test_date}. Simulated attendance based on current employee/schedule snapshots. Counts across dates are employee-days. Missing days are not zero. Department GUI filters alone are not authorization.','collection_id':collection['id'],'parameters':params}
 d=api('PUT',f"/dashboard/{d['id']}",payload) if d else api('POST','/dashboard',payload)
 cards=[]
 specs=[]
 for m,label in metrics:
  specs.append((label+(' (employee-days)' if role=='Organization' else ''),f'SELECT SUM(f.{m}) AS "{label}" {base_from} WHERE {where}','scalar',{},4,3))
 specs.append(('Daily attendance trend',f'SELECT f.tanggal AS "Date",SUM(f.checkin_days) AS "Absen Masuk",SUM(f.checkout_days) AS "Absen Pulang" {base_from} WHERE {where} GROUP BY f.tanggal ORDER BY f.tanggal','line',{'graph.dimensions':['Date'],'graph.metrics':['Absen Masuk','Absen Pulang'],'graph.show_values':True,'graph.show_points':True,'graph.x_axis.scale':'ordinal'},12,5))
 employee_query=f'''SELECT f.pegawai_id_sumber AS "Employee ID",COALESCE(p.nama,'Employee '||f.pegawai_id_sumber::text) AS "Employee",f.tanggal AS "Date",f.departemen_id_sumber AS "Department ID",COALESCE(d.nama,'Department '||f.departemen_id_sumber::text) AS "Department",first_checkin_at AS "First check-in",last_checkout_at AS "Last check-out",has_masuk AS "Check-in",has_pulang AS "Check-out",has_valid_leave AS "Valid leave",has_excused_checkin AS "Exempt check-in",has_excused_checkout AS "Exempt check-out",perlu_review AS "Needs review",NOT is_date_final AS "Provisional" {base_from} WHERE {where} AND f.active_employee_days=1 ORDER BY f.tanggal,f.pegawai_id_sumber LIMIT 1000'''
 if role=='Operational':
  query=employee_query
  label='Employee daily records — up to 1,000 rows'
 else:
  sums=','.join(f'SUM(f.{m}) AS "{label}"' for m,label in metrics)
  query=f'''SELECT f.departemen_id_sumber AS "Department ID",COALESCE(MAX(d.nama),'Department '||f.departemen_id_sumber::text,'UNKNOWN') AS "Department",{sums},ROUND(100.0*SUM(f.checkin_days)/NULLIF(SUM(f.active_employee_days),0),2) AS "Check-in %",ROUND(100.0*SUM(f.checkout_days)/NULLIF(SUM(f.active_employee_days),0),2) AS "Check-out %",ROUND(100.0*SUM(f.required_checkin_present_days)/NULLIF(SUM(f.required_checkin_days),0),2) AS "Required check-in %",ROUND(100.0*SUM(f.required_checkout_present_days)/NULLIF(SUM(f.required_checkout_days),0),2) AS "Required check-out %",BOOL_OR(f.perlu_review OR NOT f.is_date_final) AS "Provisional" {base_from} WHERE {where} GROUP BY f.departemen_id_sumber ORDER BY f.departemen_id_sumber NULLS LAST LIMIT 5000'''
  label='Department summary — employee-days'
 id_columns = ['Employee ID', 'Department ID'] if role == 'Operational' else ['Department ID']
 id_settings = {'column_settings': {json.dumps(['name', column], separators=(',', ':')): {'number_style': 'decimal', 'number_separators': '.', 'decimals': 0} for column in id_columns}}
 specs.append((label,query,'table',id_settings,12,14))
 query=f'''SELECT CASE WHEN COUNT(*)=0 THEN 'NO DATA' WHEN BOOL_OR(f.perlu_review OR NOT f.is_date_final) THEN 'PROVISIONAL' ELSE 'FINAL' END AS "Status",MIN(f.tanggal) AS "First available date",MAX(f.tanggal) AS "Last available date",COUNT(DISTINCT f.tanggal) AS "Available dates",CAST({{{{end_date}}}} AS date)-CAST({{{{start_date}}}} AS date)+1 AS "Requested dates",BOOL_AND(COALESCE(s.population_complete AND s.curated_delivery_complete,false)) AS "Published data complete",MIN(s.updated_at) AT TIME ZONE 'Asia/Jakarta' AS "Oldest refresh (Jakarta)",MAX(s.updated_at) AT TIME ZONE 'Asia/Jakarta' AS "Latest refresh (Jakarta)" {base_from} WHERE {where}'''
 specs.append(('Data coverage and publication status',query,'table',{},12,4))
 for i,(label,query,display,settings,w,h) in enumerate(specs):
  name=f'{role} | {label}'
  is_detail = 'Employee daily records' in label or 'Department summary' in label
  card_tags = tags if is_detail else {k:v for k,v in tags.items() if k != 'search'}
  if not is_detail:
   import re
   query = re.sub(r'\[\[AND[^\[\]]*\{\{search\}\}[^\[\]]*\]\]', '', query, flags=re.S)
  p={'name':name,'collection_id':collection['id'],'display':display,'description':'ATTENDANCE_DAILY_V1. Test data only. Period counts are employee-days. NULL means unavailable or undefined, not zero.','dataset_query':{'database':source['id'],'type':'native','native':{'query':query,'template-tags':card_tags}},'visualization_settings':settings}
  card=next((c for c in existing_cards if c['name']==name),None)
  card=api('PUT',f"/card/{card['id']}",p) if card else api('POST','/card',p)
  row=3+(i//3)*3 if i<6 else (9 if i==6 else (14 if i==7 else (28 if role=='Operational' or i==8 else 42)))
  cards.append({'id':-(i+2),'card_id':card['id'],'row':row,'col':(i%3)*8 if i<6 else 0,'size_x':w*2,'size_y':h,'parameter_mappings':[{'parameter_id':k,'card_id':card['id'],'target':['variable',['template-tag',k]]} for k in card_tags],'visualization_settings':{'card.title':label}})
 cards.insert(0,{'id':-1,'card_id':None,'row':0,'col':0,'size_x':24,'size_y':3,'parameter_mappings':[],'visualization_settings':{'virtual_card':{'display':'text','visualization_settings':{},'dataset_query':{}},'text':f'## TEST DATA — Provisional\nSimulated attendance date: **{test_date}**. Current employee and schedule snapshots, not proof of future assignments. Check-in-only checkpoint; checkout has not been loaded. Multi-day attendance counts mean **employee-days**. Missing dates are not zero.'}})
 current = api('GET',f"/dashboard/{d['id']}").get('dashcards',[])
 for c in cards:
  old = next((x for x in current if x.get('card_id') == c['card_id']),None)
  if old: c['id']=old['id']
 api('PUT',f"/dashboard/{d['id']}",{'dashcards':cards})
 out[role]={'id':d['id'],'url':f"http://localhost:3101/dashboard/{d['id']}",'cards':[c['card_id'] for c in cards if c['card_id']]}
 print(role,out[role]['url'],flush=True)
(ROOT/'deploy/hybrid/dashboards/metabase-manifest.json').write_text(json.dumps(out,indent=2)+'\n')
