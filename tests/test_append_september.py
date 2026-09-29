import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from collections import Counter
from contextlib import ExitStack
from datetime import date, timedelta
from unittest.mock import patch

from psycopg import sql

from etl.connectors.olap import get_olap_connection
from etl.dummy.append_september import (
    START, COLUMNS, MASTER_TABLES, append_artifact, expected_outcomes,
    generate, generate_day, fingerprint,
)
from etl.dummy.jatim import generate_jatim
from etl.dummy.seed import copy_rows
from etl.pipeline import initial_load
from etl.pipeline.incremental import run_incremental_fact_pipeline
from etl.load.calendar import load_calendar
from etl.transform.calendar import transform_calendar
from test_initial_load_postgres import ScopedConnection


def fixture(employees=100):
    tables = generate_jatim(date(2026, 8, 1), date(2026, 8, 31), employees)
    shifts = {r['id']: r for r in tables['m_shift']}
    refs = {
        'employees': [dict(id=p['id'], nama=p['nama'], departemen=p['departemen'], user_id=p['id'])
                      for p in tables['m_pegawai']],
        'schedules': [dict(departemen_id=shifts[j['jenis']]['departemen_id'], hari=j['hari'],
                           jam_masuk=j['jam_masuk'], jam_keluar=j['jam_keluar'], is_flexible=0)
                      for j in tables['m_jadwal']],
        'leave_types': [dict(id=r['id'], kode=r['kode'], tipe_id=r['tipe_id'])
                        for r in tables['m_jenis_ijin']],
    }
    return tables, refs


class SeptemberTransformTests(unittest.TestCase):
    def test_entire_month_through_existing_transforms(self):
        tables, refs = fixture()
        for table in COLUMNS:
            tables[table] = []
        categories = Counter()
        for offset in range(30):
            day = START + timedelta(days=offset)
            batch, counts = generate_day(refs, day, 202609)
            categories.update(counts)
            for table in COLUMNS:
                for row in batch[table]:
                    tables[table].append(dict(id=len(tables[table]) + 1, **row))
        mapping = {
            'extract_pegawai': 'm_pegawai', 'extract_departemen': 'm_departemen',
            'extract_jadwal': 'm_jadwal', 'extract_shift': 'm_shift',
            'extract_jenis_izin': 'm_jenis_ijin', 'extract_tipe_izin': 'm_tipe_ijin',
            'extract_perizinan': 't_perizinan', 'extract_hari_libur': 'm_hari_libur',
            'extract_attendance': 't_checkinout', 'extract_libur_shift': 't_libur_shift',
        }
        with ExitStack() as stack:
            for function, table in mapping.items():
                stack.enter_context(patch.object(initial_load, function, return_value=tables[table]))
            result = initial_load.prepare_replacement(None, START, date(2026, 9, 30))
        facts = result['fact_kehadiran']
        self.assertEqual(Counter(r['status_kehadiran'] for r in facts),
                         {'HADIR': 1804, 'IZIN': 264, 'TIDAK_ABSEN': 132, 'NON_WORKING_DAY': 800})
        self.assertEqual(sum(r['is_wfh'] for r in facts), 418)
        self.assertEqual(sum(r['is_terlambat'] for r in facts), 440)
        self.assertEqual(sum(r['is_pulang_awal'] for r in facts), 198)
        self.assertEqual(sum(r['status_kehadiran'] == 'HADIR' and not r['is_complete_attendance'] for r in facts), 88)
        self.assertEqual(sum(r['jumlah_event'] for r in facts), 3520)
        self.assertEqual(Counter(r['status_pengajuan'] for r in result['fact_perizinan']),
                         {'APPROVED': 264, 'PENDING': 44, 'REJECTED': 22})
        self.assertEqual(Counter(r['jenis_izin_id'] for r in result['fact_perizinan']),
                         {1: 110, 2: 88, 3: 132})
        self.assertEqual(expected_outcomes(categories, 100)['incremental_only_new_attendance_facts'], 2068)

    def test_reuses_noncontiguous_identities_and_is_reproducible(self):
        _, refs = fixture()
        for p in refs['employees']:
            p['id'] = p['id'] * 7 + 1000
            p['user_id'] = p['user_id'] * 11 + 9000
            p['nama'] = f"Existing {p['id']}"
        first, _ = generate_day(refs, START, 10)
        self.assertEqual((first, _), generate_day(refs, START, 10))
        self.assertNotEqual(first, generate_day(refs, START, 11)[0])
        people = {p['id']: p for p in refs['employees']}
        for table, records in first.items():
            for r in records:
                p = people[r['pegawai_id']]
                self.assertEqual(r['departemen'], p['departemen'])
                if table == 't_perizinan':
                    self.assertEqual((r['nama'], r['user_id']), (p['nama'], p['user_id']))


@unittest.skipUnless(os.getenv('RUN_POSTGRES_TESTS') == '1', 'Set RUN_POSTGRES_TESTS=1')
class SeptemberPostgresTests(unittest.TestCase):
    def test_atomic_append_preservation_duplicate_guard_and_real_incremental(self):
        token = uuid.uuid4().hex[:12]
        src, dst, ctl = [f'sept_test_{token}_{suffix}' for suffix in ('src', 'dst', 'ctl')]
        source_raw, target_raw = get_olap_connection(), get_olap_connection()
        try:
            for conn, schema in ((source_raw, src), (target_raw, dst), (target_raw, ctl)):
                conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            source, target = ScopedConnection(source_raw, src, ctl), ScopedConnection(target_raw, dst, ctl)
            source.execute(Path('etl/dummy/source.sql').read_text())
            for table in COLUMNS:
                source.execute(sql.SQL('CREATE SEQUENCE {}').format(sql.Identifier(table + '_id_seq')))
                source.execute(sql.SQL('ALTER TABLE {} ALTER COLUMN id SET DEFAULT nextval({})').format(
                    sql.Identifier(table), sql.Literal(f'{src}.{table}_id_seq')))
            tables, _ = fixture()
            source.execute("INSERT INTO m_previleges(id,previleges) VALUES(1,'Existing')")
            for table, records in tables.items():
                copy_rows(source, table, records)
            for table in initial_load.RESET_TABLES:
                target_raw.execute(sql.SQL('CREATE TABLE {} (LIKE {} INCLUDING ALL)').format(
                    sql.Identifier(dst, table), sql.Identifier('public', table)))
            for table in ('pipeline_runs', 'pipeline_state'):
                target_raw.execute(sql.SQL('CREATE TABLE {} (LIKE {} INCLUDING ALL)').format(
                    sql.Identifier(ctl, table), sql.Identifier('etl_control', table)))
            target.execute('ALTER TABLE etl_control.pipeline_runs ALTER COLUMN run_id DROP DEFAULT')
            target.execute('ALTER TABLE etl_control.pipeline_runs ALTER COLUMN run_id ADD GENERATED BY DEFAULT AS IDENTITY')
            initial_load.run_initial_load(source, target, date(2026, 8, 1), date(2026, 8, 31), apply=True)
            run_incremental_fact_pipeline(source, target, apply=True)
            load_calendar(target, transform_calendar([], START, date(2026, 9, 30)))
            masters = {t: fingerprint(source, t) for t in MASTER_TABLES}
            old_counts = {t: source.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in COLUMNS}
            with tempfile.TemporaryDirectory() as directory:
                artifact = Path(directory) / 'september.gz'
                generate(source, artifact)
                corrupt = Path(directory) / 'corrupt.gz'
                with gzip.open(artifact, 'rt') as incoming, gzip.open(corrupt, 'wt') as outgoing:
                    for line in incoming:
                        if not json.loads(line).get('complete'):
                            outgoing.write(line)
                source.execute('SAVEPOINT before_corrupt')
                with self.assertRaisesRegex(ValueError, 'Incomplete artifact'):
                    append_artifact(source, corrupt)
                source.execute('ROLLBACK TO SAVEPOINT before_corrupt')
                self.assertEqual(old_counts, {t: source.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in COLUMNS})
                result = append_artifact(source, artifact)
                self.assertEqual(result['inserted'], {'t_checkinout': 3520, 't_perizinan': 330})
                self.assertEqual(masters, {t: fingerprint(source, t) for t in MASTER_TABLES})
                with self.assertRaisesRegex(ValueError, 'already contains'):
                    append_artifact(source, artifact)
                # Real incremental applies only affected keys. It must not invent
                # no-event/weekend facts or count pending/rejected leave as approved.
                run_incremental_fact_pipeline(source, target, apply=True, chunk_size=101)
                actual = dict(target.execute("SELECT status_kehadiran,count(*) FROM fact_kehadiran WHERE tanggal >= '2026-09-01' GROUP BY status_kehadiran").fetchall())
                self.assertEqual(actual, {'HADIR': 1804, 'IZIN': 264})
                self.assertEqual(target.execute("SELECT count(*) FROM fact_perizinan WHERE tanggal_mulai >= '2026-09-01'").fetchone()[0], 330)
                replay = run_incremental_fact_pipeline(source, target, apply=True)
                self.assertEqual(replay['attendance_changes'], 0)
                self.assertEqual(replay['attendance_inserted'], 0)
        finally:
            source_raw.rollback()
            target_raw.rollback()
            source_raw.close()
            target_raw.close()
