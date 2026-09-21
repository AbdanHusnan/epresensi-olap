"""Affected-key planning and bounded employee-day recomputation, without writes."""


from collections import defaultdict
from datetime import timedelta

from etl.extract.incremental import fetch_rows
from etl.extract.fact_kehadiran import extract_schedule
from etl.extract.fact_perizinan.extract_reference import (
    extract_pegawai_reference, extract_jenis_izin_reference,
)
from etl.transform.fact_perizinan.normalize import normalize_perizinan_rows
from etl.transform.fact_perizinan.approval import apply_approval_rules
from etl.transform.fact_perizinan.dimensions import resolve_perizinan_dimensions_rows
from etl.transform.fact_perizinan.build_fact import build_fact_perizinan_rows
from etl.transform.fact_perizinan.final_validation import validate_fact_perizinan_rows
from etl.transform.fact_kehadiran.employee_day import build_employee_days
from etl.transform.fact_kehadiran.schedule import resolve_schedule
from etl.transform.fact_kehadiran.libur_shift import resolve_libur_shift
from etl.transform.fact_kehadiran.attendance import aggregate_attendance
from etl.transform.fact_kehadiran.assembler import (
    assemble_fact_rows, project_fact_kehadiran_rows, validate_final_fact_rows,
)
from etl.transform.fact_kehadiran.rules import (
    apply_expected_workday_rule, apply_attendance_status_rule, apply_time_compliance_rule,
)
from etl.transform.fact_kehadiran.leave import attach_daily_leave_coverage



def prepare_permissions(source_rows, target, *, pegawai_reference=None,
                        jenis_izin_reference=None):
    """Build permission facts, optionally reusing bounded-run dimension references."""
    pegawai_reference = (pegawai_reference if pegawai_reference is not None
                          else extract_pegawai_reference(target))
    jenis_izin_reference = (jenis_izin_reference if jenis_izin_reference is not None
                            else extract_jenis_izin_reference(target))
    rows = resolve_perizinan_dimensions_rows(
        apply_approval_rules(normalize_perizinan_rows(source_rows)),
        pegawai_reference, jenis_izin_reference,
    )
    facts = build_fact_perizinan_rows(rows)
    validate_fact_perizinan_rows(facts)
    return facts


def build_affected_employee_days(events, old_permissions, new_permissions):
    keys = {(row['pegawai_id'], row['tanggal']) for row in events}
    for row in [*old_permissions, *new_permissions]:
        if not row['is_valid_leave']:
            continue
        day = row['tanggal_mulai']
        while day <= row['tanggal_selesai']:
            keys.add((row['pegawai_id'], day))
            day += timedelta(days=1)
    if any(employee is None or day is None for employee, day in keys):
        raise ValueError('Affected employee-day contains a NULL employee or date')
    return keys


def employee_day_batches(keys, batch_size=1000):
    if batch_size <= 0:
        raise ValueError('batch_size must be positive')
    by_day = defaultdict(list)
    for employee, day in sorted(keys, key=lambda key: (key[1], key[0])):
        by_day[day].append(employee)
    for day, employees in by_day.items():
        for offset in range(0, len(employees), batch_size):
            yield day, employees[offset:offset + batch_size]


def iter_recomputed_employee_days(source, target, keys, batch_size=1000):
    """Yield bounded daily batches; query ALL current events/permissions for each key."""
    schedules = extract_schedule(target) if keys else []
    for day, employees in employee_day_batches(keys, batch_size):
        people = fetch_rows(target, 'SELECT * FROM dim_pegawai WHERE pegawai_id = ANY(%s)', (employees,))
        calendar = fetch_rows(target, 'SELECT * FROM dim_calendar WHERE tanggal = %s', (day,))
        if {r['pegawai_id'] for r in people} != set(employees) or len(calendar) != 1:
            raise ValueError(f'Missing employee/calendar dimensions for {day}; sync dimensions first')
        events = fetch_rows(source, '''
            SELECT * FROM t_checkinout WHERE pegawai_id = ANY(%s) AND work_code = 1
            AND created_at >= %s::date AND created_at < (%s::date + INTERVAL '1 day')
            ORDER BY pegawai_id, created_at, id
        ''', (employees, day, day))
        days_off = fetch_rows(source, '''
            SELECT * FROM t_libur_shift WHERE pegawai_id = ANY(%s) AND tanggal = %s
        ''', (employees, day))
        permissions = fetch_rows(source, '''
            SELECT id AS source_perizinan_id, pegawai_id, %s::date AS tanggal
            FROM t_perizinan WHERE pegawai_id = ANY(%s) AND approval IS TRUE
            AND tgl_ijin <= %s AND COALESCE(tgl_ijin_sampai, tgl_ijin) >= %s
            ORDER BY id
        ''', (day, employees, day, day))
        days = apply_expected_workday_rule(resolve_libur_shift(
            resolve_schedule(build_employee_days(people, calendar), schedules), days_off))
        facts = attach_daily_leave_coverage(
            assemble_fact_rows(days, aggregate_attendance(events)), permissions)
        facts = project_fact_kehadiran_rows(apply_time_compliance_rule(apply_attendance_status_rule(facts)))
        validate_final_fact_rows(facts)
        if {(r['pegawai_id'], r['tanggal']) for r in facts} != {(p, day) for p in employees}:
            raise ValueError('Employee-day reconciliation failed')
        if sum(r['jumlah_event'] for r in facts) != len(events):
            raise ValueError('Attendance event reconciliation failed')
        yield facts


def recompute_employee_days(oltp_conn, olap_conn, affected_employee_days):
    """Convenience API returning final rows; pipeline streams batches instead."""
    return [row for batch in iter_recomputed_employee_days(
        oltp_conn, olap_conn, affected_employee_days) for row in batch]
