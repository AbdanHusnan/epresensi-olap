"""Run inside the Superset container; writes only BI metadata, never mart data."""
import json
from superset.app import create_app
from superset import db
app=create_app()
from superset.connectors.sqla.models import SqlaTable, SqlMetric
from superset.models.core import Database
from superset.models.dashboard import Dashboard
from superset.models.slice import Slice
METRICS=[('active_employee_days','Pegawai Aktif'),('checkin_days','Absen Masuk'),('checkout_days','Absen Pulang'),('no_checkin_days','Tidak Absen Masuk'),('no_checkout_days','Tidak Absen Pulang'),('leave_days','Pegawai Izin')]
TIME='2026-10-30 : 2026-10-31'
def metric(expression,label):
 return {'expressionType':'SQL','sqlExpression':expression,'label':label,'optionName':label}
with app.app_context():
 admin=app.appbuilder.sm.find_user(username='admin')
 source=db.session.query(Database).filter_by(database_name='Attendance mart (read only)').one()
 assert 'mart_bkd_bulk_20261029' in source.sqlalchemy_uri_decrypted
 def dataset(name,sql):
  t=db.session.query(SqlaTable).filter_by(database_id=source.id,table_name=name).first()
  if not t:
   t=SqlaTable(table_name=name,database=source,sql=sql,owners=[admin]);db.session.add(t)
  t.sql=sql;t.main_dttm_col='reporting_timestamp';t.filter_select_enabled=True
  db.session.commit();t.fetch_metadata();db.session.commit()
  for c in t.columns:
   if c.column_name in ('tanggal','reporting_timestamp'):c.is_dttm=True
  return t
 summary=dataset('attendance_comparison_summary_test',"SELECT *, CAST(tanggal AS timestamp) AS reporting_timestamp, COALESCE(nama_departemen, 'Department ' || departemen_id_sumber::text, 'UNKNOWN') AS department_label, CASE WHEN is_provisional THEN 'PROVISIONAL' ELSE 'FINAL' END AS publication_status FROM serving.v_kehadiran_departemen_harian")
 detail=dataset('attendance_comparison_employees_test',"SELECT *, CAST(tanggal AS timestamp) AS reporting_timestamp, CASE WHEN NOT is_date_final OR perlu_review THEN 'PROVISIONAL' ELSE 'FINAL' END AS publication_status FROM mart_kehadiran.fact_kehadiran_daily WHERE active_employee_days=1")
 for name,label in METRICS:
  m=next((m for m in summary.metrics if m.metric_name==name),None)
  if m is None:m=SqlMetric(metric_name=name);summary.metrics.append(m)
  m.expression=f'SUM({name})';m.verbose_name=label;m.d3format=',.0f'
 db.session.commit()
 out={}
 for role in ['Operational','Organization']:
  title=f'{role} Attendance — TEST'; slug='attendance-'+role.lower()+'-test'
  dash=db.session.query(Dashboard).filter_by(slug=slug).first()
  if not dash:dash=Dashboard(slug=slug,owners=[admin]);db.session.add(dash)
  dash.dashboard_title=title;dash.published=True
  specs=[]
  for m,label in METRICS:
   specs.append((label+(' (employee-days)' if role=='Organization' else ''),summary,'big_number_total',{'metric':m,'subheader':'TEST • Provisional','y_axis_format':',.0f','header_font_size':0.35,'subheader_font_size':0.13},4,24))
  specs.append(('Daily attendance trend',summary,'echarts_timeseries_line',{'metrics':['checkin_days','checkout_days'],'groupby':[],'time_grain_sqla':'P1D','x_axis':'reporting_timestamp','show_legend':True,'show_value':True,'markerEnabled':True,'markerSize':7,'rich_tooltip':True,'x_axis_time_format':'%d %b','y_axis_format':',.0f'},12,38))
  if role=='Operational':
   settings={'query_mode':'raw','all_columns':['pegawai_id_sumber','tanggal','departemen_id_sumber','first_checkin_at','last_checkout_at','has_masuk','has_pulang','has_valid_leave','has_excused_checkin','has_excused_checkout','perlu_review','publication_status'],'order_by_cols':['["tanggal", true]','["pegawai_id_sumber", true]'],'server_pagination':True,'server_page_length':25,'page_length':25,'include_search':True}
   specs.append(('Employee daily records — up to 1,000 rows',detail,'table',settings,12,50))
  else:
   rates=[metric('100.0*SUM(checkin_days)/NULLIF(SUM(active_employee_days),0)','Check-in %'),metric('100.0*SUM(checkout_days)/NULLIF(SUM(active_employee_days),0)','Check-out %'),metric('100.0*SUM(required_checkin_present_days)/NULLIF(SUM(required_checkin_days),0)','Required check-in %'),metric('100.0*SUM(required_checkout_present_days)/NULLIF(SUM(required_checkout_days),0)','Required check-out %')]
   settings={'query_mode':'aggregate','row_limit':5000,'groupby':['departemen_id_sumber','department_label','publication_status'],'metrics':[m for m,l in METRICS]+rates,'order_by_cols':['["departemen_id_sumber", true]'],'timeseries_limit_metric':metric('MIN(departemen_id_sumber)','Department sort'),'order_desc':False,'page_length':25,'include_search':True,'column_config':{r['label']:{'d3NumberFormat':'.2f'} for r in rates}}
   specs.append(('Department summary — employee-days',summary,'table',settings,12,50))
  quality=[metric("CASE WHEN COUNT(*)=0 THEN 'NO DATA' WHEN BOOL_OR(is_provisional) THEN 'PROVISIONAL' ELSE 'FINAL' END",'Status'),metric('MIN(tanggal)','First available date'),metric('MAX(tanggal)','Last available date'),metric('COUNT(DISTINCT tanggal)','Available dates'),metric('BOOL_AND(is_data_complete)','Published data complete'),metric("MIN(refreshed_at) AT TIME ZONE 'Asia/Jakarta'",'Oldest refresh (Jakarta)'),metric("MAX(refreshed_at) AT TIME ZONE 'Asia/Jakarta'",'Latest refresh (Jakarta)')]
  specs.append(('Data coverage and publication status',summary,'table',{'query_mode':'aggregate','groupby':[],'metrics':quality,'page_length':10},12,28))
  charts=[]
  for label,t,viz,settings,w,h in specs:
   name=f'{role} | {label}'
   chart=db.session.query(Slice).filter_by(slice_name=name).first()
   if not chart:chart=Slice(slice_name=name,owners=[admin],datasource_type='table',datasource_id=t.id,datasource_name=t.table_name,viz_type=viz);db.session.add(chart)
   chart.datasource_id=t.id;chart.datasource_type='table';chart.datasource_name=t.table_name;chart.viz_type=viz;chart.cache_timeout=-1
   chart.description='ATTENDANCE_DAILY_V1. Test data only. Counts across dates are employee-days. GUI filters are not authorization.'
   base={'datasource':f'{t.id}__table','viz_type':viz,'granularity_sqla':'reporting_timestamp','time_range':TIME,'adhoc_filters':[],'row_limit':1000,'color_scheme':'supersetColors','extra_form_data':{},'show_cell_bars':False}
   base.update(settings);chart.params=json.dumps(base);db.session.flush();base['slice_id']=chart.id;chart.params=json.dumps(base);charts.append((chart,w,h))
  dash.slices=[c for c,w,h in charts];db.session.flush()
  pos={'DASHBOARD_VERSION_KEY':'v2','ROOT_ID':{'id':'ROOT_ID','type':'ROOT','children':['GRID_ID']},'GRID_ID':{'id':'GRID_ID','type':'GRID','children':[],'parents':['ROOT_ID']},'HEADER_ID':{'id':'HEADER_ID','type':'HEADER','meta':{'text':title}}}
  def addrow(rowid,children):
   pos['GRID_ID']['children'].append(rowid)
   pos[rowid]={'id':rowid,'type':'ROW','children':children,'parents':['ROOT_ID','GRID_ID'],'meta':{'background':'BACKGROUND_TRANSPARENT'}}
  addrow('ROW-NOTICE',['MARKDOWN-NOTICE'])
  pos['MARKDOWN-NOTICE']={'id':'MARKDOWN-NOTICE','type':'MARKDOWN','children':[],'parents':['ROOT_ID','GRID_ID','ROW-NOTICE'],'meta':{'width':12,'height':22,'code':'### TEST DATA — Provisional\nAvailable date: **30 October 2026** only. Missing department names use source IDs. Period totals are **employee-days**. Missing dates are not zero; compare selected range with available dates below. One date cannot establish a historical trend. GUI filters are preview controls, not authorization.'}}
  groups=[charts[:3],charts[3:6],charts[6:7],charts[7:8],charts[8:9]]
  for i,group in enumerate(groups):
   rid=f'ROW-{i}';ids=[f'CHART-{c.id}' for c,w,h in group];addrow(rid,ids)
   for c,w,h in group:pos[f'CHART-{c.id}']={'id':f'CHART-{c.id}','type':'CHART','children':[],'parents':['ROOT_ID','GRID_ID',rid],'meta':{'chartId':c.id,'sliceName':c.slice_name,'sliceNameOverride':c.slice_name.split(' | ',1)[-1],'width':w,'height':h}}
  scope={'rootPath':['ROOT_ID'],'excluded':[]}
  filters=[{'id':'NATIVE_FILTER-date','name':'Reporting period','filterType':'filter_time','type':'NATIVE_FILTER','targets':[{}],'defaultDataMask':{'extraFormData':{'time_range':TIME},'filterState':{'value':TIME}},'scope':scope,'controlValues':{},'cascadeParentIds':[]}, {'id':'NATIVE_FILTER-department','name':'Department source ID','filterType':'filter_select','type':'NATIVE_FILTER','targets':[{'datasetId':summary.id,'column':{'name':'departemen_id_sumber'}},{'datasetId':detail.id,'column':{'name':'departemen_id_sumber'}}],'defaultDataMask':{'extraFormData':{'filters':[{'col':'departemen_id_sumber','op':'IN','val':[30114]}]} if role=='Operational' else {},'filterState':{'value':[30114],'label':'30114'} if role=='Operational' else {}},'scope':scope,'controlValues':{'enableEmptyFilter':False,'multiSelect':False,'searchAllOptions':True,'inverseSelection':False},'cascadeParentIds':[]}]
  dash.position_json=json.dumps(pos);dash.json_metadata=json.dumps({'native_filter_configuration':filters,'color_scheme':'supersetColors','refresh_frequency':0,'cross_filters_enabled':False,'timed_refresh_immune_slices':[],'expanded_slices':{}})
  db.session.commit();out[role]={'id':dash.id,'url':f'http://localhost:3102/superset/dashboard/{slug}/','charts':[c.id for c,w,h in charts]}
 print('MANIFEST='+json.dumps(out))
