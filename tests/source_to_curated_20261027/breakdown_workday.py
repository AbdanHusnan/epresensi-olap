import json
from run import P,DST,q,obj,call
q(DST,(P/'breakdown_workday.sql').read_text())
sql='SELECT * FROM test_control.workday_missing_regular_breakdown ORDER BY reason,active_employees DESC,departemen_id'
data=call(DST,f'COPY ({sql}) TO STDOUT WITH (FORMAT csv,HEADER true)',data=b'').stdout
(P/'breakdown_departemen.csv').write_bytes(data)
summary=obj(DST,"""SELECT json_agg(x ORDER BY reason) FROM (
SELECT reason,count(*) AS departments,sum(active_employees) AS employees,
sum(active_employees) FILTER(WHERE active_shift>0) AS with_direct_active_shift,
sum(active_employees) FILTER(WHERE parent_regular_tuesday_count>0) AS with_parent_regular,
sum(active_employees) FILTER(WHERE nearest_regular_ancestor_id IS NOT NULL) AS with_any_ancestor_regular,
sum(active_employees) FILTER(WHERE nearest_regular_ancestor_id IS NULL) AS without_ancestor_regular
FROM test_control.workday_missing_regular_breakdown GROUP BY reason) x""")
(P/'breakdown_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
print(q(DST,'SELECT reason,departemen_id,nama_departemen,active_employees,parent_regular_tuesday_count FROM test_control.workday_missing_regular_breakdown ORDER BY active_employees DESC LIMIT 12'))
