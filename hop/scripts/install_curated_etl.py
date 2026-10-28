#!/usr/bin/env python3
"""Install leave schema upgrade and ETL functions atomically, without raw writes."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def installation_sql():
    schema = (ROOT / 'sql/staging/20261028_curated_leave_exemptions.sql').read_text()
    etl = (ROOT / 'sql/staging/20261028_curated_incremental_etl.sql').read_text()
    # Retain exactly one transaction spanning schema and replacement functions.
    assert etl.count('\nBEGIN;\n') == 1 and etl.endswith('COMMIT;\n')
    etl = etl.replace('\nBEGIN;\n', '\n', 1).removesuffix('COMMIT;\n')
    return ("\\set ON_ERROR_STOP on\nBEGIN;\nSET LOCAL lock_timeout='5s';\n"
            + schema + '\n' + etl + '\nCOMMIT;\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    if args.database != 'staging_bkd' and not args.database.startswith('staging_bkd_'):
        parser.error('Only staging_bkd or explicitly named staging_bkd_* test databases are supported')
    subprocess.run(['docker', 'exec', '-i', 'epresensi-staging-postgres', 'psql',
                    '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'admin_staging', '-d', args.database],
                   input=installation_sql(), text=True, check=True)


if __name__ == '__main__':
    main()
