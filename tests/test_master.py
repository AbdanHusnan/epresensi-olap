import unittest
from contextlib import ExitStack
from datetime import date
from unittest.mock import MagicMock, patch

from etl.pipeline import master

DAY = date(2026, 8, 3)


class MasterTests(unittest.TestCase):
    def test_stage_order_and_read_only_preview(self):
        for apply in (False, True):
            with self.subTest(apply=apply), ExitStack() as stack:
                source, target = MagicMock(), MagicMock()
                target.execute.return_value.fetchone.return_value = (DAY, DAY)
                base = {name: [{}] for name in master.DIMENSIONS}
                base['fact_perizinan'] = [{'tanggal_mulai': DAY, 'tanggal_selesai': DAY}]
                stack.enter_context(patch.object(master, 'prepare_references', return_value=(base, [], [])))
                stack.enter_context(patch.object(master, 'transform_calendar', return_value=[{}]))
                stack.enter_context(patch.object(master, 'prepare_replacement', return_value={'fact_kehadiran': [{}]}))
                calls = []
                loaders = {}
                for name in (*master.DIMENSIONS, 'dim_calendar', 'fact_perizinan', 'fact_kehadiran'):
                    def load(conn, rows, name=name):
                        calls.append(name)
                        return len(rows) if name == 'fact_perizinan' else (len(rows), 0)
                    loaders[name] = load
                stack.enter_context(patch.dict(master.LOADERS, loaders))
                def delta(*args, **kwargs):
                    calls.append('incremental')
                    return dict(attendance_changes=2, permission_rows_read=1,
                                attendance_inserted=1, attendance_updated=2)
                stack.enter_context(patch.object(master, 'run_incremental_fact_pipeline', side_effect=delta))
                report = master.run_master_pipeline(source, target, start_date=DAY, end_date=DAY, apply=apply)
                self.assertEqual(calls, [*master.DIMENSIONS, 'dim_calendar', 'incremental',
                                        'fact_perizinan', 'fact_kehadiran'] if apply else [])
                self.assertEqual(report['dry_run'], not apply)
                target.commit.assert_not_called()

    def execute_mocks(self, stack):
        source, target = MagicMock(), MagicMock()
        target.execute.return_value.fetchone.return_value = (True,)
        stack.enter_context(patch.object(master, 'get_oltp_connection', return_value=source))
        stack.enter_context(patch.object(master, 'get_olap_connection', return_value=target))
        mocks = {}
        for name, value in [('start_run', 42), ('finish_run_success', None),
                            ('finish_run_failed', None), ('run_master_pipeline',
                             dict(rows_prepared=8, rows_inserted=3, rows_updated=2))]:
            mocks[name] = stack.enter_context(patch.object(master, name, return_value=value))
        events = MagicMock()
        events.attach_mock(target, 'target')
        for name, mock in mocks.items():
            events.attach_mock(mock, name)
        return source, target, mocks, events

    def test_success_commit_boundary(self):
        with ExitStack() as stack:
            source, target, mocks, events = self.execute_mocks(stack)
            result = master.execute_pipeline(start_date=DAY, end_date=DAY, apply=True)
            names = [c[0] for c in events.mock_calls]
            commits = [i for i, name in enumerate(names) if name == 'target.commit']
            self.assertEqual(len(commits), 2)
            self.assertLess(commits[0], names.index('run_master_pipeline'))
            self.assertGreater(commits[1], names.index('finish_run_success'))
            self.assertEqual(result['run_id'], 42)
            target.rollback.assert_not_called()
            mocks['finish_run_failed'].assert_not_called()
            source.close.assert_called_once()
            target.close.assert_called_once()

    def test_rollback_precedes_failure_log(self):
        with ExitStack() as stack:
            _, target, mocks, events = self.execute_mocks(stack)
            mocks['run_master_pipeline'].side_effect = RuntimeError('daily failed')
            with self.assertRaisesRegex(RuntimeError, 'daily failed'):
                master.execute_pipeline(start_date=DAY, end_date=DAY, apply=True)
            names = [c[0] for c in events.mock_calls]
            self.assertLess(names.index('target.rollback'), names.index('finish_run_failed'))
            mocks['finish_run_failed'].assert_called_once_with(target, 42, 'daily failed')
            mocks['finish_run_success'].assert_not_called()

    def test_lock_contention(self):
        with ExitStack() as stack:
            _, target, mocks, _ = self.execute_mocks(stack)
            target.execute.return_value.fetchone.return_value = (False,)
            with self.assertRaisesRegex(RuntimeError, 'Another master'):
                master.execute_pipeline(start_date=DAY, end_date=DAY, apply=True)
            mocks['start_run'].assert_not_called()
            mocks['run_master_pipeline'].assert_not_called()
            target.commit.assert_not_called()

    def test_preview_transaction_is_read_only(self):
        with ExitStack() as stack:
            _, target, mocks, _ = self.execute_mocks(stack)
            master.execute_pipeline(start_date=DAY, end_date=DAY)
            target.execute.assert_any_call('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            target.commit.assert_not_called()
            target.rollback.assert_called_once()
            mocks['start_run'].assert_not_called()

    def test_invalid_options_fail_before_connecting(self):
        with patch.object(master, 'get_oltp_connection') as connect:
            with self.assertRaises(ValueError):
                master.execute_pipeline(start_date=DAY, end_date=DAY, batch_size=0)
            connect.assert_not_called()

    def test_target_connection_failure_closes_source(self):
        source = MagicMock()
        with patch.object(master, 'get_oltp_connection', return_value=source), patch.object(
                master, 'get_olap_connection', side_effect=RuntimeError('offline')):
            with self.assertRaisesRegex(RuntimeError, 'offline'):
                master.execute_pipeline(start_date=DAY, end_date=DAY)
        source.close.assert_called_once()
