"""Chunked incremental attendance/leave ETL; defaults to a read-only preview."""

import argparse
import json
from datetime import timedelta

from etl.connectors.oltp import get_oltp_connection
from etl.connectors.olap import get_olap_connection
from etl.control.checkpoint import get_pipeline_state, upsert_pipeline_state
from etl.control.run_log import start_run, finish_run_success, finish_run_failed
from etl.control.locking import acquire_pipeline_lock
from etl.extract.incremental import (
    fetch_rows, high_watermarks, iter_checkinout_changes, iter_perizinan_changes,
)
from etl.extract.fact_perizinan.extract_reference import (
    extract_pegawai_reference, extract_jenis_izin_reference,
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


def _recompute_and_load(source, target, keys, batch_size, available, apply, report):
    """Recompute bounded employee-day batches and validate their leave reference."""
    for facts in iter_recomputed_employee_days(source, target, keys, batch_size):
        required = {row['perizinan_id'] for row in facts if row['perizinan_id'] is not None}
        missing = required - available.keys()
        if missing:
            available.update({row['perizinan_id']: row for row in fetch_rows(target,
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


def run_incremental_fact_pipeline(source, target, *, apply=False,
                                  overlap_minutes=5, batch_size=1000,
                                  chunk_size=1000, reconcile=False):
    """Process a fixed source snapshot in bounded chunks; caller owns transaction.

    The source high watermarks are captured once. Each delta chunk is transformed
    and loaded before the following one is read, while both checkpoint updates are
    still committed atomically only after every chunk succeeds.
    """
    if overlap_minutes < 0 or batch_size <= 0 or chunk_size <= 0:
        raise ValueError('overlap_minutes must be nonnegative and batch/chunk sizes positive')
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
    report = {
        'dry_run': not apply, 'bootstrap': attendance_state is None,
        'reconcile': reconcile, 'chunk_size': chunk_size,
        'attendance_changes': 0, 'permission_rows_read': 0,
        'affected_employee_days': 0, 'attendance_inserted': 0,
        'attendance_updated': 0, 'checkinout_high_id': high_id,
        'perizinan_high_timestamp': high_time,
    }
    # Applying runs can reload permission references from OLAP for each event
    # chunk. Preview is read-only, so it keeps an overlay only for validation.
    preview_available = {}

    # Permissions run before event chunks: an event recomputation can then always
    # resolve a permission changed in the same source snapshot.
    references = None
    permission_lower = None if reconcile else lower_time
    for source_rows in iter_perizinan_changes(source, permission_lower, high_time, chunk_size):
        if references is None:
            references = (extract_pegawai_reference(target), extract_jenis_izin_reference(target))
        new_permissions = prepare_permissions(source_rows, target,
                                              pegawai_reference=references[0],
                                              jenis_izin_reference=references[1])
        report['permission_rows_read'] += len(source_rows)
        chunk_available = {row['perizinan_id']: row for row in new_permissions}
        old_permissions = []
        ids = [row['perizinan_id'] for row in new_permissions]
        for offset in range(0, len(ids), batch_size):
            old_permissions.extend(fetch_rows(target,
                'SELECT * FROM fact_perizinan WHERE perizinan_id = ANY(%s)',
                (ids[offset:offset + batch_size],)))
        if apply:
            load_fact_perizinan(target, new_permissions)
        keys = build_affected_employee_days([], old_permissions, new_permissions)
        report['affected_employee_days'] += len(keys)
        _recompute_and_load(source, target, keys, batch_size, chunk_available, apply, report)
        if not apply:
            preview_available.update(chunk_available)

    event_low_id = 0 if reconcile else last_id
    for events in iter_checkinout_changes(source, event_low_id, high_id, chunk_size):
        report['attendance_changes'] += len(events)
        keys = build_affected_employee_days(events, [], [])
        report['affected_employee_days'] += len(keys)
        _recompute_and_load(source, target, keys, batch_size,
                            preview_available if not apply else {}, apply, report)

    if apply:
        upsert_pipeline_state(target, ATTENDANCE_STATE, 't_checkinout', 'id',
                              last_watermark_id=high_id)
        upsert_pipeline_state(target, PERMISSION_STATE, 't_perizinan', 'timestamp',
                              last_watermark_timestamp=high_time)
    return report


def execute_pipeline(*, apply=False, overlap_minutes=5, batch_size=1000,
                     chunk_size=1000, reconcile=False):
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
            overlap_minutes=overlap_minutes, batch_size=batch_size,
            chunk_size=chunk_size, reconcile=reconcile)
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
    parser.add_argument('--batch-size', type=int, default=1000,
                        help='Maximum employee-days recomputed at once per date')
    parser.add_argument('--chunk-size', type=int, default=1000,
                        help='Maximum source delta rows extracted at once')
    args = parser.parse_args()
    if args.overlap_minutes < 0 or args.batch_size <= 0 or args.chunk_size <= 0:
        parser.error('overlap-minutes must be nonnegative and batch/chunk sizes positive')
    print(json.dumps(execute_pipeline(**vars(args)), indent=2, default=str))


if __name__ == '__main__':
    main()
