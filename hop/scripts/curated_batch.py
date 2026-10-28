#!/usr/bin/env python3
"""Prepare/execute/inspect a committed raw -> curated manifest using container psql.
No credentials, source connections, time-based watermarks, or raw mutations.
"""
import argparse
import re
import subprocess


def ids(value):
    if not value:
        return '{}'
    try:
        numbers = sorted(set(int(part) for part in value.split(',')))
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Use comma-separated integer IDs') from exc
    return '{' + ','.join(map(str, numbers)) + '}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enqueue', 'run', 'next', 'status'])
    parser.add_argument('--batch-id')
    parser.add_argument('--events', type=ids, default='')
    parser.add_argument('--leaves', type=ids, default='')
    parser.add_argument('--deleted-events', type=ids, default='')
    parser.add_argument('--deleted-leaves', type=ids, default='')
    parser.add_argument('--snapshot-today', action='store_true')
    parser.add_argument('--confirm-complete-employee-snapshot', action='store_true')
    parser.add_argument('--container', default='epresensi-staging-postgres')
    parser.add_argument('--database', default='staging_bkd')
    parser.add_argument('--user', default='admin_staging')
    args = parser.parse_args()
    if args.action != 'next' and not args.batch_id:
        parser.error('--batch-id required')
    if args.batch_id and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', args.batch_id):
        parser.error('batch-id must contain only 1-100 letters, digits, underscores or hyphens')
    if args.snapshot_today and not args.confirm_complete_employee_snapshot:
        parser.error('A population snapshot requires --confirm-complete-employee-snapshot')
    values = {
        'batch': args.batch_id or '', 'events': args.events, 'leaves': args.leaves,
        'deleted_events': args.deleted_events, 'deleted_leaves': args.deleted_leaves,
        'snapshot': str(args.snapshot_today).lower(),
        'complete': str(args.confirm_complete_employee_snapshot).lower(),
    }
    sql = {
        'enqueue': """SELECT etl_control.enqueue_curated_batch(
          :'batch', :'events'::integer[], :'leaves'::integer[],
          :'deleted_events'::integer[], :'deleted_leaves'::integer[],
          CASE WHEN :'snapshot'::boolean THEN (current_timestamp AT TIME ZONE 'Asia/Jakarta')::date END,
          :'complete'::boolean);""",
        'run': "SELECT etl_control.apply_curated_batch(:'batch');",
        'next': 'SELECT etl_control.apply_next_curated_batch();',
        'status': "SELECT row_to_json(b) FROM etl_control.curated_batch b WHERE batch_id=:'batch';",
    }[args.action]
    command = ['docker', 'exec', '-i', args.container, 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
               '-U', args.user, '-d', args.database]
    for key, value in values.items():
        command.extend(['-v', f'{key}={value}'])
    # SQL is passed via stdin so psql safely quotes variables using :'name'.
    # Never interpolate CLI values into shell text or SQL strings.
    return subprocess.run(command, input=sql + '\n', text=True, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
