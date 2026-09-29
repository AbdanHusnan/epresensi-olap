"""Append September 2026 transactions using existing source identities only.

Generate an auditable artifact first; apply is atomic and refuses an occupied
month. This command never loads OLAP or writes source master tables.
"""

import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta
import gzip
import hashlib
import json
from pathlib import Path
import random

from psycopg import sql

from etl.connectors.oltp import get_oltp_connection
from etl.dummy.database import confirm_database
from etl.transform.calendar import NAMA_HARI

START, END = date(2026, 9, 1), date(2026, 9, 30)
PROFILE = 'existing-employees-202609-v1'
WEIGHTS = {
    'WFO_TEPAT_WAKTU': 38, 'WFH_TEPAT_WAKTU': 14,
    'WFO_TERLAMBAT': 12, 'WFH_TERLAMBAT': 5,
    'WFO_PULANG_AWAL': 6, 'WFO_TERLAMBAT_PULANG_AWAL': 3,
    'WFO_TANPA_PULANG': 4, 'CUTI_APPROVED': 5, 'SAKIT_APPROVED': 4,
    'IZIN_APPROVED': 3, 'IZIN_PENDING': 2, 'IZIN_REJECTED': 1,
    'TIDAK_ABSEN': 3,
}
COLUMNS = {
    't_checkinout': ('pegawai_id', 'departemen', 'work_code', 'is_wfh',
                     'created_at', 'updated_at'),
    't_perizinan': ('user_id', 'nama', 'departemen', 'pegawai_id', 'tipe_ijin',
                    'jenis_ijin', 'alasan', 'approval', 'approval_at', 'tgl_ijin',
                    'tgl_ijin_sampai', 'created_at', 'updated_at'),
}
MASTER_TABLES = ('m_departemen', 'm_pegawai', 'm_user', 'm_shift', 'm_jadwal',
                 'm_tipe_ijin', 'm_jenis_ijin', 'm_hari_libur', 't_libur_shift')


def rows(conn, query, params=()):
    cur = conn.execute(query, params)
    return [dict(zip([d.name for d in cur.description], r)) for r in cur.fetchall()]


def read_references(conn):
    employees = rows(conn, '''SELECT p.id,p.nama,p.departemen,u.id AS user_id
        FROM m_pegawai p LEFT JOIN m_user u ON u.pegawai_id=p.id ORDER BY p.id,u.id''')
    if not employees or len({p['id'] for p in employees}) != len(employees):
        raise ValueError('Require existing employees with exactly one user each')
    if any(p['user_id'] is None for p in employees):
        raise ValueError('Employee without existing user')
    schedules = rows(conn, '''SELECT s.departemen_id,j.hari,j.jam_masuk,j.jam_keluar,
        s.is_flexible FROM m_jadwal j JOIN m_shift s ON s.id=j.jenis
        ORDER BY s.departemen_id,j.hari,j.id''')
    schedule_keys = [(r['departemen_id'], r['hari']) for r in schedules]
    departments = {p['departemen'] for p in employees}
    expected = {(d, NAMA_HARI[i]) for d in departments for i in range(5)}
    if len(schedule_keys) != len(set(schedule_keys)) or set(schedule_keys) != expected:
        raise ValueError('Profile requires exactly one existing Mon-Fri schedule per department')
    if any(r['is_flexible'] or r['jam_masuk'] >= r['jam_keluar'] for r in schedules):
        raise ValueError('Profile requires fixed same-day schedules')
    holidays = conn.execute('SELECT count(*) FROM m_hari_libur WHERE tanggal BETWEEN %s AND %s', (START, END)).fetchone()[0]
    days_off = conn.execute('SELECT count(*) FROM t_libur_shift WHERE tanggal BETWEEN %s AND %s', (START, END)).fetchone()[0]
    if holidays or days_off:
        raise ValueError('September profile expects no additional source holidays/days off')
    leave_types = rows(conn, 'SELECT id,kode,tipe_id FROM m_jenis_ijin ORDER BY id')
    codes = [r['kode'] for r in leave_types]
    if any(codes.count(code) != 1 for code in ('CT', 'SK', 'IP')):
        raise ValueError('Require existing unique CT, SK, IP leave types')
    return dict(employees=employees, schedules=schedules, leave_types=leave_types)


def fingerprint(conn, table, max_id=None):
    query = sql.SQL("SELECT count(*),md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' ORDER BY id),'')) FROM {} t").format(sql.Identifier(table))
    if max_id is not None:
        query += sql.SQL(' WHERE id <= %s')
    return list(conn.execute(query, (max_id,) if max_id is not None else ()).fetchone())


def reference_digest(refs):
    return hashlib.sha256(json.dumps(refs, default=str, sort_keys=True).encode()).hexdigest()


def ensure_empty(conn):
    events = conn.execute('SELECT EXISTS(SELECT 1 FROM t_checkinout WHERE created_at >= %s AND created_at < %s)', (START, END + timedelta(days=1))).fetchone()[0]
    permissions = conn.execute('SELECT EXISTS(SELECT 1 FROM t_perizinan WHERE tgl_ijin <= %s AND coalesce(tgl_ijin_sampai,tgl_ijin) >= %s)', (END, START)).fetchone()[0]
    if events or permissions:
        raise ValueError('September already contains transactions; refusing a duplicate append')


def quotas(size):
    result = {key: size * weight // 100 for key, weight in WEIGHTS.items()}
    for key in sorted(WEIGHTS, key=lambda k: -(size * WEIGHTS[k] % 100))[:size - sum(result.values())]:
        result[key] += 1
    return result


def generate_day(refs, day, seed):
    """Disjoint categories, shuffled daily; original IDs/names/department used."""
    if not START <= day <= END:
        raise ValueError('September 2026 only')
    tables = {table: [] for table in COLUMNS}
    if day.weekday() >= 5:
        return tables, Counter()
    employees = list(refs['employees'])
    rng = random.Random(f'{PROFILE}:{seed}:{day}')
    rng.shuffle(employees)
    schedules = {(r['departemen_id'], r['hari']): r for r in refs['schedules']}
    leave_types = {r['kode']: r for r in refs['leave_types']}
    counts = quotas(len(employees))
    offset = 0
    for category, count in counts.items():
        for p in employees[offset:offset + count]:
            if category == 'TIDAK_ABSEN':
                continue
            if category.startswith(('CUTI_', 'SAKIT_', 'IZIN_')):
                code = 'CT' if category.startswith('CUTI_') else 'SK' if category.startswith('SAKIT_') else 'IP'
                kind = leave_types[code]
                approval = None if category.endswith('PENDING') else not category.endswith('REJECTED')
                # Every new permission timestamp is beyond the August watermark.
                submitted = datetime.combine(day, time(5))
                decision = submitted + timedelta(minutes=30) if approval is not None else None
                tables['t_perizinan'].append(dict(user_id=p['user_id'], nama=p['nama'],
                    departemen=p['departemen'], pegawai_id=p['id'], tipe_ijin=kind['tipe_id'],
                    jenis_ijin=kind['id'], alasan=f'Fixture {PROFILE}: {category}',
                    approval=approval, approval_at=decision, tgl_ijin=day,
                    tgl_ijin_sampai=day, created_at=submitted, updated_at=decision or submitted))
                continue
            schedule = schedules[p['departemen'], NAMA_HARI[day.weekday()]]
            arrival = datetime.combine(day, schedule['jam_masuk']) + timedelta(
                minutes=rng.randint(5, 90) if 'TERLAMBAT' in category else -rng.randint(0, 25))
            departure = datetime.combine(day, schedule['jam_keluar']) + timedelta(
                minutes=-rng.randint(5, 75) if 'PULANG_AWAL' in category else rng.randint(0, 40))
            moments = [arrival] if category == 'WFO_TANPA_PULANG' else [arrival, departure]
            if len(moments) == 2 and departure <= arrival:
                raise ValueError('Existing shift is too short for this fixture')
            for moment in moments:
                tables['t_checkinout'].append(dict(pegawai_id=p['id'], departemen=p['departemen'],
                    work_code=1, is_wfh=int(category.startswith('WFH_')),
                    created_at=moment, updated_at=moment))
        offset += count
    return tables, Counter(counts)


def expected_outcomes(categories, employees):
    present = sum(v for k, v in categories.items() if k.startswith(('WFO_', 'WFH_')))
    approved = sum(v for k, v in categories.items() if k.endswith('_APPROVED'))
    absent = sum(categories[k] for k in ('IZIN_PENDING', 'IZIN_REJECTED', 'TIDAK_ABSEN'))
    return {
        'full_month_facts': employees * 30,
        'full_month_statuses': {'HADIR': present, 'IZIN': approved,
                               'TIDAK_ABSEN': absent, 'NON_WORKING_DAY': employees * 8},
        # Pending/rejected permissions create permission facts, but add no affected
        # employee-days when no old approved coverage or attendance event exists.
        'incremental_only_new_attendance_facts': present + approved,
        'late_employee_days': sum(v for k, v in categories.items() if 'TERLAMBAT' in k),
        'early_departure_employee_days': sum(v for k, v in categories.items() if 'PULANG_AWAL' in k),
        'wfh_employee_days': sum(v for k, v in categories.items() if k.startswith('WFH_')),
        'incomplete_present_days': categories['WFO_TANPA_PULANG'],
    }


def generate(conn, destination, seed=202609):
    ensure_empty(conn)
    refs = read_references(conn)
    header = dict(profile=PROFILE, start_date=str(START), end_date=str(END), seed=seed,
                  employees=len(refs['employees']), departments=len({p['departemen'] for p in refs['employees']}),
                  reference_digest=reference_digest(refs), weights=WEIGHTS,
                  master_fingerprints={t: fingerprint(conn, t) for t in MASTER_TABLES})
    totals, categories, daily = Counter(), Counter(), []
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(destination, 'xt', encoding='utf-8', compresslevel=1) as stream:
        def write(value):
            stream.write(json.dumps(value, default=str) + '\n')
        write(header)
        for index in range(30):
            day = START + timedelta(days=index)
            tables, counts = generate_day(refs, day, seed)
            categories.update(counts)
            daily.append(dict(date=str(day), categories=dict(counts)))
            for table, records in tables.items():
                totals[table] += len(records)
                for offset in range(0, len(records), 2000):
                    write(dict(table=table, rows=records[offset:offset + 2000]))
            print(f'Generated {day}: {sum(map(len, tables.values())):,} transactions', flush=True)
        summary = dict(complete=True, rows=dict(totals), categories=dict(categories), daily=daily,
                       expected=expected_outcomes(categories, len(refs['employees'])))
        write(summary)
    return {**header, **summary}


def read_artifact(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        yield from (json.loads(line) for line in stream)


def restore_types(row):
    return {k: (date.fromisoformat(v) if k in ('tgl_ijin', 'tgl_ijin_sampai') else
                datetime.fromisoformat(v) if k.endswith('_at') and v is not None else v)
            for k, v in row.items()}


def align_sequence(conn, table):
    # Source serial defaults need not be OWNED BY, so inspect default dependencies.
    sequences = conn.execute('''SELECT DISTINCT ns.nspname,s.relname
        FROM pg_class t JOIN pg_namespace tn ON tn.oid=t.relnamespace
        JOIN pg_attribute a ON a.attrelid=t.oid AND a.attname='id'
        JOIN pg_attrdef ad ON ad.adrelid=t.oid AND ad.adnum=a.attnum
        JOIN pg_depend d ON d.classid='pg_attrdef'::regclass AND d.objid=ad.oid
        JOIN pg_class s ON s.oid=d.refobjid AND s.relkind='S'
        JOIN pg_namespace ns ON ns.oid=s.relnamespace
        WHERE tn.nspname=current_schema() AND t.relname=%s''', (table,)).fetchall()
    if len(sequences) != 1:
        raise ValueError(f'{table}.id must have one serial sequence default')
    sequence = sql.Identifier(*sequences[0])
    maximum = conn.execute(sql.SQL('SELECT coalesce(max(id),0) FROM {}').format(sql.Identifier(table))).fetchone()[0]
    last, called = conn.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(sequence)).fetchone()
    next_id = max(maximum + 1, last + int(called))
    # RESTART is transactional and locks the sequence until commit. Never rewind.
    conn.execute(sql.SQL('ALTER SEQUENCE {} RESTART WITH {}').format(sequence, sql.Literal(next_id)))
    return next_id


def append_artifact(conn, path):
    """Caller owns commit. Lock writers; rollback includes sequence restarts."""
    conn.execute("SET LOCAL lock_timeout='10s'")
    conn.execute(sql.SQL('LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE').format(
        sql.SQL(',').join(sql.Identifier(t) for t in COLUMNS)))
    conn.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(
        sql.SQL(',').join(sql.Identifier(t) for t in MASTER_TABLES)))
    ensure_empty(conn)
    stream = iter(read_artifact(path))
    header = next(stream)
    if (header.get('profile') != PROFILE or header.get('start_date') != str(START)
            or header.get('end_date') != str(END)):
        raise ValueError('Unexpected fixture profile/period')
    if header['reference_digest'] != reference_digest(read_references(conn)):
        raise ValueError('Source references changed since artifact generation')
    masters = {t: fingerprint(conn, t) for t in MASTER_TABLES}
    if masters != header['master_fingerprints']:
        raise ValueError('Source masters changed since artifact generation')
    baseline = {}
    for table in COLUMNS:
        maximum = conn.execute(sql.SQL('SELECT coalesce(max(id),0) FROM {}').format(sql.Identifier(table))).fetchone()[0]
        baseline[table] = dict(max_id=maximum, fingerprint=fingerprint(conn, table, maximum))
    first_ids = {t: align_sequence(conn, t) for t in COLUMNS}
    totals, trailer = Counter(), None
    for item in stream:
        if trailer is not None:
            raise ValueError('Unexpected data after completion trailer')
        if item.get('complete'):
            trailer = item
            continue
        table = item['table']
        if table not in COLUMNS:
            raise ValueError('Only attendance and permission inserts are permitted')
        columns = COLUMNS[table]
        with conn.cursor().copy(sql.SQL('COPY {} ({}) FROM STDIN').format(
                sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, columns)))) as copy:
            for raw in item['rows']:
                if set(raw) != set(columns):
                    raise ValueError('Unexpected artifact fields')
                row = restore_types(raw)
                day = row['created_at'].date() if table == 't_checkinout' else row['tgl_ijin']
                if not START <= day <= END or (table == 't_perizinan' and row['tgl_ijin_sampai'] != day):
                    raise ValueError('Transaction outside the fixture period')
                copy.write_row([row[k] for k in columns])
                totals[table] += 1
    if trailer is None or dict(totals) != trailer['rows']:
        raise ValueError('Incomplete artifact or row count mismatch')
    for table, old in baseline.items():
        if fingerprint(conn, table, old['max_id']) != old['fingerprint']:
            raise ValueError('Existing transactions changed')
    if {t: fingerprint(conn, t) for t in MASTER_TABLES} != masters:
        raise ValueError('Source masters changed')
    return dict(profile=PROFILE, inserted=dict(totals), first_ids=first_ids,
                baseline=baseline, masters_unchanged=True, existing_transactions_unchanged=True,
                expected=trailer['expected'], categories=trailer['categories'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('generate', 'apply'))
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--seed', type=int, default=202609)
    parser.add_argument('--confirm-db')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    # Reserve the report before any database mutation; never overwrite evidence.
    with args.report.open('x') as report:
        with get_oltp_connection() as conn:
            conn.execute('SET LOCAL search_path TO public')
            if args.action == 'generate':
                conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                result = generate(conn, args.artifact, args.seed)
            else:
                confirm_database(conn, args.confirm_db)
                result = append_artifact(conn, args.artifact)
            conn.commit()
            result['committed'] = args.action == 'apply'
        json.dump(result, report, indent=2, default=str)
        report.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('daily', 'master_fingerprints')}, indent=2, default=str))


if __name__ == '__main__':
    main()
