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
 return r.json()
s.headers['X-Metabase-Session']=api('POST','/session',{'username':env['BI_ADMIN_EMAIL'],'password':env['BI_ADMIN_PASSWORD']})['id']
source=next(d for d in api('GET','/database')['data'] if d['name']=='Attendance mart (read only)')
assert source['details']['dbname']=='mart_bkd_bulk_20261029'
# The source-based cohort spans 3829 departments; retain the employee SQL LIMIT 1000.
api('PUT','/setting/unaggregated-query-row-limit',{'value':5000})
collections=api('GET','/collection')
collection=next((c for c in collections if c['name']=='Attendance comparison — TEST'),None) or api('POST','/collection',{'name':'Attendance comparison — TEST','description':'Provisional bulk test data, 30 October 2026. GUI comparison only; filters are not authorization.'})
metrics=[('active_employee_days','Pegawai Aktif'),('checkin_days','Absen Masuk'),('checkout_days','Absen Pulang'),('no_checkin_days','Tidak Absen Masuk'),('no_checkout_days','Tidak Absen Pulang'),('leave_days','Pegawai Izin')]
where='tanggal >= {{start_date}} AND tanggal <= {{end_date}} [[AND departemen_id_sumber = {{department}}]]'
existing_cards=api('GET','/card'); existing_dash=api('GET','/dashboard'); existing_dash=existing_dash.get('data',[]) if isinstance(existing_dash,dict) else existing_dash
out={}
for role in ['Operational','Organization']:
 tags={k:{'id':k,'name':k,'display-name':label,'type':typ,'required':req,**({'default':default} if default is not None else {})} for k,label,typ,req,default in [('start_date','Start date','date',True,'2026-10-30'),('end_date','End date','date',True,'2026-10-30'),('department','Department source ID','number',False,30114 if role=='Operational' else None)]}
 params=[{'id':k,'name':v['display-name'],'slug':k,'type':'date/single' if k!='department' else 'number/=',**({'default':v['default']} if 'default' in v else {})} for k,v in tags.items()]
 title=f'{role} Attendance — TEST'
 d=next((d for d in existing_dash if d['name']==title),None)
 payload={'name':title,'description':'TEST DATA — Provisional. Available: 30 Oct 2026 only. Counts across dates are employee-days. Missing days are not zero. Department filters are GUI preview controls, not access restrictions.','collection_id':collection['id'],'parameters':params}
 d=api('PUT',f"/dashboard/{d['id']}",payload) if d else api('POST','/dashboard',payload)
 cards=[]
 specs=[]
 for m,label in metrics:
  specs.append((label+(' (employee-days)' if role=='Organization' else ''),f'SELECT SUM({m}) AS "{label}" FROM serving.v_kehadiran_departemen_harian WHERE {where}','scalar',{},4,3))
 specs.append(('Daily attendance trend',f'SELECT tanggal AS "Date",SUM(checkin_days) AS "Absen Masuk",SUM(checkout_days) AS "Absen Pulang" FROM serving.v_kehadiran_departemen_harian WHERE {where} GROUP BY tanggal ORDER BY tanggal','line',{'graph.dimensions':['Date'],'graph.metrics':['Absen Masuk','Absen Pulang'],'graph.show_values':True,'graph.show_points':True,'graph.x_axis.scale':'ordinal'},12,5))
 if role=='Operational':
  query=f'''SELECT pegawai_id_sumber AS "Employee ID", tanggal AS "Date",departemen_id_sumber AS "Department ID",first_checkin_at AS "First check-in",last_checkout_at AS "Last check-out",has_masuk AS "Check-in",has_pulang AS "Check-out",has_valid_leave AS "Valid leave",has_excused_checkin AS "Exempt check-in",has_excused_checkout AS "Exempt check-out",perlu_review AS "Needs review",NOT is_date_final AS "Provisional" FROM mart_kehadiran.fact_kehadiran_daily WHERE {where} AND active_employee_days=1 ORDER BY tanggal,pegawai_id_sumber LIMIT 1000'''
  label='Employee daily records — up to 1,000 rows'
 else:
  sums=','.join(f'SUM({m}) AS "{label}"' for m,label in metrics)
  query=f'''SELECT departemen_id_sumber AS "Department ID",COALESCE(MAX(nama_departemen),'Department '||departemen_id_sumber::text,'UNKNOWN') AS "Department",{sums},ROUND(100.0*SUM(checkin_days)/NULLIF(SUM(active_employee_days),0),2) AS "Check-in %",ROUND(100.0*SUM(checkout_days)/NULLIF(SUM(active_employee_days),0),2) AS "Check-out %",ROUND(100.0*SUM(required_checkin_present_days)/NULLIF(SUM(required_checkin_days),0),2) AS "Required check-in %",ROUND(100.0*SUM(required_checkout_present_days)/NULLIF(SUM(required_checkout_days),0),2) AS "Required check-out %",BOOL_OR(is_provisional) AS "Provisional" FROM serving.v_kehadiran_departemen_harian WHERE {where} GROUP BY departemen_id_sumber ORDER BY departemen_id_sumber NULLS LAST LIMIT 5000'''
  label='Department summary — employee-days'
 id_columns = ['Employee ID', 'Department ID'] if role == 'Operational' else ['Department ID']
 id_settings = {'column_settings': {json.dumps(['name', column], separators=(',', ':')): {'number_style': 'decimal', 'number_separators': '.', 'decimals': 0} for column in id_columns}}
 specs.append((label,query,'table',id_settings,12,7))
 query=f'''SELECT CASE WHEN COUNT(*)=0 THEN 'NO DATA' WHEN BOOL_OR(is_provisional) THEN 'PROVISIONAL' ELSE 'FINAL' END AS "Status",MIN(tanggal) AS "First available date",MAX(tanggal) AS "Last available date",COUNT(DISTINCT tanggal) AS "Available dates",CAST({{{{end_date}}}} AS date)-CAST({{{{start_date}}}} AS date)+1 AS "Requested dates",BOOL_AND(is_data_complete) AS "Published data complete",MIN(refreshed_at) AT TIME ZONE 'Asia/Jakarta' AS "Oldest refresh (Jakarta)",MAX(refreshed_at) AT TIME ZONE 'Asia/Jakarta' AS "Latest refresh (Jakarta)" FROM serving.v_kehadiran_departemen_harian WHERE {where}'''
 specs.append(('Data coverage and publication status',query,'table',{},12,4))
 for i,(label,query,display,settings,w,h) in enumerate(specs):
  name=f'{role} | {label}'
  p={'name':name,'collection_id':collection['id'],'display':display,'description':'ATTENDANCE_DAILY_V1. Test data only. Period counts are employee-days. NULL means unavailable or undefined, not zero.','dataset_query':{'database':source['id'],'type':'native','native':{'query':query,'template-tags':tags}},'visualization_settings':settings}
  card=next((c for c in existing_cards if c['name']==name),None)
  card=api('PUT',f"/card/{card['id']}",p) if card else api('POST','/card',p)
  row=3+(i//3)*3 if i<6 else {6:9,7:14,8:21}[i]
  cards.append({'id':-(i+2),'card_id':card['id'],'row':row,'col':(i%3)*8 if i<6 else 0,'size_x':w*2,'size_y':h,'parameter_mappings':[{'parameter_id':k,'card_id':card['id'],'target':['variable',['template-tag',k]]} for k in tags],'visualization_settings':{'card.title':label}})
 cards.insert(0,{'id':-1,'card_id':None,'row':0,'col':0,'size_x':24,'size_y':3,'parameter_mappings':[],'visualization_settings':{'virtual_card':{'display':'text','visualization_settings':{},'dataset_query':{}},'text':'## TEST DATA — Provisional\nAvailable date: **30 October 2026**. Department names are unavailable; use source IDs. Multi-day counts mean **employee-days**. Missing dates are not zero. Only one date is loaded, so no historical trend can yet be assessed.'}})
 current = api('GET',f"/dashboard/{d['id']}").get('dashcards',[])
 for c in cards:
  old = next((x for x in current if x.get('card_id') == c['card_id']),None)
  if old: c['id']=old['id']
 api('PUT',f"/dashboard/{d['id']}",{'dashcards':cards})
 out[role]={'id':d['id'],'url':f"http://localhost:3101/dashboard/{d['id']}",'cards':[c['card_id'] for c in cards if c['card_id']]}
 print(role,out[role]['url'],flush=True)
(ROOT/'deploy/hybrid/dashboards/metabase-manifest.json').write_text(json.dumps(out,indent=2)+'\n')
