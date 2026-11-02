"""Read-only website/embed checks for the November check-in-only checkpoint."""
import base64
import json
from pathlib import Path
import requests
import run as test

env = dict(line.split('=', 1) for line in (test.ROOT / '.env.hybrid').read_text().splitlines()
           if line and not line.startswith('#'))
APP = 'http://localhost:3100'
BI = 'http://localhost:3101'
METRICS = ['active_employee_days','checkin_days','checkout_days','no_checkin_days','no_checkout_days','leave_days']
manager_department = int(env['DEMO_MANAGER_DEPARTMENT_ID'])
results = []


def checked(response, label):
    test.require(response.ok, f'{label}: HTTP {response.status_code}')
    return response.json()


for role in ['director', 'manager']:
    dashboard_id = int(env['METABASE_ANALYTICAL_DASHBOARD_ID' if role == 'director' else 'METABASE_OPERATIONAL_DASHBOARD_ID'])
    session = requests.Session()
    checked(session.post(APP + '/api/auth/login', headers={'Origin': APP},
        json={'username': role, 'password': env['DEMO_' + role.upper() + '_PASSWORD']}, timeout=30), role + ' login')
    token = checked(session.post(APP + '/api/metabase-token', headers={'Origin': APP},
        json={'entityType': 'dashboard', 'entityId': dashboard_id}, timeout=30), role + ' token')['jwt']
    claims = json.loads(base64.urlsafe_b64decode(token.split('.')[1] + '==='))
    if role == 'manager':
        test.require(claims['params']['department'] == manager_department, 'Manager scope not locked')
    meta = checked(requests.get(BI + '/api/embed/dashboard/' + token, timeout=60), role + ' embed')
    filters = {'start_date': test.DAY, 'end_date': test.DAY}
    clause = '' if role == 'director' else f' AND departemen_id_sumber={manager_department}'
    expected = test.data('SELECT jsonb_build_array(' + ','.join('SUM(' + m + ')' for m in METRICS) +
                         ") FROM mart_kehadiran.fact_kehadiran_daily WHERE tanggal=DATE '2026-11-02'" + clause, target='mart')
    charts = []
    scalars = []
    for card in sorted([c for c in meta['dashcards'] if c.get('card_id')], key=lambda c: (c['row'], c['col'])):
        url = BI + f"/api/embed/dashboard/{token}/dashcard/{card['id']}/card/{card['card_id']}"
        result = checked(requests.get(url, params={'parameters': json.dumps(filters)}, timeout=120), role + ' card')
        test.require(result.get('status') == 'completed', role + ' card failed')
        rows = result['data']['rows']
        name = card['card']['name']
        if card['row'] in (3, 6) and card['card']['display'] == 'scalar':
            scalars.append(rows[0][0])
        if 'Departments ranked by first-shift lateness' in name:
            expected_rank = test.data("""SELECT jsonb_agg(jsonb_build_array(label,rate) ORDER BY rate DESC,label)
            FROM (SELECT COALESCE(MAX(d.nama_departemen),'Department '||c.dep::text,'UNKNOWN')||' ('||COALESCE(c.dep::text,'UNKNOWN')||')' label,
              ROUND(100.0*count(*) FILTER(WHERE c.expected_status='LATE')/NULLIF(count(*) FILTER(WHERE c.expected_status IN('LATE','ON_TIME')),0),2) rate
              FROM test_checkin.cohort c LEFT JOIN raw.raw_departemen d ON d.id=c.dep GROUP BY c.dep
              HAVING count(*) FILTER(WHERE c.expected_status IN('LATE','ON_TIME'))>0
              ORDER BY rate DESC,label LIMIT 10) x""")
            test.require(rows == expected_rank, 'Embedded top-10 lateness rank differs from independent fixture oracle')
        if role == 'manager' and 'Employee daily records' in name:
            test.require(all(row[3] == manager_department and row[6] is None for row in rows), 'Manager table scope or checkout mismatch')
            attack = requests.get(url, params={'parameters': json.dumps({**filters, 'department': 30187})}, timeout=60)
            test.require(attack.status_code in (400, 403), 'Manager department override accepted')
        charts.append({'id': card['card_id'], 'name': name, 'status': result['status'], 'rows': len(rows)})
    test.require(scalars == expected, role + ' KPI mismatch')
    test.require(expected[2] == 0, role + ' checkout KPI is not zero')
    results.append({'role': role, 'passed': True, 'metrics': expected, 'charts': charts})
    print(role, 'PASS:', len(charts), 'charts; checkout KPI 0', flush=True)
    session.post(APP + '/api/auth/logout', headers={'Origin': APP}, timeout=30)
test.save('http_verification', {'passed': True, 'date': test.DAY, 'roles': results})
