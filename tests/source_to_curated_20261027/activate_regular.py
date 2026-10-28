#!/usr/bin/env python3
"""User-authorized revision: activate regular shifts in restore; preserve baseline."""
import hashlib,json
from run import P,SRC,DST,q,obj,call,cols,quoted,transform,fingerprint
if q(DST,"SELECT to_regclass('test_control.raw_shift_before_activation') IS NOT NULL")=='t':
 raise SystemExit('Revision already started/applied. Inspect audit before rerunning.')
q(DST,"""BEGIN;
CREATE TABLE test_control.raw_shift_before_activation AS TABLE raw.raw_shift;
CREATE TABLE test_control.workday_before_activation AS TABLE curated.cur_employee_workday;
CREATE TABLE test_control.daily_before_activation AS TABLE curated.cur_attendance_regular_daily;
CREATE TABLE test_control.run_before_activation AS TABLE test_control.run;
COMMIT;""")
q(SRC,"""BEGIN;
DO $$ BEGIN IF current_database()<>'dbabsen_restore' THEN RAISE EXCEPTION 'Wrong source'; END IF; END $$;
CREATE TABLE test_e2e_20261027.shift_activation_audit (
 shift_id integer PRIMARY KEY, before_row jsonb NOT NULL, changed_at timestamptz NOT NULL DEFAULT clock_timestamp());
INSERT INTO test_e2e_20261027.shift_activation_audit(shift_id,before_row)
SELECT id,to_jsonb(s) FROM public.m_shift s WHERE status IS FALSE AND nama ~* '(regular|reguler)';
UPDATE public.m_shift s SET status=true FROM test_e2e_20261027.shift_activation_audit a
WHERE s.id=a.shift_id AND s.status IS FALSE;
COMMIT;""")
n=int(q(SRC,'SELECT count(*) FROM test_e2e_20261027.shift_activation_audit'))
c=quoted(cols('raw_shift'))
payload=call(SRC,f'COPY (SELECT {c} FROM public.m_shift ORDER BY id) TO STDOUT WITH (FORMAT binary)',data=b'').stdout
q(DST,'CREATE TABLE raw.shift_activation_buffer (LIKE raw.raw_shift INCLUDING DEFAULTS)')
call(DST,f'COPY raw.shift_activation_buffer ({c}) FROM STDIN WITH (FORMAT binary)',data=payload)
# Require source and frozen snapshot to differ ONLY in the authorized status changes.
assert int(q(DST,"""SELECT count(*) FROM raw.shift_activation_buffer n
FULL JOIN test_control.raw_shift_before_activation o USING(id)
WHERE n.id IS NULL OR o.id IS NULL OR
(to_jsonb(n)-'status'-'extracted_at'-'pipeline_run_id') IS DISTINCT FROM
(to_jsonb(o)-'status'-'extracted_at'-'pipeline_run_id') OR
(n.status IS DISTINCT FROM o.status AND NOT(o.status IS FALSE AND n.status IS TRUE AND o.nama ~* '(regular|reguler)'))"""))==0
assert int(q(DST,'SELECT count(*) FROM raw.shift_activation_buffer n JOIN raw.raw_shift o USING(id) WHERE n.status IS DISTINCT FROM o.status'))==n
q(DST,"""BEGIN;
CREATE TABLE test_control.snapshot_revision(revision text PRIMARY KEY,business_date date,applied_at timestamptz,change_description text);
INSERT INTO test_control.snapshot_revision VALUES('activate_regular_v1','2026-10-27',clock_timestamp(),'User approved activating inactive regular/reguler shifts in restore');
UPDATE raw.raw_shift r SET status=n.status,extracted_at=n.extracted_at,pipeline_run_id='E2E_20261027_REGULAR_V1'
FROM raw.shift_activation_buffer n WHERE r.id=n.id AND r.status IS DISTINCT FROM n.status;
COMMIT;""")
q(DST,(P/'workday.sql').read_text());transform()
assert q(DST,'SELECT count(*) FROM curated.cur_employee_workday')=='125832'
assert int(q(DST,"SELECT count(*) FROM curated.cur_employee_workday n JOIN test_control.workday_before_activation o USING(pegawai_id,tanggal) WHERE o.is_expected_workday AND NOT n.is_expected_workday"))==0
report=json.loads((P/'results.json').read_text())
report['revision']='activate_regular_v1'
report['baseline_stages_note']='Stages are evidence from baseline; see revision checks for changed master.'
report['activated_shifts']=n
report['snapshot_tables']['shift']['source_binary_sha256']=hashlib.sha256(payload).hexdigest()
report['workday_summary']=obj(DST,"SELECT row_to_json(x) FROM (SELECT count(*) total,count(*) FILTER(WHERE is_employee_active) active,count(*) FILTER(WHERE is_expected_workday) expected,count(*) FILTER(WHERE is_employee_active AND NOT has_regular_schedule) active_without_regular FROM curated.cur_employee_workday) x")
report['revision_checks']={'only_authorized_status_changed':True,'no_previous_expected_workday_lost':True,'workday_count_unchanged':True}
(P/'results_revision1.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'activated':n,'workday':report['workday_summary']}))
