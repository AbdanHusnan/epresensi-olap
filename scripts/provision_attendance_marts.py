"""Install and backfill atomic attendance marts, preserving the ordinary source views."""
import argparse
import json
from pathlib import Path
from etl.connectors.olap import get_olap_connection
from etl.control.locking import acquire_pipeline_lock


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        print('Preview: install three aggregate marts, transactional change tracking, and backfill/validate all dates. Use --apply.')
        return
    with get_olap_connection() as conn:
        acquire_pipeline_lock(conn,transaction=True)
        conn.execute("SET LOCAL lock_timeout='5s'")
        conn.execute("SET LOCAL statement_timeout='120s'")
        conn.execute(Path('sql/dashboard/marts.sql').read_text())
        conn.execute('''INSERT INTO analytics.mart_dirty_dates
          SELECT tanggal FROM public.fact_kehadiran
          UNION SELECT tanggal FROM analytics.mart_attendance_department_daily ON CONFLICT DO NOTHING''')
        dates=conn.execute('SELECT analytics.refresh_attendance_marts()').fetchone()[0]
        counts={k:conn.execute(f'SELECT count(*) FROM analytics.mart_attendance_{k}_daily').fetchone()[0]
                for k in ('department','composition','lateness')}
        # Compare every existing aggregate field in both directions before publication.
        mismatch=conn.execute('''SELECT EXISTS (
          (SELECT * FROM analytics.attendance_department_daily EXCEPT ALL SELECT * FROM analytics.mart_attendance_department_daily)
          UNION ALL
          (SELECT * FROM analytics.mart_attendance_department_daily EXCEPT ALL SELECT * FROM analytics.attendance_department_daily))''').fetchone()[0]
        if mismatch:raise RuntimeError('Mart differs from original aggregate view')
    print(json.dumps({'refreshed_dates':dates,'rows':counts,'aggregate_view_equal':True}))

if __name__=='__main__':main()
