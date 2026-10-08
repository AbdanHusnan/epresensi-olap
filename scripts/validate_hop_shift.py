"""Reconcile combined shift values against raw masters and verify unchanged reruns."""
import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from report_paths import report_path
from zoneinfo import ZoneInfo
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from dotenv import dotenv_values
ROOT = Path(__file__).resolve().parents[1]
REPORT = report_path('validation-hop-dim-shift.json')
FIELDS = '''jadwal_id_sumber shift_id_sumber nama_shift departemen_id_sumber
 departemen_key is_aktif_saat_ini is_reguler is_flexible_kode_sumber is_flexible
 event_id_sumber shift_source_created_at jadwal_source_created_at hari_sumber hari
 hari_iso jam_masuk jam_keluar jam_masuk_awal jam_keluar_akhir flexible_time_sumber
 indikasi_lintas_tengah_malam is_jam_sama'''.split()
DAYS = ['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu']
EN = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
DAY_MAP = {label.lower(): i+1 for i,names in enumerate(zip(DAYS,EN)) for name in names for label in (name,name[:3])}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--unchanged',action='store_true')
    args=parser.parse_args()
    cfg=dotenv_values(ROOT / '.env')
    def connect(db):
        return psycopg.connect(host=cfg['OLAP_HOST'],port=cfg['OLAP_PORT'],
            user=cfg['OLAP_USER'],password=cfg['OLAP_PASSWORD'],dbname=db,
            options='-c default_transaction_read_only=on',row_factory=dict_row)
    with connect('dbabsen_restore') as source, connect('epresensi_analytics_hop_dev') as target:
        source.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        target.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        shifts={r['id']:r for r in source.execute('SELECT * FROM public.m_shift')}
        schedules=source.execute('SELECT * FROM public.m_jadwal ORDER BY id').fetchall()
        depts={r['departemen_id_sumber']:r['departemen_key'] for r in target.execute('SELECT departemen_id_sumber,departemen_key FROM public.dim_departemen')}
        expected=[]
        for j in schedules:
            s=shifts[j['jenis']]
            day=DAY_MAP[j['hari'].strip().lower()]
            assert s['is_flexible'] in (None,0,1), 'Unexpected flexible code'
            assert s['departemen_id'] is None or s['departemen_id'] in depts, 'Missing department lookup'
            expected.append(dict(zip(FIELDS, [j['id'],s['id'],s['nama'],s['departemen_id'],
                depts.get(s['departemen_id']),s['status'],bool(re.search('regular|reguler',s['nama'],re.I)),
                s['is_flexible'],None if s['is_flexible'] is None else s['is_flexible']==1,
                s['event_id'],s['created_at'],j['created_at'],j['hari'],DAYS[day-1],day,
                j['jam_masuk'],j['jam_keluar'],j['jam_masuk_awal'],j['jam_keluar_akhir'],
                j['flexible_time'],j['jam_keluar']<j['jam_masuk'],j['jam_keluar']==j['jam_masuk']])))
        actual=target.execute(sql.SQL('SELECT {} FROM public.dim_shift ORDER BY jadwal_id_sumber').format(sql.SQL(',').join(map(sql.Identifier,FIELDS)))).fetchall()
        assert len(actual)==len(expected), 'Row count mismatch'
        for a,e in zip(actual,expected):
            if a!=e:
                bad=[f for f in FIELDS if a[f]!=e[f]]
                raise AssertionError(f"Mapping mismatch for schedule {e['jadwal_id_sumber']}, fields: {bad}")
        technical=target.execute('SELECT jadwal_id_sumber,shift_key,waktu_proses,etl_loaded_at FROM public.dim_shift ORDER BY jadwal_id_sumber').fetchall()
        assert len({r['shift_key'] for r in technical})==len(expected)
        assert all(r['waktu_proses'] is not None for r in technical)
        referenced={j['jenis'] for j in schedules}
        no_schedule=sorted(set(shifts)-referenced)
        digest=lambda data:hashlib.sha256(json.dumps(data,default=str,sort_keys=True).encode()).hexdigest()
        report={'checked_at':datetime.now(ZoneInfo('Asia/Jakarta')).isoformat(),
            'source_database':'dbabsen_restore','target_database':'epresensi_analytics_hop_dev',
            'target_table':'public.dim_shift','grain':'one row per m_jadwal.id',
            'rows':len(actual),'distinct_parent_shifts':len(referenced),
            'all_mapped_values_match':True,'unique_surrogate_keys':True,
            'missing_department_lookups':sum(r['departemen_id_sumber'] is not None and r['departemen_key'] is None for r in actual),
            'rows_without_department':sum(r['departemen_id_sumber'] is None for r in actual),
            'candidate_overnight_rows':sum(r['indikasi_lintas_tengah_malam'] for r in actual),
            'equal_time_rows':sum(r['is_jam_sama'] for r in actual),
            'shifts_without_schedule_count':len(no_schedule),'shifts_without_schedule_ids':no_schedule,
            'data_sha256':digest(actual),'keys_and_timestamps_sha256':digest(technical)}
    if args.unchanged:
        previous=json.loads(REPORT.read_text())
        for key in ['target_database','target_table','rows','data_sha256','keys_and_timestamps_sha256']:
            assert previous[key]==report[key], f'Unchanged rerun mismatch: {key}'
        report['unchanged_rerun_verified']=True
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='shifts_without_schedule_ids'},indent=2))

if __name__=='__main__':
    main()
