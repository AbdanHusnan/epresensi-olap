#!/usr/bin/env python3
"""Install downstream definitions only. Never bootstrap, invoke delivery, or run Hop."""
import argparse
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = (
    ('epresensi-staging-postgres', 'staging_bkd', 'sql/staging/20261028_mart_outbox.sql'),
    ('epresensi-mart-postgres', 'mart_bkd', 'sql/mart/20261028_mart_incremental_etl.sql'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply-definitions', action='store_true')
    args = parser.parse_args()
    for container, database, path in MIGRATIONS:
        sql = (ROOT / path).read_text()
        if not re.search(r'\nBEGIN;\n', sql) or not sql.endswith('COMMIT;\n'):
            raise ValueError(f'Missing migration transaction: {path}')
        print(f'{container}/{database}: {path}', flush=True)
        if args.apply_definitions:
            # Database/user arguments never enter SQL. Secrets remain in container env.
            subprocess.run(
                ['docker', 'exec', '-i', container, 'sh', '-c',
                 'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"',
                 'psql', database], input=sql, text=True, check=True)
    print('Definitions only. Bootstrap, capture activation and all loads remain unexecuted.')


if __name__ == '__main__':
    main()
