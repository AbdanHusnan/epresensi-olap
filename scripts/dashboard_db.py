"""Database connection and writer coordination for dashboard utilities."""
import os

import psycopg
from dotenv import load_dotenv


load_dotenv()


def get_olap_connection():
    return psycopg.connect(
        host=os.getenv("OLAP_HOST"),
        port=os.getenv("OLAP_PORT"),
        dbname=os.getenv("OLAP_DB"),
        user=os.getenv("OLAP_USER"),
        password=os.getenv("OLAP_PASSWORD"),
    )



LOCK_ID = 718392046


def acquire_pipeline_lock(conn, *, transaction=False):
    function = 'pg_try_advisory_xact_lock' if transaction else 'pg_try_advisory_lock'
    if not conn.execute(f'SELECT {function}(%s)', (LOCK_ID,)).fetchone()[0]:
        raise RuntimeError('Another warehouse writer is active')
