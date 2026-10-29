#!/usr/bin/env python3
"""Plan SQL with empty temporary relations. Never invoke a delivery function.
EXPLAIN only, never ANALYZE: business INSERT/UPDATE/DELETE statements are not executed.
"""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sql = (ROOT / 'sql/mart/20261028_mart_incremental_etl.sql').read_text()
body = sql.split('CREATE FUNCTION etl_control.apply_mart_delivery', 1)[1]
header = '''BEGIN;
CREATE TEMP TABLE mart_incoming(pegawai_id integer,tanggal date,operation text,payload jsonb);
CREATE TEMP TABLE mart_candidate(LIKE mart_kehadiran.fact_kehadiran_daily INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING CONSTRAINTS);
CREATE TEMP TABLE mart_changed(LIKE mart_kehadiran.fact_kehadiran_daily);
CREATE TEMP TABLE mart_dirty(tanggal date,departemen_key bigint);
'''
statements = []
consumed = 0
for match in re.finditer(r'\n (WITH missing AS \(|INSERT INTO |DELETE FROM |UPDATE )', body):
    start = match.start() + 2
    if start < consumed:
        continue
    end = body.index(';', start) + 1
    consumed = end
    stmt = body[start:end]
    for name, value in {
        'v_batch': "'VALIDATION_ONLY'", 'v_stream': "'00000000000000000000000000000000'",
        'v_seq': '1::bigint', 'p_delivery': "'{\"items\":[]}'::jsonb",
    }.items():
        stmt = re.sub(r'\b' + name + r'\b', value, stmt)
    statements.append('EXPLAIN (COSTS OFF) ' + stmt)
# Parse/plan the candidate comparison that determines changed business rows.
comparison = re.search(r'CREATE TEMP TABLE mart_changed ON COMMIT DROP AS\n(.*?);', body, re.S).group(1)
statements.append('EXPLAIN (COSTS OFF) ' + comparison + ';')
script = header + '\n'.join(statements) + '\nROLLBACK;\n'
result = subprocess.run(['docker', 'exec', '-i', 'epresensi-mart-postgres', 'sh', '-c',
                         'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d mart_bkd'],
                        input=script, text=True, capture_output=True)
(ROOT / 'tests/mart_pipeline_20261028/sql_plan_validation.txt').write_text(result.stdout + result.stderr)
if result.returncode:
    print(result.stderr)
    raise SystemExit(result.returncode)
print(f'PASS: {len(statements)} statements planned with EXPLAIN, no ANALYZE and no function invocation/load.')
