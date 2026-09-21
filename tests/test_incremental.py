import unittest
from contextlib import ExitStack
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from etl.pipeline import incremental as pipeline
from etl.transform import incremental as transform
from etl.dummy.generate import generate_dataset
from etl.transform.pegawai import transform_pegawai
from etl.transform.calendar import transform_calendar
from etl.transform.jadwal_kerja import transform_jadwal_kerja

DAY = date(2026, 9, 1)
STAMP = datetime(2026, 9, 1, 12)


def permission(employee=1, start=DAY, end=DAY, approved=True):
    return dict(perizinan_id=7, pegawai_id=employee, tanggal_mulai=start,
                tanggal_selesai=end, is_valid_leave=approved)


class ImpactTests(unittest.TestCase):
    def test_new_event_deduplicates_same_employee_day(self):
        events = [dict(pegawai_id=1, tanggal=DAY)] * 3
        self.assertEqual(transform.build_affected_employee_days(events, [], []), {(1, DAY)})

    def test_pending_to_approved_and_revocation(self):
        pending, approved = permission(approved=False), permission()
        for old, new in [(pending, approved), (approved, pending)]:
            self.assertEqual(transform.build_affected_employee_days([], [old], [new]), {(1, DAY)})

    def test_moved_employee_and_dates_cleans_old_coverage(self):
        old = permission(end=DAY + timedelta(days=2))
        new = permission(employee=2, start=DAY + timedelta(days=4), end=DAY + timedelta(days=5))
        self.assertEqual(transform.build_affected_employee_days([], [old], [new]),
            {(1, DAY + timedelta(days=i)) for i in range(3)} |
            {(2, DAY + timedelta(days=i)) for i in (4, 5)})

    def test_rejected_new_dates_have_no_coverage(self):
        self.assertEqual(transform.build_affected_employee_days([], [permission()],
            [permission(start=DAY + timedelta(days=1), end=DAY + timedelta(days=2), approved=False)]),
            {(1, DAY)})


class RecomputeTests(unittest.TestCase):
    def setUp(self):
        tables = generate_dataset(DAY, DAY, 10)
        self.people = transform_pegawai(tables['m_pegawai'])
        self.calendar = transform_calendar([], DAY, DAY)
        self.schedules = transform_jadwal_kerja(tables['m_jadwal'], tables['m_shift'])
        self.events = [dict(id=i, pegawai_id=1, departemen=1, work_code=1,
            is_wfh=0, created_at=STAMP.replace(hour=hour), updated_at=STAMP)
            for i, hour in [(1, 8), (2, 17)]]
        self.leaves = []

    def query(self, conn, sql, params):
        if 'dim_pegawai' in sql:
            return [p for p in self.people if p['pegawai_id'] in params[0]]
        if 'dim_calendar' in sql:
            return self.calendar
        if 't_checkinout' in sql:
            return self.events
        if 't_libur_shift' in sql:
            return []
        if 't_perizinan' in sql:
            return self.leaves
        raise AssertionError(sql)

    def compute(self):
        with patch.object(transform, 'fetch_rows', side_effect=self.query), patch.object(
                transform, 'extract_schedule', return_value=self.schedules):
            return transform.recompute_employee_days(MagicMock(), MagicMock(), {(1, DAY)})

    def test_recompute_reads_full_day_not_only_new_checkout(self):
        facts = self.compute()
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]['jumlah_event'], 2)
        self.assertTrue(facts[0]['has_masuk'])
        self.assertTrue(facts[0]['has_pulang'])
        self.assertIsNone(facts[0]['perizinan_id'])

    def test_permission_without_attendance_still_builds_employee_day(self):
        self.events = []
        self.leaves = [dict(source_perizinan_id=7, pegawai_id=1, tanggal=DAY)]
        fact = self.compute()[0]
        self.assertTrue(fact['has_valid_leave'])
        self.assertEqual(fact['perizinan_id'], 7)
        self.assertEqual(fact['jumlah_event'], 0)

    def test_multiple_approved_permissions_preserve_existing_rejection_rule(self):
        self.leaves = [dict(source_perizinan_id=i, pegawai_id=1, tanggal=DAY) for i in (7, 8)]
        with self.assertRaisesRegex(ValueError, 'Multiple valid leave'):
            self.compute()

    def test_missing_calendar_fails_before_loading(self):
        self.calendar = []
        with self.assertRaisesRegex(ValueError, 'Missing employee/calendar'):
            self.compute()


class PipelineTests(unittest.TestCase):
    def mocks(self, stack, states=None):
        defaults = dict(get_pipeline_state=None, high_watermarks=(20, STAMP),
            checkinout_changes=[], perizinan_changes=[], prepare_permissions=[],
            fetch_rows=[], iter_recomputed_employee_days=[], load_fact_perizinan=0,
            load_fact_kehadiran=(0, 0), upsert_pipeline_state=None)
        mocks = {name: stack.enter_context(patch.object(pipeline, name, return_value=value))
                 for name, value in defaults.items()}
        if states:
            mocks['get_pipeline_state'].side_effect = states
        return mocks

    def states(self):
        return [('fact_kehadiran', 't_checkinout', 'id', None, 10, STAMP),
                ('fact_perizinan', 't_perizinan', 'timestamp', STAMP, None, STAMP)]

    def test_bootstrap_replays_from_zero_and_preview_does_not_write(self):
        with ExitStack() as stack:
            mocks = self.mocks(stack)
            report = pipeline.run_incremental_fact_pipeline(MagicMock(), MagicMock())
            self.assertTrue(report['bootstrap'])
            self.assertEqual(mocks['checkinout_changes'].call_args.args[1:], (0, 20))
            self.assertIsNone(mocks['perizinan_changes'].call_args.args[1])
            for name in ('load_fact_perizinan', 'load_fact_kehadiran', 'upsert_pipeline_state'):
                mocks[name].assert_not_called()

    def test_overlap_and_advance_past_irrelevant_events(self):
        with ExitStack() as stack:
            mocks = self.mocks(stack, self.states())
            target = MagicMock()
            pipeline.run_incremental_fact_pipeline(MagicMock(), target, apply=True)
            self.assertEqual(mocks['checkinout_changes'].call_args.args[1:], (10, 20))
            self.assertEqual(mocks['perizinan_changes'].call_args.args[1], STAMP - timedelta(minutes=5))
            self.assertEqual(mocks['upsert_pipeline_state'].call_args_list[0].kwargs['last_watermark_id'], 20)
            target.commit.assert_not_called()

    def test_reconcile_replays_existing_sources(self):
        with ExitStack() as stack:
            mocks = self.mocks(stack, self.states())
            pipeline.run_incremental_fact_pipeline(MagicMock(), MagicMock(), reconcile=True)
            self.assertEqual(mocks['checkinout_changes'].call_args.args[1], 0)
            self.assertIsNone(mocks['perizinan_changes'].call_args.args[1])

    def test_failure_does_not_advance_checkpoints(self):
        with ExitStack() as stack:
            mocks = self.mocks(stack)
            mocks['iter_recomputed_employee_days'].side_effect = ValueError('invalid facts')
            with self.assertRaisesRegex(ValueError, 'invalid facts'):
                pipeline.run_incremental_fact_pipeline(MagicMock(), MagicMock(), apply=True)
            mocks['upsert_pipeline_state'].assert_not_called()

    def test_wrapper_rolls_back_and_persists_failure_log(self):
        source, target = MagicMock(), MagicMock()
        with patch.object(pipeline, 'get_oltp_connection', return_value=source), patch.object(
                pipeline, 'get_olap_connection', return_value=target), patch.object(
                pipeline, 'start_run', return_value=99), patch.object(
                pipeline, 'run_incremental_fact_pipeline', side_effect=ValueError('bad batch')), patch.object(
                pipeline, 'finish_run_failed') as failed, patch.object(pipeline, 'finish_run_success') as success:
            with self.assertRaisesRegex(ValueError, 'bad batch'):
                pipeline.execute_pipeline(apply=True)
            target.rollback.assert_called_once()
            failed.assert_called_once_with(target, 99, 'bad batch')
            success.assert_not_called()
            self.assertEqual(target.commit.call_count, 2)
            source.close.assert_called_once()
            target.close.assert_called_once()

    def test_regression_and_partial_checkpoint_fail(self):
        for states in [self.states()[:1] + [None],
                       [('fact_kehadiran', 't_checkinout', 'id', None, 30, STAMP), self.states()[1]]]:
            with ExitStack() as stack:
                mocks = self.mocks(stack, states)
                with self.assertRaises(ValueError):
                    pipeline.run_incremental_fact_pipeline(MagicMock(), MagicMock(), apply=True)
                mocks['upsert_pipeline_state'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
