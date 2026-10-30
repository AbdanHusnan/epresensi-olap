"""Create local secrets once; never overwrite an existing environment file."""
import os
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / '.env.hybrid'
values = {'BI_ADMIN_EMAIL': 'admin@hybrid.local', 'MART_DATABASE': 'mart_bkd_bulk_20261029', 'DEMO_MANAGER_DEPARTMENT_ID': '30114', 'METABASE_ANALYTICAL_DASHBOARD_ID': '2', 'METABASE_OPERATIONAL_DASHBOARD_ID': '1'}
for key in ('METADATA_ADMIN_PASSWORD', 'METABASE_METADATA_PASSWORD', 'SUPERSET_METADATA_PASSWORD', 'SUPERSET_SECRET_KEY', 'SUPERSET_GUEST_TOKEN_SECRET', 'BI_ADMIN_PASSWORD', 'METABASE_MART_PASSWORD', 'SUPERSET_MART_PASSWORD', 'APP_SESSION_SECRET', 'METABASE_EMBEDDING_SECRET', 'DEMO_DIRECTOR_PASSWORD', 'DEMO_MANAGER_PASSWORD'):
    values[key] = secrets.token_hex(32)
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print('.env.hybrid already exists; preserved existing credentials.')
else:
    with os.fdopen(fd, 'w') as file:
        file.writelines(f'{key}={value}\n' for key, value in values.items())
    print('Created .env.hybrid (mode 0600).')
