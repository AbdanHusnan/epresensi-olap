"""Full calendar reconciliation, SQL edge cases and idempotent rerun verification."""
import argparse
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from report_paths import report_path
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
import psycopg
from psycopg.rows import dict_row
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
REPORT=report_path('validation-hop-dim-calendar.json')
MONTHS='Januari Februari Maret April Mei Juni Juli Agustus September Oktober November Desember'.split()
DAYS='Senin Selasa Rabu Kamis Jumat Sabtu Minggu'.split()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--start-date',type=date.fromisoformat,default=date(2021,1,1))
    p.add_argument('--end-date',type=date.fromisoformat,default=date(2026,12,31))
    p.add_argument('--unchanged',action='store_true')
    args=p.parse_args()
    if args.end_date<args.start_date:p.error('end-date must be >= start-date')
    cfg=dotenv_values(ROOT/'.env')
    def connect(db):
        return psycopg.connect(host=cfg['OLAP_HOST'],port=cfg['OLAP_PORT'],user=cfg['OLAP_USER'],
            password=cfg['OLAP_PASSWORD'],dbname=db,row_factory=dict_row,options='-c default_transaction_read_only=on')
    template=(ROOT/'sql/hop/extract_dim_calendar.sql').read_text()
    assert ET.parse(ROOT/'hop/presensi/pipelines/dim_calendar.hpl').getroot().find("transform/[type='TableInput']/sql").text==template
    with connect('dbabsen_restore') as source, connect('epresensi_analytics_hop_dev') as target:
        source.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        target.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        holidays=source.execute('SELECT id,tanggal,keterangan,created_at FROM public.m_hari_libur ORDER BY id').fetchall()
        by_date={}
        for r in holidays:by_date.setdefault(r['tanggal'],[]).append(r)
        actual=target.execute('SELECT * FROM public.dim_calendar WHERE tanggal BETWEEN %s AND %s ORDER BY tanggal',(args.start_date,args.end_date)).fetchall()
        assert len(actual)==(args.end_date-args.start_date).days+1,'Missing or duplicated dates'
        for n,row in enumerate(actual):
            d=args.start_date+timedelta(days=n);h=by_date.get(d,[])
            labels=sorted({r['keterangan'] for r in h if r['keterangan'] is not None})
            created=[r['created_at'] for r in h if r['created_at'] is not None]
            expected=dict(tanggal=d,tahun=d.year,bulan=d.month,nama_bulan=MONTHS[d.month-1],hari=d.day,
                nama_hari=DAYS[d.weekday()],minggu_ke=d.isocalendar().week,kuartal=(d.month-1)//3+1,
                is_weekend=d.weekday()>=5,is_hari_libur=bool(h),keterangan_libur='; '.join(labels) if labels else None,
                hari_iso=d.isoweekday(),tahun_iso=d.isocalendar().year,is_hari_kerja_normal=d.weekday()<5,
                libur_id_sumber=','.join(str(r['id']) for r in h) if h else None,
                libur_source_created_at_terakhir=max(created) if created else None)
            bad=[k for k,v in expected.items() if row[k]!=v]
            assert not bad,f'{d}: mismatched fields {bad}'
            assert row['waktu_proses'] is not None and row['etl_loaded_at'] is not None
        # Read-only fixtures exercise NULL descriptions and duplicate holiday dates.
        fixture=template.replace('FROM public.m_hari_libur',"FROM (VALUES (1,DATE '2024-02-29',NULL::text,NULL::timestamp),(2,DATE '2024-02-29',NULL::text,NULL::timestamp)) AS fixture(id,tanggal,keterangan,created_at)")
        def query(start,end):return fixture.replace('${START_DATE}',start).replace('${END_DATE}',end)
        leap=source.execute(query('2024-02-28','2024-03-01')).fetchall()
        assert len(leap)==3 and leap[1]['is_hari_libur'] and leap[1]['keterangan_libur'] is None
        assert leap[1]['libur_id_sumber']=='1,2'
        iso=source.execute(query('2021-01-01','2021-01-03')).fetchall()
        assert iso[0]['tahun_iso']==2020 and iso[0]['minggu_ke']==53
        assert iso[1]['is_weekend'] and not iso[1]['is_hari_kerja_normal']
        source.execute('SAVEPOINT invalid_range')
        try:source.execute(query('2026-01-02','2026-01-01')).fetchall()
        except psycopg.errors.DivisionByZero:source.execute('ROLLBACK TO SAVEPOINT invalid_range')
        else:raise AssertionError('Reversed range was not rejected')
        source.execute('RELEASE SAVEPOINT invalid_range')
        digest=lambda data:hashlib.sha256(json.dumps(data,default=str,sort_keys=True).encode()).hexdigest()
        report={'checked_at':datetime.now(ZoneInfo('Asia/Jakarta')).isoformat(),
            'target_database':'epresensi_analytics_hop_dev','target_table':'public.dim_calendar',
            'start_date':str(args.start_date),'end_date':str(args.end_date),'rows':len(actual),
            'all_mapped_values_match':True,'complete_unique_dates':True,
            'holiday_dates_in_range':sum(r['is_hari_libur'] for r in actual),
            'source_holiday_rows':len(holidays),'source_last_holiday_date':str(max(by_date)) if by_date else None,
            'holiday_calendar_completeness_verified':False,
            'edge_cases_passed':['leap_day','duplicate_holiday_date','null_holiday_description','iso_year_boundary','weekend','reversed_range_rejected'],
            'data_sha256':digest([{k:v for k,v in r.items() if k not in ('waktu_proses','etl_loaded_at')} for r in actual]),
            'keys_and_timestamps_sha256':digest([(r['tanggal'],r['waktu_proses'],r['etl_loaded_at']) for r in actual])}
    if args.unchanged:
        old=json.loads(REPORT.read_text())
        for k in ['target_database','target_table','start_date','end_date','rows','data_sha256','keys_and_timestamps_sha256']:
            assert old[k]==report[k],f'Rerun mismatch: {k}'
        report['unchanged_rerun_verified']=True
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
