"""Configure the analytical top-10 lateness chart on the existing dashboard."""
from pathlib import Path
import requests
from configure_test_runs import ranking

ROOT = Path(__file__).resolve().parents[3]
env = dict(line.split('=', 1) for line in (ROOT / '.env.hybrid').read_text().splitlines()
           if line and not line.startswith('#'))
session = requests.Session()
base = 'http://127.0.0.1:3101/api'


def api(method, path, payload=None):
    response = session.request(method, base + path, json=payload, timeout=120)
    if not response.ok:
        raise RuntimeError(f'Metabase {method} {path} failed with HTTP {response.status_code}')
    return response.json() if response.content else None


session.headers['X-Metabase-Session'] = api('POST', '/session', {
    'username': env['BI_ADMIN_EMAIL'], 'password': env['BI_ADMIN_PASSWORD']})['id']
dashboard_id = int(env['METABASE_ANALYTICAL_DASHBOARD_ID'])
dashboard = api('GET', f'/dashboard/{dashboard_id}')
assert dashboard['name'] == 'Organization Attendance — TEST'
template = next(c['card'] for c in dashboard['dashcards']
                if (c.get('card') or {}).get('name') == 'Organization | Pegawai Aktif (employee-days)')
template = api('GET', f"/card/{template['id']}")
native = template['dataset_query'].get('native')
available = native['template-tags'] if native else {t['name']: t for t in template['dataset_query']['stages'][0]['template-tags']}
parameter_ids = {p['id'] for p in dashboard['parameters']}
tags = [k for k in ('start_date', 'end_date', 'department') if k in parameter_ids and k in available]
assert {'start_date', 'end_date', 'department'} <= set(tags)
query, _ = ranking(True)
name = 'Organization | Departments ranked by first-shift lateness'
cards = api('GET', '/card')
old = next((c for c in cards if c['name'] == name), None)
card_payload = {'name': name, 'collection_id': dashboard['collection_id'], 'display': 'table',
 'description': ('Distinct employees late on their first recorded shift at least once, divided by distinct employees '
                 'assessed at least once in the selected department and period. Excused, unassessed and unknown '
                 'employee-days are excluded. Provisional test data; missing evidence is not on time.'),
 'dataset_query': {'database': template['dataset_query']['database'], 'type': 'native',
                   'native': {'query': query, 'template-tags': {k: available[k] for k in tags}}},
 'visualization_settings': {'table.pivot': False, 'table.column_widths': [52,440,110,145,155,90]}}
card = api('PUT', f"/card/{old['id']}", card_payload) if old else api('POST', '/card', card_payload)
dashcards = dashboard['dashcards']
placed = next((c for c in dashcards if c.get('card_id') == card['id']), None)
if not placed:
    row = next((c['row'] + c['size_y'] for c in dashcards
                if (c.get('card') or {}).get('name') == 'Organization | Departments ranked by employees with leave'), 23)
    for item in dashcards:
        if item['row'] >= row:
            item['row'] += 11
    placed = {'id': -101, 'card_id': card['id'], 'row': row, 'col': 0,
              'size_x': 24, 'size_y': 11, 'visualization_settings': {}}
    dashcards.append(placed)
previous_end = placed['row'] + placed['size_y']
height_delta = 11 - placed['size_y']
for item in dashcards:
    if item is not placed and item['row'] >= previous_end:
        item['row'] += height_delta
placed['size_y'] = 11
placed['parameter_mappings'] = [{'parameter_id': k, 'card_id': card['id'],
    'target': ['variable', ['template-tag', k]]} for k in tags]
placed['visualization_settings'] = {**placed.get('visualization_settings', {}),
    'card.title': 'Top 10 departments · first-shift lateness'}
dashcards = [c for c in dashcards if (c.get('card') or {}).get('name') != 'Organization | Lateness assessment coverage']
api('PUT', f'/dashboard/{dashboard_id}', {'dashcards': dashcards})
print(f"Analytical lateness chart card {card['id']} configured on dashboard {dashboard_id}.")
