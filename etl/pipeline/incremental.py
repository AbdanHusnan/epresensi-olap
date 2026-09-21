"""Incremental attendance/leave ETL; defaults to a read-only preview."""

import argparse
import json
from datetime import timedelta

from etl.connectors.oltp import get_oltp_connection
from etl.connectors.olap import get_olap_connection
from etl.control.checkpoint import get_pipeline_state, upsert_pipeline_state
from etl.control.run_log import start_run, finish_run_success, finish_run_failed
from etl.control.locking import LOCK_ID, acquire_pipeline_lock
from etl.extract.incremental import (
    fetch_rows, high_watermarks, checkinout_changes, perizinan_changes,
)
from etl.transform.incremental import (
    prepare_permissions, build_affected_employee_days, iter_recomputed_employee_days,
)
from etl.load.fact_perizinan.load_fact_perizinan import load_fact_perizinan
from etl.load.fact_kehadiran import load_fact_kehadiran


# Existing initial_load resets these names. Do not leave stale incremental states
# behind after a warehouse replacement.
ATTENDANCE_STATE = 'fact_kehadiran'
PERMISSION_STATE = 'fact_perizinan'
PIPELINE = 'incremental_facts'


def run_incremental_fact_pipeline(source, target, *, apply=False,
                                  overlap_minutes=5, batch_size=1000, reconcile=False):
    """Caller owns source snapshot and target transaction. Never commits here."""
    if overlap_minutes < 0 or batch_size <= 0:
        raise ValueError('overlap_minutes must be nonnegative and batch_size positive')
    attendance_state = get_pipeline_state(target, ATTENDANCE_STATE)
    permission_state = get_pipeline_state(target, PERMISSION_STATE)
    if bool(attendance_state) != bool(permission_state):
        raise ValueError('Incomplete checkpoint pair; restore both states before retrying')
    if attendance_state and (attendance_state[1:3] != ('t_checkinout', 'id') or
                             permission_state[1:3] != ('t_perizinan', 'timestamp')):
        raise ValueError('Incompatible checkpoint source/type')
    last_id = (attendance_state[4] or 0) if attendance_state else 0
    last_time = permission_state[3] if permission_state else None
    high_id, high_time = high_watermarks(source)
    if high_id < last_id or (last_time is not None and (high_time is None or high_time < last_time)):
        raise ValueError('Source watermark regressed; inspect source replacement/deletions')
    lower_time = last_time - timedelta(minutes=overlap_minutes) if last_time else None
    events = checkinout_changes(source, 0 if reconcile else last_id, high_id)
    changes = perizinan_changes(source, None if reconcile else lower_time, high_time)
    new_permissions = prepare_permissions(changes, target) if changes else []
    old_permissions = []
    ids = [r['perizinan_id'] for r in new_permissions]
    for offset in range(0, len(ids), batch_size):
        old_permissions.extend(fetch_rows(target,
            'SELECT * FROM fact_perizinan WHERE perizinan_id = ANY(%s)',
            (ids[offset:offset + batch_size],)))
    keys = build_affected_employee_days(events, old_permissions, new_permissions)
    report = {
        'dry_run': not apply, 'bootstrap': attendance_state is None,
        'reconcile': reconcile, 'attendance_changes': len(events),
        'permission_rows_read': len(changes), 'affected_employee_days': len(keys),
        'attendance_inserted': 0, 'attendance_updated': 0,
        'checkinout_high_id': high_id, 'perizinan_high_timestamp': high_time,
    }
    # Includes unchanged permissions needed by recompute, even in preview mode.
    available = {r['perizinan_id']: r for r in new_permissions}
    if apply:
        load_fact_perizinan(target, new_permissions)
    for facts in iter_recomputed_employee_days(source, target, keys, batch_size):
        required = {r['perizinan_id'] for r in facts if r['perizinan_id'] is not None}
        missing = required - available.keys()
        if missing:
            available.update({r['perizinan_id']: r for r in fetch_rows(target,
                'SELECT * FROM fact_perizinan WHERE perizinan_id = ANY(%s)', (list(missing),))})
        for row in facts:
            if row['perizinan_id'] is None:
                continue
            leave = available.get(row['perizinan_id'])
            if (leave is None or not leave['is_valid_leave'] or
                    leave['pegawai_id'] != row['pegawai_id'] or
                    not leave['tanggal_mulai'] <= row['tanggal'] <= leave['tanggal_selesai']):
                raise ValueError('Leave reference is missing/stale; run --reconcile')
        if apply:
            inserted, updated = load_fact_kehadiran(target, facts)
            report['attendance_inserted'] += inserted
            report['attendance_updated'] += updated
    if apply:
        upsert_pipeline_state(target, ATTENDANCE_STATE, 't_checkinout', 'id',
                              last_watermark_id=high_id)
        upsert_pipeline_state(target, PERMISSION_STATE, 't_perizinan', 'timestamp',
                              last_watermark_timestamp=high_time)
    return report


def execute_pipeline(*, apply=False, overlap_minutes=5, batch_size=1000, reconcile=False):
    """Persist failures separately; facts, SUCCESS, and both checkpoints commit together."""
    source = get_oltp_connection()
    target = None
    run_id = None
    try:
        target = get_olap_connection()
        source.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        source.execute('SET LOCAL search_path TO public')
        if not apply:
            target.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        acquire_pipeline_lock(target)
        if apply:
            run_id = start_run(target, PIPELINE)
            target.commit()
        target.execute('SET LOCAL search_path TO public')
        report = run_incremental_fact_pipeline(source, target, apply=apply,
            overlap_minutes=overlap_minutes, batch_size=batch_size, reconcile=reconcile)
        if apply:
            finish_run_success(target, run_id,
                rows_extracted=report['attendance_changes'] + report['permission_rows_read'],
                rows_inserted=report['attendance_inserted'], rows_updated=report['attendance_updated'])
            target.commit()
        else:
            target.rollback()
        return report
    except Exception as exc:
        if target is not None:
            target.rollback()
            if run_id is not None:
                finish_run_failed(target, run_id, str(exc))
                target.commit()
        raise
    finally:
        source.close()
        if target is not None:
            target.close()  # Also releases the session advisory lock.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--reconcile', action='store_true', help='Replay all existing source events and permissions')
    parser.add_argument('--overlap-minutes', type=int, default=5)
    parser.add_argument('--batch-size', type=int, default=1000)
    args = parser.parse_args()
    if args.overlap_minutes < 0 or args.batch_size <= 0:
        parser.error('overlap-minutes must be nonnegative and batch-size positive')
    print(json.dumps(execute_pipeline(**vars(args)), indent=2, default=str))


if __name__ == '__main__':
    main()
