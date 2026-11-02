"""Add the analytical leave percentage chart to the existing Metabase dashboard.

Uses the existing dashboard filters and preserves all other dashboard cards.
No attendance data is modified.
"""
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
    'username': env['BI_ADMIN_EMAIL'], 'password': env['BI_ADMIN_PASSWORD']
})['id']
dashboard_id = int(env['METABASE_ANALYTICAL_DASHBOARD_ID'])
dashboard = api('GET', f'/dashboard/{dashboard_id}')
assert dashboard['name'] == 'Organization Attendance — TEST'
template_card = next(card['card'] for card in dashboard['dashcards']
                     if (card.get('card') or {}).get('name') == 'Organization | Pegawai Izin (employee-days)')
template_card = api('GET', f"/card/{template_card['id']}")
native = template_card['dataset_query'].get('native')
if native:
    available_tags = native['template-tags']
else:
    available_tags = {tag['name']: tag for tag in template_card['dataset_query']['stages'][0]['template-tags']}
parameter_ids = {parameter['id'] for parameter in dashboard['parameters']}
tag_names = [name for name in ('start_date', 'end_date', 'department')
             if name in parameter_ids and name in available_tags]
assert {'start_date', 'end_date', 'department'} <= set(tag_names)
query, _ = ranking(False)
name = 'Organization | Departments ranked by employees with leave'
all_cards = api('GET', '/card')
existing = next((card for card in all_cards if card['name'] == name), None)
payload = {
    'name': name,
    'collection_id': dashboard['collection_id'],
    'display': 'table',
    'description': ('Distinct active employees with at least one valid approved leave in the selected period, '
                    'divided by distinct active employees in the same department and period. '
                    'A person can appear in more than one department after a transfer. '
                    'Test data is provisional.'),
    'dataset_query': {'database': template_card['dataset_query']['database'], 'type': 'native',
                      'native': {'query': query, 'template-tags': {key: available_tags[key] for key in tag_names}}},
    'visualization_settings': {'table.pivot': False, 'table.column_widths': [52,440,110,145,155,90]},
}
card = api('PUT', f"/card/{existing['id']}", payload) if existing else api('POST', '/card', payload)
dashcards = dashboard['dashcards']
placed = next((item for item in dashcards if item.get('card_id') == card['id']), None)
if not placed:
    # Place the ranking before the existing department summary and shift cards below it.
    for item in dashcards:
        if item['row'] >= 14:
            item['row'] += 11
    dashcards.append({'id': -100, 'card_id': card['id'], 'row': 14, 'col': 0,
                      'size_x': 24, 'size_y': 11, 'visualization_settings': {}})
    placed = dashcards[-1]
previous_end = placed['row'] + placed['size_y']
height_delta = 11 - placed['size_y']
for item in dashcards:
    if item is not placed and item['row'] >= previous_end:
        item['row'] += height_delta
placed['size_y'] = 11
placed['parameter_mappings'] = [{'parameter_id': key, 'card_id': card['id'],
                                 'target': ['variable', ['template-tag', key]]} for key in tag_names]
placed['visualization_settings'] = {**placed.get('visualization_settings', {}),
                                    'card.title': 'Top 10 departments · employees with izin'}
api('PUT', f'/dashboard/{dashboard_id}', {'dashcards': dashcards})
print(f"Analytical leave ranking card {card['id']} configured on dashboard {dashboard_id}.")
