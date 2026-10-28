#!/usr/bin/env python3
"""Bounded integration pilot. Requires docker access; never loads historical events."""
import json, subprocess, hashlib
from pathlib import Path
P=Path(__file__).resolve().parent
DB='staging_bkd_test_20261027'
SRC=('epresensi-olap-postgres','olap_admin','dbabsen_restore')
DST=('epresensi-staging-postgres','admin_staging',DB)
RUN='E2E_20261027'
def call(conn,sql,data=None,check=True):
 cmd=['docker','exec','-i',conn[0],'psql','-X','-q','-v','ON_ERROR_STOP=1','-U',conn[1],'-d',conn[2],'-At']
 if data is not None: cmd+=['-c',sql]
 r=subprocess.run(cmd,input=data if data is not None else sql.encode(),capture_output=True)
 if check and r.returncode: raise RuntimeError(r.stderr.decode()[-2500:])
 return r

def q(conn,sql): return call(conn,sql).stdout.decode().strip()
def obj(conn,sql):return json.loads(q(conn,sql))
def cols(table):
 return obj(DST,f"SELECT json_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='raw' AND table_name='{table}' AND column_name NOT IN ('extracted_at','pipeline_run_id')")
def quoted(names):return ','.join('"'+x+'"' for x in names)
def copy(table,source,where='true',names=None):
 names=names or cols(table); c=quoted(names)
 payload=call(SRC,f"COPY (SELECT {c} FROM public.{source} WHERE {where} ORDER BY id) TO STDOUT WITH (FORMAT binary)",data=b'').stdout
 call(DST,f'COPY raw.{table} ({c}) FROM STDIN WITH (FORMAT binary)',data=payload)
 return {'rows':int(q(DST,f'SELECT count(*) FROM raw.{table}')), 'source_binary_sha256':hashlib.sha256(payload).hexdigest()}
def transform(fail=False):
 sql=(P/'transform.sql').read_text()
 if fail:sql=sql.replace('COMMIT;','SELECT 1/0;\nCOMMIT;')
 r=call(DST,sql,check=not fail)
 if fail and not r.returncode:raise AssertionError('Failure injection did not fail')
def fingerprint():
 return q(DST,"SELECT md5(string_agg(row_to_json(x)::text,'' ORDER BY pegawai_id)) FROM curated.cur_attendance_regular_daily x")
def ingest():
 # Only fixture IDs; overlap permits identical timestamps and replay. This is not a CDC certification.
 cursor=q(DST,'SELECT watermark::text FROM test_control.run')
 upper=q(SRC,"SET TIME ZONE 'Asia/Jakarta'; SELECT clock_timestamp()::timestamp::text")
 c=quoted(cols('raw_checkinout'))
 data=call(SRC,f"COPY (SELECT {c} FROM public.t_checkinout WHERE id IN (SELECT event_id FROM test_e2e_20261027.events) AND updated_at >= timestamp '{cursor}' - interval '1 second' AND updated_at <= timestamp '{upper}' ORDER BY id) TO STDOUT WITH (FORMAT binary)",data=b'').stdout
 # Temporary buffer exists only in the dedicated test database; commit data before checkpoint.
 q(DST,'DROP TABLE IF EXISTS raw.event_buffer; CREATE TABLE raw.event_buffer (LIKE raw.raw_checkinout INCLUDING DEFAULTS)')
 call(DST,f'COPY raw.event_buffer ({c}) FROM STDIN WITH (FORMAT binary)',data=data)
 updates=','.join(f'"{x}"=excluded."{x}"' for x in cols('raw_checkinout') if x!='id')
 q(DST,f"BEGIN; INSERT INTO raw.raw_checkinout SELECT * FROM raw.event_buffer ON CONFLICT(id) DO UPDATE SET {updates},extracted_at=excluded.extracted_at; UPDATE test_control.run SET watermark=timestamp '{upper}'; COMMIT;")
 # Exact source/raw equality, all business attributes including NULL.
 a=q(SRC,f"SELECT coalesce(json_agg(x ORDER BY id),'[]') FROM (SELECT {c} FROM t_checkinout WHERE id IN (SELECT event_id FROM test_e2e_20261027.events)) x")
 b=q(DST,f"SELECT coalesce(json_agg(x ORDER BY id),'[]') FROM (SELECT {c} FROM raw.raw_checkinout) x")
 assert json.loads(a)==json.loads(b),'source/raw attribute mismatch'
def event(kind,fixture):
 peg,jad=fixture['pegawai_id'],fixture['jadwal_id']
 offset="j.jam_masuk - interval '5 minutes'" if kind==1 else "j.jam_keluar + interval '5 minutes'"
 q(SRC,f"""BEGIN; SET LOCAL TIME ZONE 'Asia/Jakarta';
 WITH inserted AS (
 INSERT INTO t_checkinout(pegawai_id,departemen,checktype,created_at,updated_at,timezone,is_wfh,work_code,jadwal_id,hari,jam_masuk,jam_keluar,jam_masuk_awal,jam_keluar_akhir,flexible_time,is_manual)
 SELECT p.id,p.departemen,{kind},date '2026-10-27'+({offset}),clock_timestamp()::timestamp,'Asia/Jakarta',0,j.jenis,j.id,j.hari,j.jam_masuk,j.jam_keluar,j.jam_masuk_awal,j.jam_keluar_akhir,j.flexible_time,false
 FROM m_pegawai p CROSS JOIN m_jadwal j WHERE p.id={peg} AND j.id={jad}
 AND NOT EXISTS(SELECT 1 FROM test_e2e_20261027.events WHERE checktype={kind}) RETURNING id)
 INSERT INTO test_e2e_20261027.events SELECT {kind},id FROM inserted; COMMIT;""")
def stage(name,fixture,expected):
 row=obj(DST,f"SELECT row_to_json(x) FROM curated.cur_attendance_regular_daily x WHERE pegawai_id={fixture['pegawai_id']}")
 for k,v in expected.items(): assert row[k]==v,(name,k,row[k],v)
 n=int(q(DST,'SELECT count(*) FROM curated.cur_employee_workday'))
 assert n==int(q(DST,'SELECT count(*) FROM raw.raw_pegawai'))
 assert int(q(DST,'SELECT count(*) FROM curated.cur_attendance_regular_daily'))==n
 assert q(DST,'SELECT count(*) FROM curated.cur_event_attendance')==q(DST,'SELECT count(*) FROM raw.raw_checkinout')
 report['stages'].append({'stage':name,'passed':True,'expected':expected,'workday_count':n})
 (P/'results.json').write_text(json.dumps(report,indent=2)+'\n')
 print(name,'PASS',flush=True)

def main():
    global report
    report={'run_id':RUN,'business_date':'2026-10-27','source':SRC[2],'target':DB,'stages':[]}
    admin=(DST[0],DST[1],'postgres')
    exists=q(admin,f"SELECT 1 FROM pg_database WHERE datname='{DB}'")
    if exists:raise SystemExit('Test database already exists. Preserve evidence; use replay.py for a non-destructive rerun.')
    q(admin,f'CREATE DATABASE {DB}')
    q(DST,(P/'schema_reference.sql').read_text())
    q(DST,"""CREATE SCHEMA test_control;
     CREATE TABLE test_control.run(snapshot_date date PRIMARY KEY,snapshot_at timestamptz NOT NULL,day_closed boolean DEFAULT false,watermark timestamp NOT NULL);
     INSERT INTO test_control.run VALUES ('2026-10-27',clock_timestamp(),false,'1970-01-01');
     CREATE TABLE raw.raw_previleges(id int PRIMARY KEY,previleges varchar(200),extracted_at timestamptz NOT NULL,pipeline_run_id text NOT NULL);""")
    for table in ['pegawai','departemen','shift','jadwal','hari_libur','libur_shift','perizinan','jenis_ijin','tipe_ijin','user','checkinout','previleges']:
     q(DST,f"ALTER TABLE raw.raw_{table} ALTER extracted_at SET DEFAULT clock_timestamp(), ALTER pipeline_run_id SET DEFAULT '{RUN}'")
    report['snapshot_tables']={}
    for table,source,where in [
     ('pegawai','m_pegawai','true'),('departemen','m_departemen','true'),('shift','m_shift','true'),('jadwal','m_jadwal','true'),
     ('hari_libur','m_hari_libur','true'),('libur_shift','t_libur_shift',"tanggal='2026-10-27'"),
     ('perizinan','t_perizinan',"tgl_ijin <= '2026-10-27' AND coalesce(tgl_ijin_sampai,tgl_ijin) >= '2026-10-27'"),
     ('jenis_ijin','m_jenis_ijin','true'),('tipe_ijin','m_tipe_ijin','true'),('user','m_user','true'),('previleges','m_previleges','true')]:
     report['snapshot_tables'][table]=copy('raw_'+table,source,where)
     print('snapshot',table,report['snapshot_tables'][table]['rows'],flush=True)
    q(DST,(P/'workday.sql').read_text())
    # Choose a real regular schedule for Tuesday; the pilot intentionally excludes overnight/flexible schedules.
    fixtures=obj(DST,"""SELECT json_agg(x) FROM (
     SELECT w.pegawai_id,min(j.id) AS jadwal_id
     FROM curated.cur_employee_workday w
     JOIN raw.raw_shift s ON s.departemen_id=w.departemen_id AND s.status AND s.nama ~* '(regular|reguler)'
     JOIN raw.raw_jadwal j ON j.jenis=s.id AND j.hari='Tue'
     WHERE w.is_expected_workday AND coalesce(s.is_flexible,0)=0
     AND j.jam_masuk > time '00:05' AND j.jam_keluar < time '23:55' AND j.jam_keluar>j.jam_masuk
     AND NOT EXISTS(SELECT 1 FROM raw.raw_perizinan p WHERE p.pegawai_id=w.pegawai_id)
     GROUP BY w.pegawai_id ORDER BY w.pegawai_id LIMIT 2) x""")
    assert fixtures and len(fixtures)==2,'Need two eligible employees'
    f,control=fixtures
    report['fixtures']={'attendance':f,'no_event':control}
    (P/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    q(SRC,"CREATE SCHEMA IF NOT EXISTS test_e2e_20261027; CREATE TABLE IF NOT EXISTS test_e2e_20261027.events(checktype integer PRIMARY KEY,event_id integer UNIQUE NOT NULL);")
    assert q(SRC,'SELECT count(*) FROM test_e2e_20261027.events')=='0','Existing fixture events; do not overwrite'
    transform();stage('baseline',f,{'is_expected_workday':True,'has_masuk':False,'has_pulang':False,'status_kehadiran':None})
    event(1,f);ingest();transform();stage('checkin',f,{'status_kehadiran':'CHECKIN_BELUM_PULANG','checkin_event_count':1,'checkout_event_count':0,'is_late':False})
    event(2,f);ingest();transform();stage('checkout',f,{'status_kehadiran':'HADIR_LENGKAP','checkin_event_count':1,'checkout_event_count':1})
    before=fingerprint();ingest();transform();assert before==fingerprint();stage('rerun',f,{'status_kehadiran':'HADIR_LENGKAP'})
    q(SRC,"SET TIME ZONE 'Asia/Jakarta'; UPDATE t_checkinout SET created_at=date '2026-10-27'+jam_masuk+interval '10 minutes', updated_at=clock_timestamp()::timestamp WHERE id=(SELECT event_id FROM test_e2e_20261027.events WHERE checktype=1)")
    ingest();before=fingerprint();transform(fail=True);assert before==fingerprint();transform()
    stage('correction_and_recovery',f,{'status_kehadiran':'HADIR_LENGKAP','late_minutes':10,'is_late':True,'checkin_event_count':1})
    q(DST,'UPDATE test_control.run SET day_closed=true');transform()
    stage('day_close_control',control,{'status_kehadiran':'TANPA_KETERANGAN','scheduled_regular_days':1,'checkin_days':0})
    report['events']=obj(SRC,'SELECT json_agg(x ORDER BY checktype) FROM test_e2e_20261027.events x')
    report['workday_summary']=obj(DST,"SELECT row_to_json(x) FROM (SELECT count(*) total,count(*) FILTER(WHERE is_employee_active) active,count(*) FILTER(WHERE is_expected_workday) expected,count(*) FILTER(WHERE is_employee_active IS NULL) unknown_status FROM curated.cur_employee_workday) x")
    report['snapshot_at']=q(DST,'SELECT snapshot_at FROM test_control.run')
    (P/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print('All pilot assertions passed.',flush=True)

if __name__ == "__main__":
    main()
