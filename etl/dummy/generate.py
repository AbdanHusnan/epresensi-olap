"""Generate fictional source rows; no database connection is needed."""

import argparse
import json
import gzip
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

from etl.transform.calendar import NAMA_HARI
from etl.dummy.jatim import PROFILE, generate_jatim, profile_metadata, validate_period


def generate_dataset(start_date, end_date, employees=100, seed=42, employee_offset=0):
    if start_date > end_date or not 1 <= employees <= 10000:
        raise ValueError("Use an ordered date range and 1–10,000 employees")
    if employees * ((end_date - start_date).days + 1) > 500000:
        raise ValueError("Limit this development dataset to 500,000 employee-days")
    rng = random.Random(seed)
    tables = {name: [] for name in (
        'm_departemen', 'm_pegawai', 'm_user', 'm_shift', 'm_jadwal',
        'm_tipe_ijin', 'm_jenis_ijin', 'm_hari_libur', 't_libur_shift',
        't_perizinan', 't_checkinout',
    )}
    stamp = datetime.combine(start_date - timedelta(days=30), time(9))

    def add(table, **values):
        row = {'id': len(tables[table]) + 1, **values}
        tables[table].append(row)
        return row

    for dept, name in enumerate(('Administrasi', 'Keuangan', 'Teknologi', 'Pelayanan', 'Operasional'), 1):
        add('m_departemen', kode=f'DEMO{dept:02}', nama_departemen=f'{name} Demo', created_at=stamp)
        add('m_shift', nama=f'Jadwal {name}', departemen_id=dept, is_flexible=int(dept == 3), created_at=stamp)
        for weekday in range(6 if dept == 5 else 5):
            add('m_jadwal', jenis=dept, hari=NAMA_HARI[weekday],
                jam_masuk=time(8), jam_keluar=time(16 if weekday != 4 else 15),
                jam_masuk_awal=time(6), jam_keluar_akhir=time(20), created_at=stamp)
    add('m_tipe_ijin', nama='Izin Demo', tipe='izin')
    for code, name in [('CT', 'Cuti tahunan'), ('SK', 'Sakit'), ('IP', 'Izin pribadi')]:
        add('m_jenis_ijin', nama=name, kode=code, tipe_id=1, created_at=stamp)

    dates = [start_date + timedelta(days=i) for i in range((end_date-start_date).days+1)]
    # Fictional organization closures, deliberately not a national holiday calendar.
    holidays = {d for d in dates if d.day == 15 and d.weekday() < 5}
    for day in sorted(holidays):
        add('m_hari_libur', tanggal=day, keterangan='Penutupan kantor sintetis', created_at=stamp)

    for emp in range(employee_offset + 1, employee_offset + employees + 1):
        rng = random.Random(seed + emp)
        dept = (emp - 1) % 5 + 1
        name = f'Pegawai Demo {emp:05}'
        add('m_pegawai', id=emp, nip=f'DEMO{emp:014}', nama=name, departemen=dept,
            created_at=stamp, updated_at=stamp)
        add('m_user', id=emp, email=f'pegawai{emp}@example.invalid', nama=name,
            pegawai_id=emp, is_active=True, last_login=None, created_at=stamp, updated_at=stamp)
        leave_until = start_date - timedelta(days=1)
        for day in dates:
            scheduled = day.weekday() < (6 if dept == 5 else 5) and day not in holidays
            if scheduled and dept == 5 and (day.toordinal() + emp) % 14 == 0:
                add('t_libur_shift', departemen_id=dept, pegawai_id=emp, tanggal=day,
                    keterangan='Istirahat bergilir demo', created_at=stamp, updated_at=stamp)
                scheduled = False
            if day <= leave_until:
                continue
            if scheduled and rng.random() < 0.025:
                approval = rng.choices([True, False, None], weights=[80, 10, 10])[0]
                until = min(day + timedelta(days=rng.choices([0, 1, 2], [65, 25, 10])[0]), end_date)
                submitted = datetime.combine(day - timedelta(days=3), time(10))
                approved_at = submitted + timedelta(days=1) if approval is not None else None
                add('t_perizinan', user_id=emp, nama=name, departemen=dept, pegawai_id=emp,
                    tipe_ijin=1, jenis_ijin=rng.randint(1, 3), alasan='Pengajuan sintetis untuk pengujian ETL',
                    approval=approval, approval_at=approved_at, tgl_ijin=day,
                    tgl_ijin_sampai=until, created_at=submitted, updated_at=approved_at or submitted)
                if approval is True:
                    leave_until = until
                    continue
            # Occasional work on a day off; absence on expected days.
            if (not scheduled and rng.random() >= 0.015) or (scheduled and rng.random() < 0.025):
                continue
            wfh = int(dept in (1, 2, 3) and rng.random() < 0.18)
            late = rng.randint(5, 70) if rng.random() < 0.12 else -rng.randint(0, 25)
            early = -rng.randint(5, 60) if rng.random() < 0.07 else rng.randint(0, 35)
            arrival = datetime.combine(day, time(8)) + timedelta(minutes=late)
            departure = datetime.combine(day, time(15 if day.weekday() == 4 else 16)) + timedelta(minutes=early)
            moments = [arrival]
            if rng.random() >= 0.025:
                moments.append(departure)
            if len(moments) == 2 and rng.random() < 0.04:
                moments.insert(1, datetime.combine(day, time(12)))
            for moment in moments:
                add('t_checkinout', pegawai_id=emp, departemen=dept, work_code=1,
                    is_wfh=wfh, created_at=moment, updated_at=moment)
    return tables


def write_dataset(destination, start_date, end_date, employees=82000, seed=42, profile='legacy'):
    """Stream compressed JSON Lines in batches; IDs stay unique across batches."""
    if start_date > end_date or not 1 <= employees <= 100000:
        raise ValueError('Use an ordered date range and 1–100,000 employees')
    if (end_date - start_date).days > 365:
        raise ValueError('Generate at most one year per dataset')
    if profile not in ('legacy', PROFILE):
        raise ValueError(f'Unknown dummy profile: {profile}')
    if profile == PROFILE:
        validate_period(start_date, end_date)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    counts = {}
    masters = {'m_departemen', 'm_shift', 'm_jadwal', 'm_tipe_ijin', 'm_jenis_ijin', 'm_hari_libur'}
    with gzip.open(destination, 'xt', encoding='utf-8', compresslevel=1) as stream:
        def write(value):
            stream.write(json.dumps(value, default=lambda v: v.isoformat()) + '\n')
        write({'format_version': 2, 'synthetic': True, 'start_date': start_date,
               'end_date': end_date, 'employees': employees, 'seed': seed,
               'profile': profile_metadata() if profile == PROFILE else {'name': 'legacy'}})
        for offset in range(0, employees, 100):
            if profile == PROFILE:
                tables = generate_jatim(start_date, end_date, min(100, employees-offset), seed, offset, employees)
            else:
                tables = generate_dataset(start_date, end_date, min(100, employees-offset), seed, offset)
            for table, rows in tables.items():
                if offset and table in masters:
                    continue
                if table not in masters | {'m_pegawai', 'm_user'}:
                    for row in rows:
                        row['id'] += counts.get(table, 0)
                counts[table] = counts.get(table, 0) + len(rows)
                write({'table': table, 'rows': rows})
            if offset % 1000 == 0:
                print(f'Generated {min(offset+100, employees):,}/{employees:,} employees', flush=True)
        write({'complete': True, 'counts': counts})
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-date', type=date.fromisoformat, required=True)
    parser.add_argument('--end-date', type=date.fromisoformat, required=True)
    parser.add_argument('--employees', type=int, default=82000)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--profile', choices=('legacy', PROFILE), default='legacy')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    counts = write_dataset(args.output, args.start_date, args.end_date, args.employees, args.seed, args.profile)
    print(json.dumps(counts, indent=2))


if __name__ == '__main__':
    main()
