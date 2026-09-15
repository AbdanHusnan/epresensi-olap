"""Reproducible August 2026 fixture with exact daily department-level quotas.

Office names: https://api.sikipo.jatimprov.go.id/index.php/dashboard/opd
Holidays: https://www.kemenkopmk.go.id/node/5862
People, work patterns, and attendance are fictional (local WIB wall-clock times).
"""

import random
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from math import gcd

from etl.transform.calendar import NAMA_HARI

PROFILE = 'jatim-202608'
DEPARTMENTS = (
    'Dinas Pertanian dan Ketahanan Pangan',
    'Dinas Pekerjaan Umum Sumber Daya Air',
    'Dinas Pendidikan',
    'Dinas Kesehatan',
    'Dinas Sosial',
    'Dinas Tenaga Kerja dan Transmigrasi',
    'Dinas Perhubungan',
    'Dinas Komunikasi dan Informatika',
    'Dinas Perindustrian dan Perdagangan',
    'Dinas Koperasi, Usaha Kecil dan Menengah',
    'Dinas Lingkungan Hidup',
    'Dinas Kehutanan',
    'Dinas Kelautan dan Perikanan',
    'Dinas Peternakan',
    'Dinas Perkebunan',
    'Dinas Energi dan Sumber Daya Mineral',
    'Dinas Kebudayaan dan Pariwisata',
    'Dinas Kepemudaan dan Olahraga',
    'Dinas Pekerjaan Umum dan Bina Marga',
    'Dinas Perumahan Rakyat, Kawasan Permukiman dan Cipta Karya',
    'Dinas Pemberdayaan Masyarakat dan Desa',
    'Dinas Pemberdayaan Perempuan, Perlindungan Anak dan Kependudukan',
    'Dinas Penanaman Modal dan Pelayanan Terpadu Satu Pintu',
    'Dinas Perpustakaan dan Kearsipan',
    'Badan Pendapatan Daerah',
)
SHIFTS = (
    ('Shift 1', time(7), time(15)),
    ('Shift 2', time(8), time(16)),
    ('Shift 3', time(9), time(17)),
    ('Shift 4', time(12), time(20)),
)
HOLIDAYS = {
    date(2026, 8, 17): 'Proklamasi Kemerdekaan Republik Indonesia',
    date(2026, 8, 25): 'Maulid Nabi Muhammad SAW',
}
WEIGHTS = {'WFO_TEPAT_WAKTU': 60, 'WFH': 10, 'WFO_TERLAMBAT': 10,
           'IZIN': 10, 'TIDAK_ABSEN': 10}


def validate_period(start_date, end_date):
    if not date(2026, 8, 1) <= start_date <= end_date <= date(2026, 8, 31):
        raise ValueError('Profile jatim-202608 requires dates within August 2026')


def quotas(size):
    """Largest-remainder rounding; exact percentages when size is divisible by 10."""
    result = {key: size * weight // 100 for key, weight in WEIGHTS.items()}
    order = sorted(WEIGHTS, key=lambda key: -(size * WEIGHTS[key] % 100))
    for key in order[:size - sum(result.values())]:
        result[key] += 1
    return result


@lru_cache(maxsize=4096)
def assignment(day, department, total_employees, seed):
    size = (total_employees - department) // len(DEPARTMENTS) + 1
    rng = random.Random(f'{seed}:{day.isoformat()}:{department}:categories')
    # An affine permutation assigns every local employee a unique rank, without
    # allocating/shuffling an 82,000-entry list in every generation batch.
    multiplier = rng.randrange(1, max(2, size))
    while gcd(multiplier, size) != 1:
        multiplier += 1
    return size, multiplier, rng.randrange(size), quotas(size)


def category_for(employee, day, total_employees, seed):
    department = (employee - 1) % len(DEPARTMENTS) + 1
    local_index = (employee - 1) // len(DEPARTMENTS)
    size, multiplier, offset, counts = assignment(day, department, total_employees, seed)
    rank = (local_index * multiplier + offset) % size
    for category, count in counts.items():
        if rank < count:
            return category
        rank -= count
    raise AssertionError('Category quotas do not cover employee rank')


def generate_jatim(start_date, end_date, employees=100, seed=42,
                   employee_offset=0, total_employees=None):
    validate_period(start_date, end_date)
    total_employees = total_employees if total_employees is not None else employees
    if (not 1 <= employees <= 10000 or employee_offset < 0
            or total_employees < employee_offset + employees or total_employees > 100000):
        raise ValueError('Invalid employee batch or total employee count')
    tables = {name: [] for name in (
        'm_departemen', 'm_pegawai', 'm_user', 'm_shift', 'm_jadwal',
        'm_tipe_ijin', 'm_jenis_ijin', 'm_hari_libur', 't_libur_shift',
        't_perizinan', 't_checkinout',
    )}
    stamp = datetime(2026, 7, 1, 9)

    def add(table, **values):
        row = {'id': len(tables[table]) + 1, **values}
        tables[table].append(row)
        return row

    for department, name in enumerate(DEPARTMENTS, 1):
        add('m_departemen', kode=f'DUMMYJT{department:02}',
            nama_departemen=name + ' Provinsi Jawa Timur', created_at=stamp)
        for shift_index, (label, _, _) in enumerate(SHIFTS):
            add('m_shift', id=(department - 1) * 4 + shift_index + 1,
                nama=label, departemen_id=department, is_flexible=0, created_at=stamp)
        for weekday in range(5):
            shift_index = (department - 1 + weekday) % 4
            _, arrival, departure = SHIFTS[shift_index]
            add('m_jadwal', jenis=(department - 1) * 4 + shift_index + 1,
                hari=NAMA_HARI[weekday], jam_masuk=arrival, jam_keluar=departure,
                jam_masuk_awal=time(arrival.hour - 1),
                jam_keluar_akhir=time(departure.hour + 1), created_at=stamp)
    add('m_tipe_ijin', nama='Izin ketidakhadiran', tipe='izin')
    for code, label in [('CT', 'Cuti tahunan'), ('SK', 'Sakit'), ('IP', 'Izin pribadi')]:
        add('m_jenis_ijin', nama=label, kode=code, tipe_id=1, created_at=stamp)
    for day, label in HOLIDAYS.items():
        if start_date <= day <= end_date:
            add('m_hari_libur', tanggal=day, keterangan=label, created_at=stamp)
    dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    for employee in range(employee_offset + 1, employee_offset + employees + 1):
        department = (employee - 1) % len(DEPARTMENTS) + 1
        name = f'Pegawai Dummy Jatim {employee:05}'
        add('m_pegawai', id=employee, nip=f'DUMMYJT{employee:011}', nama=name,
            departemen=department, created_at=stamp, updated_at=stamp)
        add('m_user', id=employee, email=f'dummy.jatim.{employee}@example.invalid',
            nama=name, pegawai_id=employee, is_active=True, last_login=None,
            created_at=stamp, updated_at=stamp)
        for day in dates:
            if day.weekday() >= 5 or day in HOLIDAYS:
                continue
            category = category_for(employee, day, total_employees, seed)
            rng = random.Random(f'{seed}:{employee}:{day.isoformat()}:events')
            if category == 'TIDAK_ABSEN':
                continue
            if category == 'IZIN':
                submitted = datetime.combine(day - timedelta(days=3), time(10))
                approved = submitted + timedelta(days=1)
                add('t_perizinan', user_id=employee, nama=name, departemen=department,
                    pegawai_id=employee, tipe_ijin=1, jenis_ijin=rng.randint(1, 3),
                    alasan='Izin satu hari sintetis untuk dummy OLAP', approval=True,
                    approval_at=approved, tgl_ijin=day, tgl_ijin_sampai=day,
                    created_at=submitted, updated_at=approved)
                continue
            _, shift_start, shift_end = SHIFTS[(department - 1 + day.weekday()) % 4]
            offset = rng.randint(5, 60) if category == 'WFO_TERLAMBAT' else -rng.randint(0, 25)
            arrival = datetime.combine(day, shift_start) + timedelta(minutes=offset)
            departure = datetime.combine(day, shift_end) + timedelta(minutes=rng.randint(0, 30))
            for moment in (arrival, departure):
                add('t_checkinout', pegawai_id=employee, departemen=department,
                    work_code=1, is_wfh=int(category == 'WFH'),
                    created_at=moment, updated_at=moment)
    return tables


def profile_metadata():
    return {'name': PROFILE, 'department_names_source': 'https://api.sikipo.jatimprov.go.id/index.php/dashboard/opd',
            'holiday_source': 'https://www.kemenkopmk.go.id/node/5862',
            'timezone': 'Asia/Jakarta', 'timestamp_storage': 'naive local wall-clock',
            'category_percentages': WEIGHTS, 'percentage_denominator': 'scheduled employee-days excluding holidays',
            'departments': list(DEPARTMENTS),
            'shift_patterns': [{'name': n, 'start': a.isoformat(), 'end': b.isoformat()} for n, a, b in SHIFTS],
            'shift_storage': '4 patterns per department, 100 m_shift rows, 125 weekday schedules',
            'holiday_dates': {d.isoformat(): label for d, label in HOLIDAYS.items()},
            'leave_rule': 'one-day approved only', 'weekend_work': False}
