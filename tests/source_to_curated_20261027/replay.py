#!/usr/bin/env python3
"""Replay existing snapshot and events; no source writes or master refresh."""
import json
from run import P, DST, q, ingest, transform, fingerprint
before=fingerprint()
ingest()
transform()
assert before==fingerprint(),'Business result changed during identical replay'
result={'replay_passed':True,'daily_fingerprint':fingerprint(),
        'event_count':int(q(DST,'SELECT count(*) FROM curated.cur_event_attendance')),
        'workday_count':int(q(DST,'SELECT count(*) FROM curated.cur_employee_workday'))}
(P/'replay_results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
