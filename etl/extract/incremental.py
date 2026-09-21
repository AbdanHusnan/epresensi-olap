"""Read-only, bounded incremental queries.

Connections must use a consistent source snapshot. The iterators deliberately
use keyset pagination rather than ``fetchall()`` so a large delta does not have
to live in the Python process at once.
"""


def fetch_rows(conn, query, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        columns = [column.name for column in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def high_watermarks(conn):
    attendance = conn.execute('SELECT COALESCE(MAX(id), 0) FROM t_checkinout').fetchone()[0]
    permission = conn.execute(
        'SELECT MAX(COALESCE(updated_at, created_at)) FROM t_perizinan'
    ).fetchone()[0]
    return attendance, permission


def iter_checkinout_changes(conn, low_id, high_id, chunk_size):
    """Yield affected check-in/out rows in increasing-ID chunks."""
    if chunk_size <= 0:
        raise ValueError('chunk_size must be positive')
    cursor_id = low_id
    while cursor_id < high_id:
        rows = fetch_rows(conn, '''
            SELECT id, pegawai_id, created_at::date AS tanggal
            FROM t_checkinout
            WHERE id > %s AND id <= %s AND work_code = 1
            ORDER BY id
            LIMIT %s
        ''', (cursor_id, high_id, chunk_size))
        if not rows:
            return
        yield rows
        cursor_id = rows[-1]['id']


def iter_perizinan_changes(conn, lower_timestamp, upper_timestamp, chunk_size):
    """Yield permission changes in bounded chunks.

    Non-NULL timestamps use ``(timestamp, id)`` keyset pagination so rows with
    the same timestamp cannot be skipped. Rows without a timestamp are replayed
    by ID on every run because they cannot safely advance a timestamp watermark.
    """
    if chunk_size <= 0:
        raise ValueError('chunk_size must be positive')
    timestamp_expression = 'COALESCE(updated_at, created_at)'
    if upper_timestamp is not None:
        cursor_timestamp = cursor_id = None
        while True:
            clauses = [f'{timestamp_expression} IS NOT NULL',
                       f'{timestamp_expression} <= %s']
            params = [upper_timestamp]
            if lower_timestamp is not None:
                clauses.append(f'{timestamp_expression} >= %s')
                params.append(lower_timestamp)
            if cursor_timestamp is not None:
                clauses.append(f'({timestamp_expression}, id) > (%s, %s)')
                params.extend([cursor_timestamp, cursor_id])
            params.append(chunk_size)
            rows = fetch_rows(conn, f'''
                SELECT * FROM t_perizinan
                WHERE {' AND '.join(clauses)}
                ORDER BY {timestamp_expression}, id
                LIMIT %s
            ''', tuple(params))
            if not rows:
                break
            yield rows
            cursor_timestamp = rows[-1]['updated_at'] or rows[-1]['created_at']
            cursor_id = rows[-1]['id']

    # NULL timestamps are replayed: without a timestamp they cannot be checkpointed.
    cursor_id = 0
    while True:
        rows = fetch_rows(conn, '''
            SELECT * FROM t_perizinan
            WHERE COALESCE(updated_at, created_at) IS NULL AND id > %s
            ORDER BY id
            LIMIT %s
        ''', (cursor_id, chunk_size))
        if not rows:
            return
        yield rows
        cursor_id = rows[-1]['id']
