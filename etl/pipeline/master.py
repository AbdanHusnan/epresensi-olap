"""Phase 10: atomic dimension, incremental, and daily attendance orchestration."""

import argparse
import json
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from etl.connectors.oltp import get_oltp_connection
from etl.connectors.olap import get_olap_connection
from etl.control.run_log import start_run, finish_run_success, finish_run_failed
from etl.pipeline.initial_load import prepare_references, prepare_replacement, LOADERS
from etl.pipeline.incremental import run_incremental_fact_pipeline
from etl.control.locking import acquire_pipeline_lock
from etl.transform.calendar import transform_calendar

PIPELINE = 'master_orchestration'
DIMENSIONS = ('dim_departemen', 'dim_pegawai', 'dim_jadwal_kerja', 'dim_jenis_izin')
logger = logging.getLogger(__name__)


def run_master_pipeline(source, target, *, start_date, end_date, apply=False,
                        overlap_minutes=5, batch_size=1000, reconcile=False):
    """Never commit here. Preview validates source data without target writes.

    Incremental must see OLD permission coverage before the complete permission
    refresh; otherwise moved/revoked permissions can leave stale attendance.
    """
    if start_date > end_date or overlap_minutes < 0 or batch_size <= 0:
        raise ValueError('Invalid date range, overlap_minutes, or batch_size')
    report = {'dry_run': not apply, 'start_date': start_date, 'end_date': end_date,
              'stages': [], 'rows_inserted': 0, 'rows_updated': 0,
              'rows_prepared': 0, 'permission_rows_written': 0}
    stage = 'prepare_references'

    def record(name, count, result=(0, 0)):
        inserted, updated = result
        report['rows_prepared'] += count
        report['rows_inserted'] += inserted
        report['rows_updated'] += updated
        detail = dict(stage=name, rows_prepared=count, inserted=inserted, updated=updated)
        report['stages'].append(detail)
        logger.info('%s', json.dumps(detail))

    try:
        references = prepare_references(source)
        base, _, holidays = references
        for stage in DIMENSIONS:
            rows = base[stage]
            result = LOADERS[stage](target, rows) if apply else (0, 0)
            record(stage, len(rows), result)
        stage = 'dim_calendar'
        # Retain and refresh existing calendar coverage for historical corrections.
        bounds = target.execute('SELECT min(tanggal), max(tanggal) FROM dim_calendar').fetchone()
        calendar_start = min(start_date, bounds[0] or start_date)
        calendar_end = max(end_date, bounds[1] or end_date)
        for leave in base['fact_perizinan']:
            calendar_start = min(calendar_start, leave['tanggal_mulai'])
            calendar_end = max(calendar_end, leave['tanggal_selesai'])
        calendar = transform_calendar(holidays, calendar_start, calendar_end)
        record(stage, len(calendar), LOADERS[stage](target, calendar) if apply else (0, 0))

        stage = 'incremental_facts'
        if apply:
            delta = run_incremental_fact_pipeline(source, target, apply=True,
                overlap_minutes=overlap_minutes, batch_size=batch_size, reconcile=reconcile)
            report['incremental'] = delta
            record(stage, delta['attendance_changes'] + delta['permission_rows_read'],
                   (delta['attendance_inserted'], delta['attendance_updated']))
        else:
            report['incremental'] = {'status': 'not_executed',
                'reason': 'Read-only preview does not materialize refreshed dimensions; validate delta with incremental preview separately.'}

        stage = 'fact_perizinan'
        permissions = base[stage]
        if apply:
            report['permission_rows_written'] = LOADERS[stage](target, permissions)
        record(stage, len(permissions))
        current = start_date
        while current <= end_date:
            stage = f'fact_kehadiran:{current}'
            rows = prepare_replacement(source, current, current, references)['fact_kehadiran']
            record(stage, len(rows), LOADERS['fact_kehadiran'](target, rows) if apply else (0, 0))
            current += timedelta(days=1)
        return report
    except Exception as exc:
        raise RuntimeError(f'Master stage {stage} failed: {exc}') from exc


def execute_pipeline(*, start_date, end_date, apply=False, overlap_minutes=5,
                     batch_size=1000, reconcile=False):
    """One source snapshot; one target commit for data, checkpoints and SUCCESS."""
    if start_date > end_date or overlap_minutes < 0 or batch_size <= 0:
        raise ValueError('Invalid date range, overlap_minutes, or batch_size')
    source = target = None
    run_id = None
    try:
        source = get_oltp_connection()
        target = get_olap_connection()
        source.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        source.execute('SET LOCAL search_path TO public')
        if not apply:
            target.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        acquire_pipeline_lock(target)
        if apply:
            # Lock ownership proves older cooperative writers are no longer active.
            target.execute("""UPDATE etl_control.pipeline_runs
                SET status = 'FAILED', finished_at = CURRENT_TIMESTAMP,
                    error_message = 'Interrupted run; transaction rolled back. Retry from committed checkpoints.'
                WHERE status = 'RUNNING' AND pipeline_name = ANY(%s)""",
                ([PIPELINE, 'incremental_facts'],))
            run_id = start_run(target, PIPELINE)
            target.commit()
        target.execute('SET LOCAL search_path TO public')
        logger.info('Master run_id=%s apply=%s period=%s..%s reconcile=%s',
                    run_id, apply, start_date, end_date, reconcile)
        report = run_master_pipeline(source, target, start_date=start_date, end_date=end_date,
            apply=apply, overlap_minutes=overlap_minutes, batch_size=batch_size, reconcile=reconcile)
        report['run_id'] = run_id
        if apply:
            finish_run_success(target, run_id, rows_extracted=report['rows_prepared'],
                               rows_inserted=report['rows_inserted'], rows_updated=report['rows_updated'])
            target.commit()
        else:
            target.rollback()
        return report
    except BaseException as exc:
        if target is not None:
            try:
                target.rollback()
                if run_id is not None:
                    finish_run_failed(target, run_id, str(exc) or type(exc).__name__)
                    target.commit()
            except Exception:
                logger.exception('Could not persist FAILED for run %s; original failure follows', run_id)
        raise
    finally:
        if source is not None:
            source.close()
        if target is not None:
            target.close()  # Releases session lock even after rollback.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-date', type=date.fromisoformat)
    parser.add_argument('--end-date', type=date.fromisoformat)
    parser.add_argument('--recent-days', type=int,
                        help='Include today and N-1 previous days in Asia/Jakarta')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--reconcile', action='store_true')
    parser.add_argument('--overlap-minutes', type=int, default=5)
    parser.add_argument('--batch-size', type=int, default=1000)
    args = parser.parse_args()
    recent_days = args.recent_days
    del args.recent_days
    if recent_days is not None:
        if recent_days <= 0 or args.start_date is not None or args.end_date is not None:
            parser.error('Use positive recent-days OR an explicit start-date/end-date pair')
        args.end_date = datetime.now(ZoneInfo('Asia/Jakarta')).date()
        args.start_date = args.end_date - timedelta(days=recent_days - 1)
    elif args.start_date is None or args.end_date is None:
        parser.error('Provide start-date and end-date, or recent-days')
    if args.start_date > args.end_date or args.overlap_minutes < 0 or args.batch_size <= 0:
        parser.error('Invalid date range, overlap-minutes, or batch-size')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    print(json.dumps(execute_pipeline(**vars(args)), indent=2, default=str))


if __name__ == '__main__':
    main()
