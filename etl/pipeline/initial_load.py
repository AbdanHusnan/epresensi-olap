"""Validate a complete replacement, then atomically reset and load the existing OLAP schema."""

import argparse
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from psycopg import sql

from etl.connectors.oltp import get_oltp_connection
from etl.connectors.olap import get_olap_connection
from etl.control.run_log import start_run, finish_run_success
from etl.dummy.database import backup_database, confirm_database, table_counts
from etl.dummy.seed import copy_rows
from etl.pipeline.initial_load_preflight import check_requirements
from etl.extract.calendar import extract_hari_libur
from etl.extract.departemen import extract_departemen
from etl.extract.pegawai import extract_pegawai
from etl.extract.jadwal_kerja import extract_jadwal, extract_shift
from etl.extract.jenis_izin import extract_jenis_izin, extract_tipe_izin
from etl.extract.fact_perizinan.extract_perizinan import extract_perizinan
from etl.extract.fact_kehadiran import extract_attendance, extract_libur_shift
from etl.transform.calendar import transform_calendar
from etl.transform.departemen import transform_departemen
from etl.transform.pegawai import transform_pegawai
from etl.transform.jadwal_kerja import transform_jadwal_kerja
from etl.transform.jenis_izin import transform_jenis_izin
from etl.transform.fact_perizinan.normalize import normalize_perizinan_rows
from etl.transform.fact_perizinan.approval import apply_approval_rules
from etl.transform.fact_perizinan.dimensions import resolve_perizinan_dimensions_rows
from etl.transform.fact_perizinan.build_fact import build_fact_perizinan_rows
from etl.transform.fact_perizinan.daily_coverage import build_daily_leave_coverage
from etl.transform.fact_perizinan.final_validation import validate_fact_perizinan_rows
from etl.transform.fact_kehadiran.employee_day import build_employee_days
from etl.transform.fact_kehadiran.schedule import resolve_schedule, build_schedule_index
from etl.transform.fact_kehadiran.libur_shift import resolve_libur_shift
from etl.transform.fact_kehadiran.attendance import aggregate_attendance
from etl.transform.fact_kehadiran.assembler import assemble_fact_rows, project_fact_kehadiran_rows, validate_final_fact_rows
from etl.transform.fact_kehadiran.leave import attach_daily_leave_coverage
from etl.transform.fact_kehadiran.rules import apply_expected_workday_rule, apply_attendance_status_rule, apply_time_compliance_rule
from etl.transform.cross_fact_validation import (
    validate_fact_kehadiran_dimension_references, validate_fact_perizinan_dimension_references,
    validate_perizinan_reference_integrity, validate_fact_kehadiran_key_reconciliation,
)
from etl.load.calendar import load_calendar
from etl.load.departemen import load_departemen
from etl.load.pegawai import load_pegawai
from etl.load.jadwal_kerja import load_jadwal_kerja
from etl.load.jenis_izin import load_jenis_izin
from etl.load.fact_perizinan.load_fact_perizinan import load_fact_perizinan
from etl.load.fact_kehadiran import load_fact_kehadiran


LOADERS = {
    'dim_departemen': load_departemen, 'dim_pegawai': load_pegawai,
    'dim_calendar': load_calendar, 'dim_jadwal_kerja': load_jadwal_kerja,
    'dim_jenis_izin': load_jenis_izin, 'fact_perizinan': load_fact_perizinan,
    'fact_kehadiran': load_fact_kehadiran,
}
RESET_TABLES = (*LOADERS, 'analytical_user')
PIPELINES = ('departemen', 'pegawai', 'calendar', 'jadwal_kerja', 'jenis_izin',
             'fact_perizinan', 'fact_kehadiran', 'analytical_user')


def prepare_references(source):
    employees = extract_pegawai(source)
    if not employees:
        raise ValueError('Refusing an empty employee source')
    rows = {
        'dim_departemen': transform_departemen(extract_departemen(source)),
        'dim_pegawai': transform_pegawai(employees),
        'dim_jadwal_kerja': transform_jadwal_kerja(extract_jadwal(source), extract_shift(source)),
        'dim_jenis_izin': transform_jenis_izin(extract_jenis_izin(source), extract_tipe_izin(source)),
    }
    departments = {r['departemen_id'] for r in rows['dim_departemen']}
    for table in ('dim_pegawai', 'dim_jadwal_kerja'):
        if any(r['departemen_id'] not in departments for r in rows[table]):
            raise ValueError(f'{table} references unknown departments')
    build_schedule_index(rows['dim_jadwal_kerja'])
    if any(r['nama_tipe_izin'] is None for r in rows['dim_jenis_izin']):
        raise ValueError('Jenis izin references a missing or unnamed tipe izin')
    leave = resolve_perizinan_dimensions_rows(
        apply_approval_rules(normalize_perizinan_rows(extract_perizinan(source))),
        {r['pegawai_id']: r['departemen_id'] for r in rows['dim_pegawai']},
        {r['jenis_izin_id'] for r in rows['dim_jenis_izin']})
    rows['fact_perizinan'] = build_fact_perizinan_rows(leave)
    validate_fact_perizinan_rows(rows['fact_perizinan'])
    validate_fact_perizinan_dimension_references(rows['fact_perizinan'], rows['dim_pegawai'], rows['dim_departemen'], rows['dim_jenis_izin'])
    return rows, leave, extract_hari_libur(source)


def prepare_replacement(source, start_date, end_date, references=None):
    """Reuse existing business rules without writes; callers use one day per batch."""
    if start_date > end_date:
        raise ValueError('start_date must be on or before end_date')
    base, leave, holidays = references if references is not None else prepare_references(source)
    if len(base['dim_pegawai']) * ((end_date - start_date).days + 1) > 500000:
        raise ValueError('Use batches of at most 500,000 employee-days')
    rows = dict(base)
    rows['dim_calendar'] = transform_calendar(holidays, start_date, end_date)
    # Limit coverage expansion to the attendance period, while keeping every request fact.
    coverage = build_daily_leave_coverage([
        {**r, 'tgl_izin_mulai': max(start_date, r['tgl_izin_mulai']),
         'tgl_izin_sampai': min(end_date, r['tgl_izin_sampai'])}
        for r in leave if r['tgl_izin_mulai'] <= end_date and r['tgl_izin_sampai'] >= start_date])
    days = build_employee_days(rows['dim_pegawai'], rows['dim_calendar'])
    attendance = extract_attendance(source, start_date, end_date)
    days_off = extract_libur_shift(source, start_date, end_date)
    ids = {r['pegawai_id'] for r in rows['dim_pegawai']}
    if any(r['pegawai_id'] not in ids for r in attendance + days_off):
        raise ValueError('Attendance or days off reference unknown employees')
    resolved = apply_expected_workday_rule(resolve_libur_shift(
        resolve_schedule(days, rows['dim_jadwal_kerja']), days_off))
    facts = assemble_fact_rows(resolved, aggregate_attendance(attendance))
    facts = attach_daily_leave_coverage(facts, coverage)
    facts = project_fact_kehadiran_rows(apply_time_compliance_rule(apply_attendance_status_rule(facts)))
    validate_final_fact_rows(facts)
    validate_fact_kehadiran_key_reconciliation(days, facts)
    validate_fact_kehadiran_dimension_references(facts, rows['dim_pegawai'], rows['dim_departemen'], rows['dim_jadwal_kerja'])
    validate_fact_perizinan_dimension_references(rows['fact_perizinan'], rows['dim_pegawai'], rows['dim_departemen'], rows['dim_jenis_izin'])
    validate_perizinan_reference_integrity(facts, rows['fact_perizinan'])
    if sum(r['jumlah_event'] for r in facts) != len(attendance):
        raise ValueError('Attendance event reconciliation failed')
    rows['fact_kehadiran'] = facts
    return rows


def replace_warehouse(conn, rows):
    """Caller commits once; any error rolls back the reset and every loader."""
    conn.execute("SET LOCAL lock_timeout = '10s'")
    conn.execute('SET LOCAL search_path TO public')
    # No CASCADE: newly introduced dependent tables must be reviewed explicitly.
    conn.execute(sql.SQL('TRUNCATE {}').format(sql.SQL(', ').join(
        sql.Identifier('public', table) for table in RESET_TABLES)))
    conn.execute('DELETE FROM etl_control.pipeline_state WHERE pipeline_name = ANY(%s)', (list(PIPELINES),))
    run_id = start_run(conn, 'initial_load')
    for table in LOADERS:
        copy_rows(conn, table, rows[table])
    counts = table_counts(conn, LOADERS)
    if counts != {table: len(rows[table]) for table in LOADERS}:
        raise ValueError('Loaded table counts do not match prepared data')
    finish_run_success(conn, run_id, rows_extracted=sum(counts.values()), rows_inserted=sum(counts.values()))
    return counts


def run_initial_load(source, target, start_date, end_date, apply=False, references=None):
    """Daily batches bound memory; all target batches share one transaction."""
    if start_date > end_date:
        raise ValueError('start_date must be on or before end_date')
    references = references or prepare_references(source)
    base, _, holidays = references
    calendar = transform_calendar(holidays, start_date, end_date)
    statuses = Counter()
    attendance_count = 0
    user_count = 0
    employee_ids = {r['pegawai_id'] for r in base['dim_pegawai']}
    with source.cursor() as cursor:
        cursor.execute("SELECT pegawai_id FROM m_user")
        while batch := cursor.fetchmany(1000):
            if any(row[0] is not None and row[0] not in employee_ids for row in batch):
                raise ValueError('m_user references unknown employees')
            user_count += len(batch)
    if apply:
        target.execute("SET LOCAL lock_timeout = '10s'")
        target.execute('SET LOCAL search_path TO public')
        target.execute(sql.SQL('TRUNCATE {}').format(sql.SQL(', ').join(
            sql.Identifier('public', table) for table in RESET_TABLES)))
        target.execute('DELETE FROM etl_control.pipeline_state WHERE pipeline_name = ANY(%s)', (list(PIPELINES),))
        run_id = start_run(target, 'initial_load')
        for table in LOADERS:
            if table == 'fact_kehadiran':
                continue
            copy_rows(target, table, calendar if table == 'dim_calendar' else base[table])
        with source.cursor() as cursor:
            cursor.execute("SELECT id AS user_id, pegawai_id, is_active, last_login, (last_login IS NOT NULL) AS pernah_login, coalesce(updated_at, created_at) AS source_updated_at FROM m_user")
            columns = [c.name for c in cursor.description]
            while batch := cursor.fetchmany(1000):
                copy_rows(target, 'analytical_user', [dict(zip(columns, row)) for row in batch])
    current = start_date
    while current <= end_date:
        rows = prepare_replacement(source, current, current, references)
        facts = rows['fact_kehadiran']
        attendance_count += len(facts)
        statuses.update(r['status_kehadiran'] for r in facts)
        if apply:
            copy_rows(target, 'fact_kehadiran', facts)
        print(f"{'Loaded' if apply else 'Validated'} {current}: {len(facts):,} employee-days", flush=True)
        current += timedelta(days=1)
    expected = {table: len(rows) for table, rows in base.items()}
    expected['dim_calendar'] = len(calendar)
    expected['analytical_user'] = user_count
    expected['fact_kehadiran'] = len(base['dim_pegawai']) * len(calendar)
    if attendance_count != expected['fact_kehadiran']:
        raise ValueError('Employee-day count mismatch')
    if apply:
        if table_counts(target, RESET_TABLES) != expected:
            raise ValueError('Loaded counts do not match source replacement')
        finish_run_success(target, run_id, rows_inserted=sum(expected.values()))
    return {'rows': expected, 'attendance_statuses': dict(statuses)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-date', type=date.fromisoformat, required=True)
    parser.add_argument('--end-date', type=date.fromisoformat, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--check-only', action='store_true',
                        help='Read-only schema and source readiness report; skip daily transformations')
    parser.add_argument('--confirm-db')
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    if args.start_date > args.end_date:
        parser.error('start-date must be on or before end-date')
    if args.check_only and args.apply:
        parser.error('--check-only cannot be combined with --apply')
    with get_oltp_connection() as source, get_olap_connection() as target:
        source.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        source.execute('SET LOCAL search_path TO public')
        if not args.apply:
            target.execute('SET TRANSACTION READ ONLY')
        readiness = check_requirements(source, target, args.start_date, args.end_date)
        print(json.dumps({'preflight': readiness}, indent=2))
        if not readiness['ready']:
            raise SystemExit(1)
        if args.check_only:
            print('Prerequisite checks passed. Run preview for full business-rule validation.')
            return
        references = prepare_references(source)
        print(json.dumps({'source_database': source.info.dbname, 'target_database': target.info.dbname,
                          'existing': table_counts(target, RESET_TABLES),
                          'employees': len(references[0]['dim_pegawai']),
                          'expected_employee_days': len(references[0]['dim_pegawai']) * ((args.end_date-args.start_date).days+1)}, indent=2))
        if args.apply:
            confirm_database(target, args.confirm_db)
            backup_database(target, 'OLAP', args.backup)
        report = run_initial_load(source, target, args.start_date, args.end_date, args.apply, references)
    print(json.dumps(report, indent=2))
    print('Initial load committed.' if args.apply else 'Validation passed. Preview only; no database writes.')


if __name__ == '__main__':
    main()
