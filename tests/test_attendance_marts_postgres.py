"""Opt-in isolated mart tests. Dedicated test schemas are rolled back or removed."""
import os
from pathlib import Path
import unittest
import uuid
from etl.connectors.olap import get_olap_connection
from etl.control.locking import acquire_pipeline_lock


@unittest.skipUnless(os.getenv('RUN_POSTGRES_TESTS') == '1','Set RUN_POSTGRES_TESTS=1')
class MartTransactionTests(unittest.TestCase):
    def setUp(self):
        self.conn=get_olap_connection()
        acquire_pipeline_lock(self.conn,transaction=True)
        self.src='mart_test_src_'+uuid.uuid4().hex[:10]
        self.dst='mart_test_dst_'+uuid.uuid4().hex[:10]
        self.conn.execute(f'CREATE SCHEMA {self.src}')
        self.conn.execute(f'CREATE SCHEMA {self.dst}')
        self.conn.execute(f'CREATE TABLE {self.src}.fact_kehadiran AS SELECT * FROM public.fact_kehadiran WITH NO DATA')
        self.conn.execute(f'CREATE TABLE {self.src}.dim_departemen AS SELECT * FROM public.dim_departemen')
        for path in ['sql/dashboard/views.sql','sql/dashboard/marts.sql']:
            script=Path(path).read_text().replace('public.',self.src+'.').replace('analytics.',self.dst+'.').replace('SCHEMA IF NOT EXISTS analytics',f'SCHEMA IF NOT EXISTS {self.dst}').replace('search_path=pg_catalog,analytics',f'search_path=pg_catalog,{self.dst}')
            self.conn.execute(script)
        self.conn.execute(f'''INSERT INTO {self.src}.fact_kehadiran
          SELECT * FROM public.fact_kehadiran WHERE tanggal='2026-08-03'
          AND status_kehadiran='HADIR' AND is_terlambat LIMIT 1''')
        self.employee=self.conn.execute(f'SELECT pegawai_id FROM {self.src}.fact_kehadiran').fetchone()[0]
        self.flush()

    def tearDown(self):
        self.conn.rollback()
        if getattr(self,'committed_fixture',False):
            self.conn.execute(f'DROP SCHEMA {self.dst} CASCADE')
            self.conn.execute(f'DROP SCHEMA {self.src} CASCADE')
            self.conn.commit()
        self.conn.close()

    def flush(self):
        self.conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
        self.conn.execute('SET CONSTRAINTS ALL DEFERRED')
        self.assertEqual(self.conn.execute(f'SELECT count(*) FROM {self.dst}.mart_dirty_dates').fetchone()[0],0)
        self.assertFalse(self.conn.execute(f'''SELECT EXISTS (
          (SELECT * FROM {self.dst}.attendance_department_daily EXCEPT ALL SELECT * FROM {self.dst}.mart_attendance_department_daily)
          UNION ALL
          (SELECT * FROM {self.dst}.mart_attendance_department_daily EXCEPT ALL SELECT * FROM {self.dst}.attendance_department_daily))''').fetchone()[0])

    def test_insert_is_deferred_then_published(self):
        before=self.conn.execute(f'SELECT generation FROM {self.dst}.mart_refresh_state').fetchone()[0]
        self.conn.execute(f"UPDATE {self.src}.fact_kehadiran SET menit_terlambat=menit_terlambat+10")
        self.assertEqual(self.conn.execute(f'SELECT generation FROM {self.dst}.mart_refresh_state').fetchone()[0],before)
        self.flush()
        self.assertEqual(self.conn.execute(f'SELECT generation FROM {self.dst}.mart_refresh_state').fetchone()[0],before+1)
        self.assertEqual(self.conn.execute(f'SELECT sum(late_minutes) FROM {self.dst}.mart_attendance_lateness_daily').fetchone(),self.conn.execute(f'SELECT sum(late_minutes) FROM {self.dst}.attendance_daily').fetchone())

    def test_date_move_department_move_delete_and_truncate(self):
        other=self.conn.execute(f'SELECT departemen_id FROM {self.src}.dim_departemen WHERE departemen_id<>(SELECT departemen_id FROM {self.src}.fact_kehadiran) LIMIT 1').fetchone()[0]
        self.conn.execute(f"UPDATE {self.src}.fact_kehadiran SET tanggal='2026-08-04',departemen_id=%s",(other,))
        self.flush()
        self.assertEqual(str(self.conn.execute(f'SELECT tanggal FROM {self.dst}.mart_attendance_department_daily').fetchone()[0]),'2026-08-04')
        self.conn.execute(f'DELETE FROM {self.src}.fact_kehadiran');self.flush()
        self.assertEqual(self.conn.execute(f'SELECT count(*) FROM {self.dst}.mart_attendance_composition_daily').fetchone()[0],0)
        self.conn.execute(f"INSERT INTO {self.src}.fact_kehadiran SELECT * FROM public.fact_kehadiran WHERE pegawai_id=%s AND tanggal='2026-08-03'",(self.employee,));self.flush()
        self.conn.execute(f'TRUNCATE {self.src}.fact_kehadiran');self.flush()
        self.assertEqual(self.conn.execute(f'SELECT count(*) FROM {self.dst}.mart_attendance_department_daily').fetchone()[0],0)

    def test_noop_does_not_refresh_and_updates_coalesce(self):
        before=self.conn.execute(f'SELECT generation FROM {self.dst}.mart_refresh_state').fetchone()[0]
        self.conn.execute(f'UPDATE {self.src}.dim_departemen SET nama_departemen=nama_departemen WHERE false')
        self.conn.execute(f'UPDATE {self.src}.fact_kehadiran SET menit_terlambat=menit_terlambat WHERE false')
        self.flush()
        self.assertEqual(self.conn.execute(f'SELECT generation FROM {self.dst}.mart_refresh_state').fetchone()[0],before)
        for _ in range(3):self.conn.execute(f'UPDATE {self.src}.fact_kehadiran SET menit_terlambat=menit_terlambat+1')
        self.flush()
        self.assertEqual(self.conn.execute(f'SELECT generation FROM {self.dst}.mart_refresh_state').fetchone()[0],before+1)

    def test_dimension_rename_refreshes_history(self):
        self.conn.execute(f"UPDATE {self.src}.dim_departemen SET nama_departemen='Renamed test department'")
        self.flush()
        self.assertEqual(self.conn.execute(f'SELECT nama_departemen FROM {self.dst}.mart_attendance_department_daily').fetchone()[0],'Renamed test department')

    def test_empty_and_unevaluated_kpis_remain_null(self):
        metrics='100.0*sum(present_days)/nullif(sum(expected_days),0),100.0*sum(ontime_days)/nullif(sum(evaluated_days),0),sum(late_minutes)/nullif(sum(late_days),0)'
        table=f'{self.dst}.mart_attendance_department_daily'
        self.assertEqual(self.conn.execute(f'SELECT {metrics} FROM {table} WHERE false').fetchone(),(None,None,None))
        self.conn.execute(f'UPDATE {self.src}.fact_kehadiran SET menit_terlambat=NULL')
        self.flush()
        self.assertEqual(self.conn.execute(f'SELECT {metrics} FROM {table}').fetchone(),(100,None,None))
        self.conn.execute(f'UPDATE {self.src}.fact_kehadiran SET is_expected_workday=false')
        self.flush()
        self.assertEqual(self.conn.execute(f'SELECT {metrics} FROM {table}').fetchone(),(None,None,None))

    def test_real_commit_visibility_and_failed_commit(self):
        self.conn.commit()
        self.committed_fixture=True
        with get_olap_connection() as observer:
            observer.execute('SET TRANSACTION READ ONLY')
            query=f'SELECT sum(late_minutes) FROM {self.dst}.mart_attendance_lateness_daily'
            old=observer.execute(query).fetchone()[0]
            self.conn.execute(f'UPDATE {self.src}.fact_kehadiran SET menit_terlambat=menit_terlambat+10')
            self.assertEqual(observer.execute(query).fetchone()[0],old)
            self.conn.commit()
            self.assertEqual(observer.execute(query).fetchone()[0],old+10)
            self.conn.execute(f"UPDATE {self.src}.fact_kehadiran SET status_kehadiran='INVALID',is_expected_workday=true")
            with self.assertRaisesRegex(Exception,'KPI components'):
                self.conn.commit()
            self.conn.rollback()
            self.assertEqual(observer.execute(query).fetchone()[0],old+10)
            self.assertEqual(observer.execute(f'SELECT status_kehadiran FROM {self.src}.fact_kehadiran').fetchone()[0],'HADIR')

    def test_failed_validation_rolls_back_fact_and_mart(self):
        before=self.conn.execute(f'SELECT * FROM {self.dst}.mart_refresh_state').fetchone()
        self.conn.execute('SAVEPOINT before_invalid')
        self.conn.execute(f"UPDATE {self.src}.fact_kehadiran SET status_kehadiran='INVALID',is_expected_workday=true")
        with self.assertRaisesRegex(Exception,'KPI components'):
            self.conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
        self.conn.execute('ROLLBACK TO SAVEPOINT before_invalid')
        self.assertEqual(self.conn.execute(f'SELECT * FROM {self.dst}.mart_refresh_state').fetchone(),before)
        self.assertEqual(self.conn.execute(f'SELECT status_kehadiran FROM {self.src}.fact_kehadiran').fetchone()[0],'HADIR')
        self.flush()

if __name__=='__main__':unittest.main()
