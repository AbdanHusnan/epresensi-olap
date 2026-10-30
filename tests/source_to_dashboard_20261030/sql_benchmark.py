import importlib.util,json,math
from pathlib import Path
OUT=Path(__file__).resolve().parent
import run as r
from types import SimpleNamespace
t=SimpleNamespace(data=lambda q,target=False:r.data(q,where='mart' if target else 'stage'),save=r.save)
queries={}
for label,start in [('day','2026-10-30')]:
    where=f"tanggal BETWEEN DATE '{start}' AND DATE '2026-10-30'"
    queries[label+'_institution']=f'SELECT * FROM serving.v_kehadiran_instansi_harian WHERE {where}'
    queries[label+'_departments']=f'SELECT departemen_id_sumber,SUM(active_employee_days),SUM(checkin_days),SUM(checkout_days) FROM serving.v_kehadiran_departemen_harian WHERE {where} GROUP BY departemen_id_sumber ORDER BY departemen_id_sumber'
    queries[label+'_trend']=f'SELECT tanggal,SUM(checkin_days),SUM(checkout_days) FROM serving.v_kehadiran_departemen_harian WHERE {where} GROUP BY tanggal ORDER BY tanggal'
    queries[label+'_manager_detail']=f'SELECT pegawai_id_sumber,tanggal,departemen_id_sumber,first_checkin_at,last_checkout_at FROM mart_kehadiran.fact_kehadiran_daily WHERE {where} AND departemen_id_sumber=30114 AND active_employee_days=1 ORDER BY tanggal,pegawai_id_sumber LIMIT 1000'
    queries[label+'_unscoped_detail']=f'SELECT pegawai_id_sumber,tanggal,departemen_id_sumber FROM mart_kehadiran.fact_kehadiran_daily WHERE {where} AND active_employee_days=1 ORDER BY tanggal,pegawai_id_sumber LIMIT 1000'
output={}
for name,query in queries.items():
    plans=[t.data("BEGIN READ ONLY;SET LOCAL statement_timeout='30s';EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) "+query+';COMMIT;',target=True)[0] for _ in range(10)]
    values=[p['Execution Time'] for p in plans];warm=sorted(values[1:])
    output[name]={'sql':query,'execution_ms':values,'first_ms':values[0],'warm_p50_ms':warm[len(warm)//2],'warm_p95_ms':warm[math.ceil(len(warm)*.95)-1],'first_plan':plans[0],'last_plan':plans[-1]}
    print(name,round(output[name]['warm_p95_ms'],3),'ms p95',flush=True)
t.save('sql_benchmark',output)
