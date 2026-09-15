import gzip
import json
import tempfile
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import patch

from etl.dummy.generate import generate_dataset, write_dataset
from etl.dummy.seed import read_dataset
from etl.pipeline import initial_load


class DummyInitialLoadTests(unittest.TestCase):
    def test_reproducible_batches_and_global_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.jsonl.gz'
            counts = write_dataset(path, date(2026, 3, 1), date(2026, 3, 31), 205)
            seen = {}
            for table, rows in read_dataset(path):
                ids = seen.setdefault(table, set())
                self.assertFalse(ids.intersection(row['id'] for row in rows))
                ids.update(row['id'] for row in rows)
            self.assertEqual(len(seen['m_pegawai']), 205)
            self.assertEqual(counts['m_departemen'], 5)
            self.assertEqual({t: len(ids) for t, ids in seen.items()}, counts)
        first = generate_dataset(date(2026, 3, 1), date(2026, 3, 31), 1, employee_offset=100)
        second = generate_dataset(date(2026, 3, 1), date(2026, 3, 31), 1, employee_offset=100)
        self.assertEqual(first, second)
        self.assertEqual(first['m_pegawai'][0]['id'], 101)

    def test_truncated_dataset_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'broken.gz'
            with gzip.open(path, 'wt') as stream:
                stream.write(json.dumps({'format_version': 2, 'synthetic': True, 'employees': 100}) + '\n')
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                list(read_dataset(path))

    def test_generated_data_passes_existing_business_rules(self):
        start, end = date(2026, 3, 1), date(2026, 3, 31)
        tables = generate_dataset(start, end, 100)
        mappings = {
            'extract_pegawai': 'm_pegawai', 'extract_departemen': 'm_departemen',
            'extract_jadwal': 'm_jadwal', 'extract_shift': 'm_shift',
            'extract_jenis_izin': 'm_jenis_ijin', 'extract_tipe_izin': 'm_tipe_ijin',
            'extract_perizinan': 't_perizinan', 'extract_hari_libur': 'm_hari_libur',
            'extract_attendance': 't_checkinout', 'extract_libur_shift': 't_libur_shift',
        }
        from contextlib import ExitStack
        with ExitStack() as stack:
            for function, table in mappings.items():
                stack.enter_context(patch.object(initial_load, function, return_value=tables[table]))
            result = initial_load.prepare_replacement(None, start, end)
        facts = result['fact_kehadiran']
        self.assertEqual(len(facts), 3100)
        self.assertEqual(sum(r['jumlah_event'] for r in facts), len(tables['t_checkinout']))
        self.assertEqual(set(Counter(r['status_kehadiran'] for r in facts)),
                         {'HADIR', 'IZIN', 'TIDAK_ABSEN', 'NON_WORKING_DAY'})
        self.assertEqual({r['status_pengajuan'] for r in result['fact_perizinan']},
                         {'APPROVED', 'REJECTED', 'PENDING'})
        self.assertTrue(any(r['is_terlambat'] for r in facts))
        self.assertTrue(any(r['is_pulang_awal'] for r in facts))
        self.assertTrue(any(r['is_wfh'] for r in facts))
        self.assertTrue(any(r['jumlah_event'] == 1 for r in facts))

    def test_invalid_parameters(self):
        with self.assertRaises(ValueError):
            generate_dataset(date(2026, 4, 1), date(2026, 3, 1))
        with self.assertRaises(ValueError):
            generate_dataset(date(2026, 3, 1), date(2026, 3, 2), 0)


if __name__ == '__main__':
    unittest.main()
