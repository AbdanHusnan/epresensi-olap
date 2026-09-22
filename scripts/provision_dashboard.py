"""Create local secrets, analytics views and a least-privilege OLAP login.

Run from repository root: python -m scripts.provision_dashboard --apply
No existing passwords are rotated. Secrets are never printed.
"""
import argparse
import os
from pathlib import Path
import secrets

from dotenv import dotenv_values
from psycopg import sql
from etl.connectors.olap import get_olap_connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.apply:
        print('Preview: create .env.dashboard if absent; provision dashboard_reader and two analytics views.')
        return
    path = Path('.env.dashboard')
    if not path.exists():
        base = dotenv_values('.env')
        values = {
            'SUPERSET_SECRET_KEY': secrets.token_urlsafe(64),
            'SUPERSET_METADATA_PASSWORD': secrets.token_urlsafe(32),
            'SUPERSET_ADMIN_USERNAME': 'dashboard_admin',
            'SUPERSET_ADMIN_PASSWORD': secrets.token_urlsafe(24),
            'DASHBOARD_READER_PASSWORD': secrets.token_urlsafe(32),
            'DASHBOARD_OLAP_DB': base['OLAP_DB'],
        }
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(''.join(f'{k}={v}\n' for k, v in values.items()))
    values = dotenv_values(path)
    if path.stat().st_mode & 0o077:
        raise RuntimeError('.env.dashboard must be owner-only (chmod 600)')
    with get_olap_connection() as conn:
        conn.execute("SET LOCAL lock_timeout='5s'")
        conn.execute("SET LOCAL statement_timeout='30s'")
        if conn.execute('SELECT current_database()').fetchone()[0] != values['DASHBOARD_OLAP_DB']:
            raise RuntimeError('OLAP database does not match dashboard configuration')
        role = conn.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname='dashboard_reader'").fetchone()
        if role is None:
            conn.execute(sql.SQL('CREATE ROLE dashboard_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Literal(values['DASHBOARD_READER_PASSWORD'])))
        elif any(role):
            raise RuntimeError('Existing dashboard_reader has elevated privileges; inspect before continuing')
        conn.execute('ALTER ROLE dashboard_reader SET default_transaction_read_only=on')
        conn.execute("ALTER ROLE dashboard_reader SET statement_timeout='30s'")
        conn.execute('ALTER ROLE dashboard_reader SET search_path=analytics,pg_catalog')
        conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO dashboard_reader').format(sql.Identifier(values['DASHBOARD_OLAP_DB'])))
        conn.execute(Path('sql/dashboard/views.sql').read_text())
        conn.execute('GRANT USAGE ON SCHEMA analytics TO dashboard_reader')
        conn.execute('GRANT SELECT ON analytics.attendance_daily, analytics.attendance_department_daily TO dashboard_reader')
    print('Analytics views and dashboard_reader provisioned; existing passwords retained.')


if __name__ == '__main__':
    main()
