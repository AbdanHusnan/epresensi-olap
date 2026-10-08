"""Provision both dimensions in the existing Hop dev database and scoped accounts.

Run from repository root: .venv/bin/python scripts/setup_hop_departemen.py
Passwords are written only to ignored .env.hop, never to project metadata/logs.
"""
import os
import json
import secrets
from pathlib import Path

import psycopg
from psycopg import sql
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = dotenv_values(ROOT / '.env')
    secret_path = ROOT / '.env.hop'
    existing = dotenv_values(secret_path) if secret_path.exists() else {}
    values = {
        'HOP_SOURCE_HOST': 'epresensi-olap-postgres', 'HOP_SOURCE_PORT': '5432',
        'HOP_SOURCE_DB': 'dbabsen_restore', 'HOP_SOURCE_USER': 'hop_presensi_reader',
        'HOP_SOURCE_PASSWORD': existing.get('HOP_SOURCE_PASSWORD') or secrets.token_hex(24),
        'HOP_TARGET_HOST': 'epresensi-olap-postgres', 'HOP_TARGET_PORT': '5432',
        'HOP_TARGET_DB': 'epresensi_analytics_hop_dev', 'HOP_TARGET_USER': 'hop_presensi_writer',
        'HOP_TARGET_PASSWORD': existing.get('HOP_TARGET_PASSWORD') or secrets.token_hex(24),
    }
    def connect(db):
        return psycopg.connect(host=config['OLAP_HOST'], port=config['OLAP_PORT'],
                               user=config['OLAP_USER'], password=config['OLAP_PASSWORD'], dbname=db)

    with connect(values['HOP_TARGET_DB']) as c:
        for prefix in ('SOURCE', 'TARGET'):
            role = values[f'HOP_{prefix}_USER']
            found = c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone()
            if found and not existing:
                raise RuntimeError('Scoped account already exists but .env.hop is missing; refusing to reset it.')
            if not found:
                c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(
                    sql.Identifier(role), sql.Literal(values[f'HOP_{prefix}_PASSWORD'])))
        c.execute((ROOT / 'sql/hop/dev_dimensions.sql').read_text())
        c.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO hop_presensi_writer').format(sql.Identifier(values['HOP_TARGET_DB'])))
        c.execute('GRANT USAGE ON SCHEMA public, analytics TO hop_presensi_writer')
        c.execute('GRANT SELECT, INSERT, UPDATE ON public.dim_departemen, public.dim_pegawai TO hop_presensi_writer')
        c.execute('GRANT USAGE, SELECT ON SEQUENCE public.dim_departemen_departemen_key_seq, public.dim_pegawai_pegawai_key_seq TO hop_presensi_writer')
        c.execute('GRANT SELECT ON analytics.mart_attendance_department_daily TO hop_presensi_writer')
        c.execute('GRANT SELECT, INSERT ON analytics.mart_dirty_dates TO hop_presensi_writer')
        c.execute("ALTER ROLE hop_presensi_reader SET default_transaction_read_only = on")
    with connect('dbabsen_restore') as c:
        c.execute('GRANT CONNECT ON DATABASE dbabsen_restore TO hop_presensi_reader')
        c.execute('GRANT USAGE ON SCHEMA public TO hop_presensi_reader')
        c.execute('GRANT SELECT ON public.m_departemen, public.m_pegawai, public.m_previleges TO hop_presensi_reader')
    fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write('\n'.join(f'{k}={v}' for k, v in values.items()) + '\n')
    secret_path.chmod(0o600)
    env_path = ROOT / '.env.hop.json'
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump({'variables': [{'name': k, 'value': v,
                                 'description': 'Scoped Hop presensi connection'}
                                for k, v in values.items()]}, f)
    env_path.chmod(0o600)
    print('Ready: epresensi_analytics_hop_dev.public dimensions; scoped reader/writer; credentials saved in ignored .env.hop.')


if __name__ == '__main__':
    main()
