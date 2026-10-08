"""Read-only source and target audit for the remaining dimension mapping."""
import json
from datetime import datetime
from pathlib import Path
from report_paths import report_path
from zoneinfo import ZoneInfo
import psycopg
from psycopg import sql
from dotenv import dotenv_values
ROOT = Path(__file__).resolve().parents[1]
TABLES = ['m_shift', 'm_jadwal', 'm_hari_libur', 'm_jenis_ijin', 'm_tipe_ijin']

def main():
    cfg = dotenv_values(ROOT / '.env')
    def connect(db):
        return psycopg.connect(host=cfg['OLAP_HOST'], port=cfg['OLAP_PORT'],
            user=cfg['OLAP_USER'], password=cfg['OLAP_PASSWORD'], dbname=db,
            options='-c default_transaction_read_only=on -c statement_timeout=60000')
    report = {'checked_at': datetime.now(ZoneInfo('Asia/Jakarta')).isoformat(),
              'source_database': 'dbabsen_restore', 'target_database': 'epresensi_analytics_hop_dev'}
    with connect('dbabsen_restore') as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        report['source_columns'] = c.execute("SELECT table_name,column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name=ANY(%s) ORDER BY table_name,ordinal_position", (TABLES,)).fetchall()
        report['counts'] = {t: c.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(t))).fetchone()[0] for t in TABLES}
        queries = {
            'shift_status': 'SELECT status,count(*) FROM m_shift GROUP BY 1 ORDER BY 1',
            'shift_flexible': 'SELECT is_flexible,count(*) FROM m_shift GROUP BY 1 ORDER BY 1',
            'shift_references': 'SELECT count(*) FILTER (WHERE s.departemen_id IS NULL) AS null_departemen, count(*) FILTER (WHERE s.departemen_id IS NOT NULL AND d.id IS NULL) AS orphan_departemen, count(*) FILTER (WHERE s.nama ~* \'regular|reguler\') AS regular FROM m_shift s LEFT JOIN m_departemen d ON d.id=s.departemen_id',
            'jadwal_days': 'SELECT hari,count(*) FROM m_jadwal GROUP BY 1 ORDER BY 1',
            'jadwal_quality': '''SELECT count(*) FILTER (WHERE s.id IS NULL) AS orphan_shift,
              count(*) FILTER (WHERE j.jam_keluar<j.jam_masuk) AS candidate_overnight,
              count(*) FILTER (WHERE j.jam_keluar=j.jam_masuk) AS equal_times,
              count(*) FILTER (WHERE j.jam_masuk='00:00' AND j.jam_keluar='00:00') AS both_midnight,
              count(*) FILTER (WHERE j.flexible_time IS NOT NULL) AS flexible_time_present
              FROM m_jadwal j LEFT JOIN m_shift s ON s.id=j.jenis''',
            'jadwal_duplicate_shift_day': 'SELECT count(*) FROM (SELECT jenis,lower(btrim(hari)) FROM m_jadwal GROUP BY 1,2 HAVING count(*)>1) d',
            'shifts_without_schedule': 'SELECT count(*) FROM m_shift s WHERE NOT EXISTS (SELECT 1 FROM m_jadwal j WHERE j.jenis=s.id)',
            'holiday_quality': '''SELECT min(tanggal),max(tanggal),count(DISTINCT tanggal),count(*) FILTER (WHERE keterangan IS NULL),count(*) FILTER (WHERE keterangan='') FROM m_hari_libur''',
            'holiday_duplicate_dates': 'SELECT tanggal,count(*) FROM m_hari_libur GROUP BY 1 HAVING count(*)>1 ORDER BY 1',
            'holiday_years': 'SELECT extract(year FROM tanggal)::int,count(*) FROM m_hari_libur GROUP BY 1 ORDER BY 1',
            'leave_types': 'SELECT id,nama,tipe FROM m_tipe_ijin ORDER BY id',
            'leave_kinds': 'SELECT id,nama,kode,setengah_hari,tipe_id,potongan,is_aktif,label_kode FROM m_jenis_ijin ORDER BY id',
            'leave_orphans': 'SELECT count(*) FROM m_jenis_ijin j LEFT JOIN m_tipe_ijin t ON t.id=j.tipe_id WHERE j.tipe_id IS NOT NULL AND t.id IS NULL',
        }
        report['audit'] = {}
        for label, query in queries.items():
            cur = c.execute(query)
            report['audit'][label] = {'columns': [d.name for d in cur.description], 'rows': cur.fetchall()}
    with connect(report['target_database']) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        targets = ['dim_calendar','dim_tanggal','dim_shift','dim_jadwal_kerja','dim_jenis_izin']
        report['target_columns'] = c.execute("SELECT table_name,column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name=ANY(%s) ORDER BY table_name,ordinal_position", (targets,)).fetchall()
        report['target_counts'] = {t:c.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(t))).fetchone()[0] for t in sorted({r[0] for r in report['target_columns']})}
    out = report_path('audit-remaining-dimensions.json')
    out.write_text(json.dumps(report,indent=2,default=str)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='source_columns'},indent=2,default=str))

if __name__ == '__main__':
    main()
