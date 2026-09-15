import gzip
import json
import tempfile
import unittest
from collections import Counter
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch

from etl.dummy.generate import write_dataset
from etl.dummy.jatim import PROFILE, DEPARTMENTS, SHIFTS, generate_jatim
from etl.dummy.seed import read_dataset
from etl.pipeline import initial_load


class JatimDummyTests(unittest.TestCase):
    def test_month_matches_agreed_categories_after_etl(self):
        start, end = date(2026, 8, 1), date(2026, 8, 31)
        tables = generate_jatim(start, end, 250)
        self.assertEqual(len(tables['m_departemen']), 25)
        self.assertEqual(set(Counter(r['departemen'] for r in tables['m_pegawai']).values()), {10})
        self.assertEqual(len(tables['m_shift']), 100)
        self.assertEqual(len(tables['m_jadwal']), 125)
        self.assertEqual({(r['jam_masuk'], r['jam_keluar']) for r in tables['m_jadwal']},
                         {(a, b) for _, a, b in SHIFTS})
        mappings = {
            'extract_pegawai': 'm_pegawai', 'extract_departemen': 'm_departemen',
            'extract_jadwal': 'm_jadwal', 'extract_shift': 'm_shift',
            'extract_jenis_izin': 'm_jenis_ijin', 'extract_tipe_izin': 'm_tipe_ijin',
            'extract_perizinan': 't_perizinan', 'extract_hari_libur': 'm_hari_libur',
            'extract_attendance': 't_checkinout', 'extract_libur_shift': 't_libur_shift',
        }
        with ExitStack() as stack:
            for function, table in mappings.items():
                stack.enter_context(patch.object(initial_load, function, return_value=tables[table]))
            result = initial_load.prepare_replacement(None, start, end)
        facts = result['fact_kehadiran']
        self.assertEqual(len(facts), 7750)
        self.assertEqual(Counter(r['status_kehadiran'] for r in facts),
                         {'HADIR': 3800, 'IZIN': 475, 'TIDAK_ABSEN': 475, 'NON_WORKING_DAY': 3000})
        self.assertEqual(sum(r['is_wfh'] for r in facts), 475)
        self.assertEqual(sum(r['is_terlambat'] for r in facts), 475)
        self.assertEqual(sum(r['is_wfo'] and not r['is_terlambat'] for r in facts), 2850)
        self.assertFalse(any(r['is_wfh'] and r['is_terlambat'] for r in facts))
        self.assertFalse(any(r['is_pulang_awal'] for r in facts))
        self.assertEqual(len(result['fact_perizinan']), 475)
        self.assertTrue(all(r['status_pengajuan'] == 'APPROVED' for r in result['fact_perizinan']))
        self.assertEqual(sum(r['jumlah_event'] for r in facts), 7600)
        # Quotas hold independently for each department and scheduled day.
        groups = {}
        for row in facts:
            if row['is_expected_workday']:
                category = ('WFH' if row['is_wfh'] else 'TERLAMBAT' if row['is_terlambat']
                            else row['status_kehadiran'])
                groups.setdefault((row['departemen_id'], row['tanggal']), Counter())[category] += 1
        self.assertEqual(len(groups), 25 * 19)
        self.assertTrue(all(c == {'HADIR': 6, 'WFH': 1, 'TERLAMBAT': 1, 'IZIN': 1, 'TIDAK_ABSEN': 1}
                            for c in groups.values()))

    def test_streaming_preserves_assignments_across_batch_boundaries(self):
        start, end = date(2026, 8, 3), date(2026, 8, 7)
        whole = generate_jatim(start, end, 275)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'jatim.gz'
            counts = write_dataset(path, start, end, 275, profile=PROFILE)
            streamed = {}
            for table, rows in read_dataset(path):
                streamed.setdefault(table, []).extend(rows)
            # Compare all serialized values, including globally aligned IDs.
            expected = json.loads(json.dumps(whole, default=lambda value: value.isoformat()))
            self.assertEqual(streamed, expected)
            self.assertEqual(counts['m_departemen'], len(DEPARTMENTS))
            with gzip.open(path, 'rt') as stream:
                self.assertEqual(json.loads(next(stream))['profile']['name'], PROFILE)
            with self.assertRaises(FileExistsError):
                write_dataset(path, start, end, 275, profile=PROFILE)

    def test_seed_is_reproducible_and_changes_events(self):
        start = date(2026, 8, 3)
        first = generate_jatim(start, start, 250, seed=42)
        self.assertEqual(first, generate_jatim(start, start, 250, seed=42))
        self.assertNotEqual(first['t_checkinout'], generate_jatim(start, start, 250, seed=43)['t_checkinout'])

    def test_profile_rejects_dates_outside_supported_calendar(self):
        with self.assertRaises(ValueError):
            generate_jatim(date(2026, 8, 1), date(2026, 9, 1))
        with self.assertRaises(ValueError):
            generate_jatim(date(2026, 8, 1), date(2026, 8, 31), 100,
                           employee_offset=200, total_employees=250)
