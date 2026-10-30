"""Provision only isolated reader roles. No attendance records or definitions change."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
env = dict(line.split('=', 1) for line in (ROOT / '.env.hybrid').read_text().splitlines() if line and not line.startswith('#'))
database = env.get('MART_DATABASE', 'mart_bkd')
if not database.replace('_', '').isalnum():
    raise SystemExit('Invalid MART_DATABASE')
statements = ['BEGIN;']
for engine in ('metabase', 'superset'):
    role = f'hybrid_{engine}_reader'
    password = env[f'{engine.upper()}_MART_PASSWORD'].replace("'", "''")
    statements.extend([
        f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN CREATE ROLE {role} LOGIN; END IF; END $$;",
        f"ALTER ROLE {role} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '{password}';",
        f'GRANT CONNECT ON DATABASE {database} TO {role};',
        f'GRANT USAGE ON SCHEMA serving, mart_kehadiran TO {role};',
        f'GRANT SELECT ON ALL TABLES IN SCHEMA serving, mart_kehadiran TO {role};',
        f'ALTER ROLE {role} SET default_transaction_read_only = on;',
        f"ALTER ROLE {role} SET statement_timeout = '30s';",
        f'ALTER ROLE {role} CONNECTION LIMIT 10;',
    ])
statements.append('COMMIT;')
# Credentials travel over stdin, not process arguments or printed output.
result = subprocess.run(['docker', 'exec', '-i', 'epresensi-mart-postgres', 'sh', '-c', 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d ' + database], input='\n'.join(statements), text=True, capture_output=True)
if result.returncode:
    raise SystemExit('Mart provisioning failed. Check database/container availability and schema names; secret-bearing SQL output is suppressed.')
print('Provisioned two dedicated read-only mart roles. Rerun after new tables/views are added.')
