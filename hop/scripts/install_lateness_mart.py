"""Install the additive lateness mart definitions; do not load data."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def installation_sql():
    migration = (ROOT / 'sql/mart/20261030_lateness_columns.sql').read_text()
    migration = migration.replace('\nBEGIN;\n', '\n', 1).removesuffix('COMMIT;\n')
    source = (ROOT / 'sql/mart/20261028_mart_incremental_etl.sql').read_text()
    start = source.index('CREATE FUNCTION etl_control.apply_mart_delivery(')
    end = source.index('\nREVOKE ALL ON FUNCTION etl_control.apply_mart_delivery', start)
    function = source[start:end].replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1)
    view = (ROOT / 'sql/mart/20261030_lateness_serving.sql').read_text()
    return ("\\set ON_ERROR_STOP on\nBEGIN;\nSET LOCAL lock_timeout='5s';\n"
            "SELECT pg_advisory_xact_lock(hashtext('attendance_daily_v1_apply'));\n"
            + migration + '\n' + function + '\n' + view + '\nCOMMIT;\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    if args.database != 'mart_bkd' and not args.database.startswith('mart_bkd_'):
        parser.error('Only mart_bkd or explicitly named mart_bkd_* databases are supported')
    subprocess.run(['docker', 'exec', '-i', 'epresensi-mart-postgres', 'sh', '-c',
                    'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"',
                    'psql', args.database], input=installation_sql(), text=True, check=True)


if __name__ == '__main__':
    main()
