"""Build a compact machine-readable summary from retained test evidence."""
import json,re
from pathlib import Path
P=Path(__file__).resolve().parent
read=lambda n:json.loads((P/(n+'.json')).read_text())
ramps=[]
for n in [10000,40000,82000]:
 f=read(f'ramp_{n}_fixture');h=read(f'ramp_{n}_hop')
 internal=float(re.search(r'Workflow duration : ([0-9.]+) seconds',(P/f'ramp_{n}.log').read_text()).group(1))
 ramps.append({**f,'hop_wall_seconds':h['seconds'],'workflow_seconds':internal,'rows_per_hop_second':f['inserted']/h['seconds']})
stages=[]
for name in ['daily_82000','five_user_repeat','ten_user_warm']:
 for stage in read(name+'_http')['stages']:
  stages.append({'run':name,**{k:v for k,v in stage.items() if k!='visits'},'failed_charts':sum(c['status']!='completed' for v in stage['visits'] for c in v['cards']),'cache_status_unreported':sum(c.get('cached') is None for v in stage['visits'] for c in v['cards'])})
resources=[json.loads(l) for l in (P/'resources.jsonl').read_text().splitlines()]
def mib(s):
 v,unit=re.match(r'([\d.]+)(\w+)',s).groups();return float(v)*{'B':1/1048576,'KiB':1/1024,'MiB':1,'GiB':1024}[unit]
peaks={}
for snapshot in resources:
 for c in snapshot['containers']:
  q=peaks.setdefault(c['Name'],{'memory_mib':0,'cpu_percent':0})
  q['memory_mib']=max(q['memory_mib'],mib(c['MemUsage'].split(' / ')[0]));q['cpu_percent']=max(q['cpu_percent'],float(c['CPUPerc'].rstrip('%')))
x={'target':'mart_bkd_bulk_20261029','source':'staging_bkd_mart_bulk_20261029','date':'2026-10-28','employees':82000,'facts':82000,'departments':757,'historical_load_performed':False,'correctness_passed':True,'ten_user_acceptance_passed':False,'ramps':ramps,'sum_fixture_seconds':sum(r['seconds'] for r in ramps),'sum_hop_wall_seconds':sum(r['hop_wall_seconds'] for r in ramps),'http_stages':stages,'browser':[{k:v for k,v in x.items() if k not in ['renderedText','chartResponses']} for x in read('browser')],'website_checks':len(read('website_security_results')['checks']),'reconciliation':read('final_reconciliation'),'resource_peaks_sampled':peaks,'storage':read('storage'),'failure_diagnosis':read('error_diagnosis')}
(P/'summary.json').write_text(json.dumps(x,indent=2)+'\n')
print(json.dumps({'ramps':ramps,'resource_peaks_sampled':peaks,'browser':x['browser']},indent=2))
