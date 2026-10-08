"""Rule scenarios, rollback-only day integration, and backfill checkpoint audit."""
import argparse
from datetime import date,datetime
from pathlib import Path
from report_paths import report_path
from zoneinfo import ZoneInfo
import json
import psycopg
from psycopg.rows import dict_row
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--dry-run-day',type=date.fromisoformat);p.add_argument('--complete',action='store_true');args=p.parse_args()
 c=dotenv_values(ROOT/'.env')
 report={'checked_at':datetime.now(ZoneInfo('Asia/Jakarta')).isoformat(),'target_database':'epresensi_analytics_hop_dev'}
 with psycopg.connect(host=c['OLAP_HOST'],port=c['OLAP_PORT'],user=c['OLAP_USER'],password=c['OLAP_PASSWORD'],dbname=report['target_database'],row_factory=dict_row) as x:
  baseline=[0,False,2,True,True,False,True,False,False,True,True]
  cases=[('complete_same_day',{},'HADIR',None),('approved_over_presence',{0:1},'IZIN',None),
   ('incomplete',{2:1,3:False},None,'PASANGAN_EVENT_BELUM_FINAL'),
   ('approved_with_incomplete',{0:1,2:1,3:False},'IZIN','PASANGAN_EVENT_BELUM_FINAL'),
   ('no_event_unknown_population',{2:0,3:False,4:False},None,'POPULASI_DAN_KEWAJIBAN_HISTORIS_BELUM_TERVERIFIKASI'),
   ('weekend_or_holiday',{5:True},'HADIR','HARI_NONWAJIB_PERLU_KEPUTUSAN_PENYIMPANAN'),
   ('ambiguous_schedule',{4:False},'HADIR','JADWAL_ATAU_HISTORI_BELUM_TERVERIFIKASI'),
   ('mixed_mode',{6:False},'HADIR','MODE_KERJA_ATAU_TIMEZONE_TIDAK_KONSISTEN'),
   ('manual',{7:True},'HADIR','PRESENSI_MANUAL_BELUM_TERVERIFIKASI'),
   ('flexible',{8:True},'HADIR','ATURAN_FLEKSIBEL_BELUM_FINAL'),
   ('department_conflict',{9:False},'HADIR','DEPARTEMEN_TRANSAKSI_MASTER_TIDAK_KONSISTEN'),
   ('unknown_day_closure',{10:None},'HADIR','CAKUPAN_HARI_SUMBER_BELUM_TERVERIFIKASI'),
   ('partial_or_conflicting_leave',{0:1,1:True},'IZIN','IDENTITAS_CAKUPAN_ATAU_JENIS_IZIN_PERLU_REVIEW'),
   ('overlapping_leave',{0:2},'IZIN','IDENTITAS_CAKUPAN_ATAU_JENIS_IZIN_PERLU_REVIEW')]
  passed=[]
  for name,changes,status,reason in cases:
   values=baseline.copy()
   for i,v in changes.items():values[i]=v
   r=x.execute('SELECT * FROM hop_etl.classify_fact('+','.join(['%s']*len(values))+')',values).fetchone()
   assert r['status_usulan']==status,(name,r)
   assert (not r['alasan_review']) if reason is None else reason in r['alasan_review'],(name,r)
   passed.append(name)
  report['rule_cases_passed']=passed
  x.commit()
  if args.dry_run_day:
   with x.transaction(force_rollback=True):
    x.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
    if not x.execute('SELECT 1 FROM hop_etl.reference_snapshot').fetchone():raise RuntimeError('Reference snapshot is not ready')
    assert x.execute('SELECT count(*) AS n FROM public.fact_kehadiran WHERE tanggal=%s',(args.dry_run_day,)).fetchone()['n']==0,'Use a date not already loaded for rollback test'
    body=(ROOT/'sql/hop/fact_kehadiran_rules.sql').read_text().split('CREATE OR REPLACE FUNCTION hop_etl.build_fact_day',1)[1].split('REVOKE ALL ON FUNCTION hop_etl.build_fact_day',1)[0]
    body='CREATE OR REPLACE FUNCTION pg_temp.fact_day_probe'+body
    body=body.replace('SELECT last_date INTO STRICT last_day FROM hop_etl.fact_checkpoint WHERE singleton;', "last_day := DATE '2026-09-01';")
    x.execute(body)
    r=x.execute('SELECT pg_temp.fact_day_probe(%s) AS rows', (args.dry_run_day,)).fetchone()
    counts=x.execute('''SELECT count(*) AS rows,count(*) FILTER(WHERE is_kpi_final) AS final,
      count(*) FILTER(WHERE perlu_review) AS review,sum(jumlah_event) AS events,
      count(*) FILTER(WHERE is_kpi_final AND (perlu_review OR cardinality(alasan_review)>0 OR status_kehadiran IS NULL)) AS invalid_final,
      count(*) FILTER(WHERE has_valid_leave AND status_kehadiran='HADIR') AS priority_violations
      FROM public.fact_kehadiran WHERE tanggal=%s''',(args.dry_run_day,)).fetchone()
    expected=x.execute('SELECT coalesce(sum(n),0) AS events FROM hop_etl.event_day WHERE tanggal=%s',(args.dry_run_day,)).fetchone()['events']
    assert counts['events']==expected,(counts,expected)
    assert counts['invalid_final']==0 and counts['priority_violations']==0
    assert counts['rows']==r['rows'] and counts['rows']==counts['final']+counts['review']
    assert x.execute('SELECT count(*) AS n FROM analytics.hop_fact_kehadiran_final').fetchone()['n']==0,'Incomplete run exposed in final view'
    report['rollback_day_test']={'tanggal':str(args.dry_run_day),**counts,'rolled_back':True}
  x.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
  report['checkpoint']=x.execute('SELECT * FROM hop_etl.fact_checkpoint').fetchone()
  report['batches']=x.execute('SELECT count(*) AS batches,coalesce(sum(event_rows),0) AS events,coalesce(sum(rejected_rows),0) AS rejected FROM hop_etl.fact_batches').fetchone()
  assert report['batches']['events']==report['checkpoint']['event_rows']
  assert report['batches']['rejected']==report['checkpoint']['rejected_event_rows']
  gaps=x.execute('''WITH b AS (SELECT start_id,end_id,lag(end_id) OVER(ORDER BY start_id) AS previous_end FROM hop_etl.fact_batches)
   SELECT count(*) AS n FROM b WHERE start_id<>coalesce(previous_end+1,%s) OR end_id<start_id''',(report['checkpoint']['first_id'],)).fetchone()['n']
  assert gaps==0,'Batch ID coverage has gaps or overlaps'
  end=x.execute('SELECT max(end_id) AS id FROM hop_etl.fact_batches').fetchone()['id']
  assert end is None or end+1==report['checkpoint']['next_id']
  report['rejected_events']=x.execute('SELECT count(*) AS rows FROM hop_etl.event_rejects').fetchone()
  assert report['rejected_events']['rows']==report['checkpoint']['rejected_event_rows']
  report['processed_days']=x.execute('SELECT count(*) AS days,coalesce(sum(rows_written),0) AS rows,coalesce(sum(final_rows),0) AS final,coalesce(sum(review_rows),0) AS review,coalesce(sum(event_rows),0) AS events FROM hop_etl.fact_days').fetchone()
  if args.complete:
   assert report['checkpoint']['phase']=='done','Backfill not complete yet'
   st=report['checkpoint'];days=(st['last_date']-st['first_date']).days+1
   assert report['processed_days']['days']==days
   assert report['processed_days']['events']+st['rejected_event_rows']==st['event_rows']
   assert report['processed_days']['rows']==st['fact_rows']
   assert st['next_id']>st['last_id'] and st['next_date']>st['last_date']
   report['actual_facts']=x.execute('''SELECT count(*) AS rows,coalesce(sum(jumlah_event),0) AS events,
    count(*) FILTER(WHERE is_kpi_final) AS final,count(*) FILTER(WHERE perlu_review) AS review,
    count(*) FILTER(WHERE is_kpi_final AND (perlu_review OR cardinality(alasan_review)>0 OR status_kehadiran IS NULL)) AS invalid_final,
    count(*) FILTER(WHERE perlu_review AND (status_kehadiran IS NOT NULL OR is_kpi_final)) AS invalid_review,
    count(*) FILTER(WHERE has_valid_leave AND status_kehadiran='HADIR') AS priority_violations
    FROM public.fact_kehadiran''').fetchone()
   actual=report['actual_facts']
   for key in ['rows','events','final','review']:assert actual[key]==report['processed_days'][key],(key,actual,report['processed_days'])
   assert actual['invalid_final']==actual['invalid_review']==actual['priority_violations']==0
   report['full_backfill_verified']=True
 path=report_path('validation-hop-fact-complete.json' if args.complete else 'validation-hop-fact-progress.json')
 if args.dry_run_day:
  report_path('validation-hop-fact-rollback.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
 path.write_text(json.dumps(report,indent=2,default=str)+'\n');print(path.read_text())
if __name__=='__main__':main()
