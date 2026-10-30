"""Initialize the local Metabase administrator and read-only connection, no content."""
import json
from pathlib import Path
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
env = dict(line.split('=', 1) for line in (ROOT / '.env.hybrid').read_text().splitlines() if line and not line.startswith('#'))
base = 'http://127.0.0.1:3101'
session = None

def api(path, payload=None, method=None):
    headers = {'Content-Type': 'application/json'}
    if session:
        headers['X-Metabase-Session'] = session
    request = urllib.request.Request(base + path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f'Metabase request {path} failed (HTTP {error.code}); response suppressed to protect credentials.') from None

properties = api('/api/session/properties')
if properties.get('setup-token'):
    api('/api/setup', {
        'token': properties['setup-token'],
        'user': {'first_name': 'Hybrid', 'last_name': 'Administrator', 'email': env['BI_ADMIN_EMAIL'], 'password': env['BI_ADMIN_PASSWORD']},
        'prefs': {'site_name': 'Hybrid prototype', 'allow_tracking': False},
    })
session = api('/api/session', {'username': env['BI_ADMIN_EMAIL'], 'password': env['BI_ADMIN_PASSWORD']})['id']
databases = api('/api/database')
rows = databases.get('data', []) if isinstance(databases, dict) else databases
existing = next((database for database in rows if database['name'] == 'Attendance mart (read only)'), None)
payload = {
    'name': 'Attendance mart (read only)', 'engine': 'postgres',
    'is_full_sync': False, 'is_on_demand': True, 'auto_run_queries': False,
    'details': {'host': 'epresensi-mart-postgres', 'port': 5432, 'dbname': env.get('MART_DATABASE', 'mart_bkd'), 'user': 'hybrid_metabase_reader', 'password': env['METABASE_MART_PASSWORD'], 'ssl': False, 'schema-filters-type': 'inclusion', 'schema-filters-patterns': 'serving,mart_kehadiran'},
}
if existing:
    api('/api/database/' + str(existing['id']), payload, method='PUT')
else:
    api('/api/database', payload)
print('Metabase read-only source configured for ' + payload['details']['dbname'])
