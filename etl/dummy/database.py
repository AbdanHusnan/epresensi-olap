"""Database safeguards shared by development reload commands."""

import os
import subprocess
from pathlib import Path

from psycopg import sql


def confirm_database(conn, expected):
    actual = conn.execute('SELECT current_database()').fetchone()[0]
    if not expected or expected != actual:
        raise ValueError(f'Write requires --confirm-db {actual}')
    return actual


def backup_database(conn, prefix, destination):
    """Require a successful full custom-format dump before replacing existing data."""
    if destination is None:
        raise ValueError('Write requires --backup PATH (a new PostgreSQL dump file)')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['PGPASSWORD'] = os.getenv(f'{prefix}_PASSWORD', '')
    command = [os.getenv('DUMMY_PG_DUMP', 'pg_dump'), '--format=custom', '--no-owner', '--no-acl',
               '--host', conn.info.host, '--port', str(conn.info.port),
               '--username', conn.info.user, '--dbname', conn.info.dbname]
    # Exclusive creation also prevents overwriting the only recovery copy.
    with destination.open('xb') as stream:
        os.chmod(destination, 0o600)
        subprocess.run(command, env=env, stdout=stream, check=True)
    return str(destination)


def table_counts(conn, tables):
    return {table: conn.execute(sql.SQL('SELECT count(*) FROM {}').format(
        sql.Identifier('public', table))).fetchone()[0] for table in tables}
