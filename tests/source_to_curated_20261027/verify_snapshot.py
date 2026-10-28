#!/usr/bin/env python3
"""Compare frozen raw business columns against the source snapshot binary hashes."""
import hashlib,json
from run import P,DST,call,cols,quoted
report_path=P/'results_revision1.json' if (P/'results_revision1.json').exists() else P/'results.json'
report=json.loads(report_path.read_text())
results={}
for table,expected in report['snapshot_tables'].items():
 name='raw_'+table
 payload=call(DST,f'COPY (SELECT {quoted(cols(name))} FROM raw.{name} ORDER BY id) TO STDOUT WITH (FORMAT binary)',data=b'').stdout
 results[table]=hashlib.sha256(payload).hexdigest()==expected['source_binary_sha256']
 assert results[table],table
(P/('snapshot_validation_revision1.json' if report.get('revision') else 'snapshot_validation.json')).write_text(json.dumps(results,indent=2)+'\n')
print('All 11 snapshot tables match source business attributes exactly.')
