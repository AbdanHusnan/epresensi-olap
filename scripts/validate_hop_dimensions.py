"""Read-only full source/target reconciliation; --unchanged checks idempotent reruns."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from report_paths import report_path
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import psycopg
from psycopg import sql
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
TARGET_DB = 'epresensi_analytics_hop_dev'
REPORT = report_path('validation-hop-dimensions.json')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--unchanged', action='store_true')
    args = parser.parse_args()
    cfg = dotenv_values(ROOT / '.env')
    def connect(db):
        return psycopg.connect(host=cfg['OLAP_HOST'], port=cfg['OLAP_PORT'],
            user=cfg['OLAP_USER'], password=cfg['OLAP_PASSWORD'], dbname=db,
            options='-c default_transaction_read_only=on')
    report = {'checked_at': datetime.now(ZoneInfo('Asia/Jakarta')).isoformat(),
              'source_database': 'dbabsen_restore', 'target_database': TARGET_DB,
              'tables': {}}
    with connect('dbabsen_restore') as source, connect(TARGET_DB) as target:
        source.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        target.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        depts = dict(target.execute('SELECT departemen_id_sumber, departemen_key FROM public.dim_departemen'))
        for table, key in [('dim_departemen', 'departemen'), ('dim_pegawai', 'pegawai')]:
            pipeline = ET.parse(ROOT / f'hop/presensi/pipelines/{table}.hpl').getroot()
            query = pipeline.find("transform/[type='TableInput']/sql").text
            cur = source.execute(query)
            fields = [d.name for d in cur.description]
            expected = cur.fetchall()
            if table == 'dim_pegawai':
                idx = fields.index('departemen_id_sumber')
                assert all(row[idx] in depts for row in expected), 'Missing target department reference'
                expected = [(*row, depts[row[idx]], row[idx]) for row in expected]
                fields += ['departemen_key', 'departemen_id']
            rows = target.execute(sql.SQL('SELECT {} FROM public.{} ORDER BY {}').format(
                sql.SQL(', ').join(map(sql.Identifier, fields)), sql.Identifier(table),
                sql.Identifier(key + '_id_sumber'))).fetchall()
            assert rows == expected, f'{table}: source/target values differ'
            technical = target.execute(sql.SQL('SELECT {}, {}, waktu_proses, etl_loaded_at FROM public.{} ORDER BY {}').format(
                sql.Identifier(key+'_id_sumber'), sql.Identifier(key+'_key'),
                sql.Identifier(table), sql.Identifier(key+'_id_sumber'))).fetchall()
            assert len({r[1] for r in technical}) == len(rows), 'Nonunique surrogate keys'
            assert all(r[1] is not None and r[2] is not None for r in technical), 'Missing key or timestamp'
            digest = lambda value: hashlib.sha256(json.dumps(value, default=str).encode()).hexdigest()
            report['tables'][table] = {'rows': len(rows), 'all_mapped_values_match': True,
                'unique_surrogate_keys': True, 'data_sha256': digest(rows),
                'keys_and_timestamps_sha256': digest(technical)}
        report['missing_department_lookups'] = target.execute('SELECT count(*) FROM public.dim_pegawai WHERE departemen_key IS NULL').fetchone()[0]
        report['category_counts'] = dict(target.execute('SELECT kategori_pegawai, count(*) FROM public.dim_pegawai GROUP BY 1 ORDER BY 1'))
        report['empty_names_preserved'] = target.execute("SELECT count(*) FROM public.dim_pegawai WHERE nama_pegawai=''").fetchone()[0]
        report['empty_nips_preserved'] = target.execute("SELECT count(*) FROM public.dim_pegawai WHERE nip=''").fetchone()[0]
        report['null_status_aktif'] = target.execute('SELECT count(*) FROM public.dim_pegawai WHERE status_aktif IS NULL').fetchone()[0]
    if args.unchanged:
        previous = json.loads(REPORT.read_text())
        assert previous['target_database'] == TARGET_DB
        for table, result in report['tables'].items():
            assert result == previous['tables'][table], f'{table}: unchanged rerun changed values/keys/timestamps'
        report['unchanged_rerun_verified'] = True
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
