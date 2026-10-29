"""Smoke-check the environment, without querying business records."""
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
compose = ['docker', 'compose', '--env-file', str(ROOT / '.env.hybrid'), '-f', str(ROOT / 'docker-compose.hybrid.yml')]
subprocess.run(compose + ['config', '--quiet'], check=True)
for name, url in [('web', 'http://127.0.0.1:3100/api/health'), ('metabase', 'http://127.0.0.1:3101/api/health'), ('superset', 'http://127.0.0.1:3102/health')]:
    with urllib.request.urlopen(url, timeout=15) as response:
        assert response.status == 200, name
    print(f'{name}: HTTP health passed')
result = subprocess.run(compose + ['ps', '--format', 'json'], capture_output=True, text=True, check=True)
seen = set()
for line in result.stdout.splitlines():
    service = json.loads(line)
    seen.add(service['Service'])
    assert service['State'] == 'running', service['Service']
    assert service.get('Health') == 'healthy', service['Service']
    print(f"{service['Service']}: container healthy")
assert seen == {'web', 'metabase', 'superset', 'metadata', 'redis'}, seen
print('Environment smoke checks passed.')
