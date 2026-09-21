"""One advisory-lock key for cooperating warehouse writers."""

LOCK_ID = 718392046


def acquire_pipeline_lock(conn, *, transaction=False):
    function = 'pg_try_advisory_xact_lock' if transaction else 'pg_try_advisory_lock'
    if not conn.execute(f'SELECT {function}(%s)', (LOCK_ID,)).fetchone()[0]:
        raise RuntimeError('Another master, incremental, or initial-load run is active')
