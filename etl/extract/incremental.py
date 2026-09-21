"""Read-only incremental queries. Connections must use a consistent source snapshot."""


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


def checkinout_changes(conn, low_id, high_id):
    # Watermark includes all work codes, even when none of the events affect facts.
    return fetch_rows(conn, '''
        SELECT id, pegawai_id, created_at::date AS tanggal
        FROM t_checkinout
        WHERE id > %s AND id <= %s AND work_code = 1
        ORDER BY id
    ''', (low_id, high_id))


def perizinan_changes(conn, lower_timestamp, upper_timestamp):
    if lower_timestamp is None:
        return fetch_rows(conn, 'SELECT * FROM t_perizinan ORDER BY id')
    # NULL timestamps are replayed: without a timestamp they cannot be checkpointed.
    return fetch_rows(conn, '''
        SELECT * FROM t_perizinan
        WHERE COALESCE(updated_at, created_at) IS NULL
           OR (COALESCE(updated_at, created_at) >= %s
               AND COALESCE(updated_at, created_at) <= %s)
        ORDER BY id
    ''', (lower_timestamp, upper_timestamp))
