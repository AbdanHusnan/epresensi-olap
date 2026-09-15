"""Preview or replace source records, preserving the existing PostgreSQL schema."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from psycopg import sql

from etl.connectors.oltp import get_oltp_connection
from etl.dummy.database import backup_database, confirm_database

SOURCE_TABLES = (
    'm_departemen', 'm_pegawai', 'm_user', 'm_shift', 'm_jadwal',
    'm_tipe_ijin', 'm_jenis_ijin', 'm_hari_libur', 't_libur_shift',
    't_perizinan', 't_checkinout',
)


# Schema-specific master required by the application default m_pegawai.status=1.
# Keep it outside SOURCE_TABLES so existing version-2 artifacts remain valid.
REFERENCE_ROWS = {'m_previleges': [{'id': 1, 'previleges': 'Pegawai Dummy'}]}


def reference_rows(tables):
    return {table: rows for table, rows in REFERENCE_ROWS.items() if table in tables}


def read_dataset(path):
    """Validate the completion trailer so interrupted generation cannot be loaded."""
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        header = json.loads(next(stream))
        if header.get('format_version') != 2 or header.get('synthetic') is not True:
            raise ValueError('Expected a version 2 synthetic dataset')
        counts = Counter()
        complete = False
        for line in stream:
            if complete:
                raise ValueError('Unexpected data after completion trailer')
            batch = json.loads(line)
            if batch.get('complete'):
                if dict(counts) != batch['counts'] or counts['m_pegawai'] != header['employees']:
                    raise ValueError('Dataset counts do not reconcile')
                complete = True
                continue
            table, rows = batch['table'], batch['rows']
            if table not in SOURCE_TABLES:
                raise ValueError(f'Unsupported source table: {table}')
            counts[table] += len(rows)
            yield table, rows
        if not complete or set(counts) != set(SOURCE_TABLES):
            raise ValueError('Dataset is incomplete')


def copy_rows(conn, table, rows):
    if not rows:
        return
    columns = list(rows[0])
    statement = sql.SQL('COPY {} ({}) FROM STDIN').format(
        sql.Identifier('public', table), sql.SQL(', ').join(map(sql.Identifier, columns)))
    with conn.cursor() as cursor, cursor.copy(statement) as copy:
        for row in rows:
            if set(row) != set(columns):
                raise ValueError(f'Inconsistent columns in {table}')
            copy.write_row([row[c] for c in columns])


def reset_source(conn, path, tables):
    """Caller owns one transaction. Foreign keys stay enabled; no CASCADE."""
    conn.execute("SET LOCAL lock_timeout = '10s'")
    conn.execute('SET LOCAL search_path TO public')
    conn.execute(sql.SQL('TRUNCATE {} RESTART IDENTITY').format(sql.SQL(', ').join(
        sql.Identifier('public', table) for table in tables)))
    counts = Counter()
    for table, rows in reference_rows(tables).items():
        copy_rows(conn, table, rows)
        counts[table] = len(rows)
    for table, rows in read_dataset(path):
        copy_rows(conn, table, rows)
        counts[table] += len(rows)
        if table == 't_checkinout':
            print(f"Loaded source for {counts['m_pegawai']:,} employees", flush=True)
    # Explicit synthetic IDs must not collide with the next application insert.
    for table in counts:
        sequence = conn.execute('SELECT pg_get_serial_sequence(%s, %s)', (f'public.{table}', 'id')).fetchone()[0]
        if sequence:
            schema, name = conn.execute('SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=%s::regclass', (sequence,)).fetchone()
            next_id = conn.execute(sql.SQL('SELECT coalesce(max(id), 0) + 1 FROM {}').format(sql.Identifier('public', table))).fetchone()[0]
            conn.execute(sql.SQL('ALTER SEQUENCE {} RESTART WITH {}').format(sql.Identifier(schema, name), sql.Literal(next_id)))
    for table in counts:
        actual = conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier('public', table))).fetchone()[0]
        if actual != counts[table]:
            raise ValueError(f'Row-count mismatch for {table}')
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-db')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--all-public-records', action='store_true',
                        help='Clear records in ALL public source tables, including old application/log records')
    args = parser.parse_args()
    counts = Counter()
    for table, rows in read_dataset(args.dataset):
        counts[table] += len(rows)
    with get_oltp_connection() as conn:
        if not args.apply:
            conn.execute('SET TRANSACTION READ ONLY')
        tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
        if not set(SOURCE_TABLES) <= set(tables):
            raise ValueError('Source database is missing required tables; schema is not created by this command')
        counts.update({table: len(rows) for table, rows in reference_rows(tables).items()})
        print(json.dumps({'database': conn.info.dbname, 'tables_to_clear': tables,
                          'replacement_rows': counts}, indent=2))
        if not args.apply:
            print('Preview only. No records changed.')
            return
        if not args.all_public_records:
            parser.error('Replacing this source requires --all-public-records; review the listed tables first')
        confirm_database(conn, args.confirm_db)
        backup_database(conn, 'OLTP', args.backup)
        reset_source(conn, args.dataset, tables)
    print('Source replacement committed. Run the OLAP initial load next.')


if __name__ == '__main__':
    main()
