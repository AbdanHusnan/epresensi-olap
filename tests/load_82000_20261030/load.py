"""Explicitly authorized expansion of the existing bulk test through real Hop."""
import argparse,importlib.util,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('bulk',ROOT/'tests/mart_bulk_20261029/run.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b);t=b.t;t.OUT=OUT

def init():
    t.require(t.TARGET=='mart_bkd_bulk_20261029','Target mismatch')
    t.require(t.scalar('SELECT count(*) FROM curated.cur_attendance_daily')=='2400','Unexpected initial size')
    t.require(t.scalar('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL')=='0','Pending deliveries')
    t.save('protected_before',t.guards())
    backups=ROOT/'backups/load_82000_20261030';backups.mkdir(parents=True,exist_ok=True)
    import subprocess,os
    for container,db in [(t.SC,t.SOURCE),(t.MC,t.TARGET)]:
        path=backups/(db+'.dump')
        with path.open('xb') as f:
            os.chmod(path,0o600)
            subprocess.run(['docker','exec',container,'sh','-c','exec pg_dump -Fc -U "$POSTGRES_USER" -d "$1"','backup',db],stdout=f,check=True)
    t.sql('''CREATE SCHEMA test_load_82000;
    CREATE TABLE test_load_82000.daily AS SELECT row_number() OVER(ORDER BY pegawai_id)::int AS fixture_n,d.* FROM curated.cur_attendance_daily d;
    CREATE TABLE test_load_82000.population AS SELECT row_number() OVER(ORDER BY pegawai_id)::int AS fixture_n,p.* FROM curated.cur_employee_population_daily p;
    CREATE UNIQUE INDEX ON test_load_82000.daily(fixture_n);
    CREATE UNIQUE INDEX ON test_load_82000.population(fixture_n);''')
    t.save('init',{'target':t.TARGET,'source':t.SOURCE,'backups':str(backups),'synthetic_id_start':1000000001})

def ramp(n):
    current=int(t.scalar("SELECT count(*) FROM curated.cur_attendance_daily WHERE tanggal='2026-10-28'"))
    t.require(current<n<=82000,'Ramp must increase population up to 82000')
    t.require(t.scalar('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL')=='0','Drain queue first')
    start=time.monotonic()
    statements=[]
    for table,fixture in [('curated.cur_employee_population_daily','population'),('curated.cur_attendance_daily','daily')]:
        cols=t.columns(table); names=','.join(cols)
        selected=','.join('1000000000+g.n' if c=='pegawai_id' else 'f.'+c for c in cols)
        statements.append(f'INSERT INTO {table} ({names}) SELECT {selected} FROM generate_series({current-2400+1},{n-2400}) g(n) JOIN test_load_82000.{fixture} f ON f.fixture_n=((g.n-1)%2400)+1')
    t.sql("BEGIN; SET LOCAL statement_timeout='180s'; SET LOCAL lock_timeout='5s';"+';'.join(statements)+'; COMMIT;')
    t.save(f'ramp_{n}_fixture',{'seconds':time.monotonic()-start,'inserted':n-current,'employees':n})
    t.hop(f'ramp_{n}')
    verify(f'ramp_{n}')

def verify(label):
    # Existing verifier compares all shared source/fact fields and independently
    # derives all 12 measures from Boolean flags, then checks all aggregate rows.
    result=t.verify(label)
    metrics=','.join(f'SUM({m}) AS {m}' for m in t.MEASURES)
    expected=t.data(f'SELECT jsonb_agg(to_jsonb(x) ORDER BY tanggal,departemen_id) FROM (SELECT tanggal,departemen_id,{metrics} FROM curated.cur_attendance_daily GROUP BY tanggal,departemen_id) x')
    actual=t.data('SELECT jsonb_agg(to_jsonb(x) ORDER BY tanggal,departemen_id) FROM (SELECT tanggal,departemen_id_sumber AS departemen_id,'+','.join(t.MEASURES)+' FROM serving.v_kehadiran_departemen_harian) x',target=True)
    t.require(expected==actual,'Source-grouped department measures differ')
    t.require(t.scalar("""SELECT count(*) FROM mart_kehadiran.fact_kehadiran_daily f
    JOIN mart_kehadiran.dim_pegawai p USING(pegawai_key) JOIN mart_kehadiran.dim_departemen d USING(departemen_key)
    WHERE f.pegawai_id_sumber IS DISTINCT FROM p.pegawai_id_sumber OR f.departemen_id_sumber IS DISTINCT FROM d.departemen_id_sumber
    OR NOT(f.tanggal>=p.valid_from AND (p.valid_to IS NULL OR f.tanggal<p.valid_to))
    OR NOT(f.tanggal>=d.valid_from AND (d.valid_to IS NULL OR f.tanggal<d.valid_to))""",target=True)=='0','Dimension mismatch')
    t.require(t.guards()==json.loads((OUT/'protected_before.json').read_text()),'Protected data changed')
    t.save(label+'_reconciliation',{'passed':True,'department_partitions':len(expected),'protected_unchanged':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['init','ramp','verify']);p.add_argument('--employees',type=int);a=p.parse_args()
    if a.phase=='init':init()
    elif a.phase=='ramp':ramp(a.employees)
    else:verify('manual')
