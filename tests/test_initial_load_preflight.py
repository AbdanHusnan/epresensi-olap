import unittest
from datetime import date
from unittest.mock import MagicMock, patch
from contextlib import ExitStack

from etl.pipeline import initial_load as load
from etl.pipeline.initial_load_preflight import check_columns, check_requirements
from etl.dummy.generate import generate_dataset


class PreflightTests(unittest.TestCase):
    def test_reports_all_missing_schema_requirements(self):
        conn = MagicMock()
        conn.execute.return_value = [('m_pegawai', 'id')]
        errors = check_columns(conn, 'public', {'m_pegawai': 'id nip', 'm_shift': 'id'}, 'OLTP')
        self.assertEqual(len(errors), 2)
        self.assertIn('nip', errors[0])
        self.assertIn('m_shift', errors[1])

    @patch('etl.pipeline.initial_load_preflight.check_columns', return_value=[])
    def test_empty_source_blocks_load(self, _):
        source = MagicMock()
        source.execute.return_value.fetchone.return_value = (0,)
        report = check_requirements(source, MagicMock(), date(2026, 3, 1), date(2026, 3, 3))
        self.assertFalse(report['ready'])
        self.assertEqual(len(report['errors']), 6)
        self.assertEqual(report['expected_employee_days'], 0)

    @patch('etl.pipeline.initial_load_preflight.check_columns', return_value=[])
    def test_empty_transactions_allow_master_load_with_warning(self, _):
        source = MagicMock()
        # Source contract order: six master tables, then holiday and transaction/user tables.
        source.execute.return_value.fetchone.side_effect = [(2,)] * 6 + [(0,)] * 5
        report = check_requirements(source, MagicMock(), date(2026, 3, 1), date(2026, 3, 3))
        self.assertTrue(report['ready'])
        self.assertEqual(report['expected_employee_days'], 6)
        self.assertTrue(report['warnings'])

    def test_preview_validates_users_and_counts_every_target(self):
        start = date(2026, 3, 1)
        tables = generate_dataset(start, start, 10)
        mappings = {
            'extract_pegawai': 'm_pegawai', 'extract_departemen': 'm_departemen',
            'extract_jadwal': 'm_jadwal', 'extract_shift': 'm_shift',
            'extract_jenis_izin': 'm_jenis_ijin', 'extract_tipe_izin': 'm_tipe_ijin',
            'extract_perizinan': 't_perizinan', 'extract_hari_libur': 'm_hari_libur',
            'extract_attendance': 't_checkinout', 'extract_libur_shift': 't_libur_shift',
        }
        source, target = MagicMock(), MagicMock()
        cursor = source.cursor.return_value.__enter__.return_value
        with ExitStack() as stack:
            for function, table in mappings.items():
                stack.enter_context(patch.object(load, function, return_value=tables[table]))
            cursor.fetchmany.side_effect = [[(1,), (None,)], []]
            report = load.run_initial_load(source, target, start, start)
            self.assertEqual(report['rows']['analytical_user'], 2)
            self.assertEqual(set(report['rows']), set(load.RESET_TABLES))
            target.execute.assert_not_called()
            cursor.fetchmany.side_effect = [[(99999,)]]
            with self.assertRaisesRegex(ValueError, 'unknown employees'):
                load.run_initial_load(source, target, start, start, apply=True)
            target.execute.assert_not_called()
            tables['m_pegawai'][0]['departemen'] = 99999
            with self.assertRaisesRegex(ValueError, 'unknown departments'):
                load.prepare_references(source)
