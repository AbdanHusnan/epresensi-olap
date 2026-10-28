#!/usr/bin/env python3
"""Run integration tests in a fixed disposable synthetic database, never source/raw live."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TEST_DB = 'staging_bkd_etl_v2_test_20261028'
BASE = ['docker', 'exec', 'epresensi-staging-postgres']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reset-synthetic', action='store_true',
                        help='Drop/recreate only the fixed synthetic test database')
    args = parser.parse_args()
    exists = subprocess.check_output(BASE + ['psql', '-X', '-U', 'admin_staging', '-d', 'postgres',
        '-Atc', f"SELECT count(*) FROM pg_database WHERE datname='{TEST_DB}'"], text=True).strip()
    if exists == '1':
        if not args.reset_synthetic:
            parser.error('Synthetic database exists; use --reset-synthetic to rerun')
        subprocess.run(BASE + ['dropdb', '-U', 'admin_staging', TEST_DB], check=True)
    subprocess.run(BASE + ['createdb', '-U', 'admin_staging', TEST_DB], check=True)
    ddl = subprocess.check_output(BASE + ['pg_dump', '-U', 'admin_staging', '-d', 'staging_bkd',
        '--schema-only', '--schema=raw', '--schema=curated', '--no-owner', '--no-privileges'])
    psql = ['docker', 'exec', '-i', 'epresensi-staging-postgres', 'psql', '-X', '-v',
            'ON_ERROR_STOP=1', '-U', 'admin_staging', '-d', TEST_DB]
    subprocess.run(psql, input=ddl + b'\nCREATE SCHEMA etl_control;\n' +
        (ROOT / 'sql/staging/20261028_curated_incremental_etl.sql').read_bytes(),
        stdout=subprocess.DEVNULL, check=True)
    with (ROOT / 'tests/curated_etl_v2/integration_results.txt').open('wb') as output:
        subprocess.run(psql, input=(ROOT / 'tests/curated_etl_v2/integration.sql').read_bytes(),
                       stdout=output, check=True)
    print('PASS: isolated raw-to-curated integration tests; no live business data loaded.')


if __name__ == '__main__':
    main()
