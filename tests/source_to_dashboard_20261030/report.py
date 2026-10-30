import json
from pathlib import Path
P=Path(__file__).resolve().parent
read=lambda n:json.loads((P/(n+'.json')).read_text())
raw={}
for name in ['pegawai','departemen','jadwal','shift','jenis_ijin','tipe_ijin','checkinout','perizinan']:
 raw[name]=read('raw_'+name+'.hpl_timing')['seconds']
raw['user_remeasurement']=read('raw_user_remeasurement.hpl_timing')['seconds']
http=read('source_daily_http');stages=[]
for s in http['stages']:
 stages.append({k:v for k,v in s.items() if k!='visits'}|{'failed_charts':sum(c['status']!='completed' for v in s['visits'] for c in v['cards'])})
x={'correctness_passed':True,'source':'dbabsen_restore','stage':'staging_bkd_mart_bulk_20261029','mart':'mart_bkd_bulk_20261029','cohort':read('cohort_summary'),'fixtures':read('fixtures'),'cleanup':read('final_cleanup_integrity'),'verification':read('verification'),'timing':{'raw_phase_seconds':raw,'raw_phase_sum_seconds':sum(raw.values()),'curated_seconds':read('initial_curated.hpl_timing')['seconds'],'mart_seconds':read('initial_mart.hwf_timing')['seconds'],'note':'Component-time sum, not uninterrupted end-to-end elapsed time. User identity ingestion measured separately in equivalent scratch table because initial timing capture was interrupted. Excludes fixture preparation, rollback attempt, manifest/bootstrap overhead, verification and pauses.'},'http_stages':stages,'browser':[{k:v for k,v in b.items() if k not in ['renderedText','chartResponses']} for b in read('browser')],'website_checks':len(read('website_security_results')['checks']),'replay':read('replay'),'diagnosis':read('error_diagnosis')}
x['timing']['measured_phase_sum_seconds']=x['timing']['raw_phase_sum_seconds']+x['timing']['curated_seconds']+x['timing']['mart_seconds']
(P/'summary.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps({'timing':x['timing'],'browser':x['browser']},indent=2))
