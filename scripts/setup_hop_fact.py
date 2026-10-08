"""Provision target-only FDW staging and bounded fact loader. Secrets are never printed."""
from pathlib import Path
import psycopg
from psycopg import sql
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
TABLES={
 't_checkinout': 'id integer,pegawai_id integer,departemen integer,checktype integer,created_at timestamp,updated_at timestamp,is_wfh smallint,work_code integer,jadwal_id integer,jam_masuk time,jam_keluar time,timezone text,is_manual boolean',
 't_perizinan':'id integer,user_id integer,pegawai_id integer,departemen integer,approval boolean,approval_at timestamp,tgl_ijin date,tgl_ijin_sampai date,jenis_ijin integer,updated_at timestamp',
 'm_user':'id integer,pegawai_id integer',
 'm_jenis_ijin':'id integer,nama text,tipe_id integer,setengah_hari boolean',
 't_libur_shift':'id integer,pegawai_id integer,tanggal date,updated_at timestamp',
}

def main():
 c=dotenv_values(ROOT/'.env');h=dotenv_values(ROOT/'.env.hop')
 def connect(db):return psycopg.connect(host=c['OLAP_HOST'],port=c['OLAP_PORT'],user=c['OLAP_USER'],password=c['OLAP_PASSWORD'],dbname=db)
 with connect('dbabsen_restore') as source:
  for table,definition in TABLES.items():
   columns=[p.strip().split()[0] for p in definition.split(',')]
   source.execute(sql.SQL('GRANT SELECT ({}) ON public.{} TO {}').format(sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(table),sql.Identifier(h['HOP_SOURCE_USER'])))
  lo=source.execute('SELECT id FROM t_checkinout ORDER BY id LIMIT 1').fetchone()[0]
  hi=source.execute('SELECT id FROM t_checkinout ORDER BY id DESC LIMIT 1').fetchone()[0]
 with connect('epresensi_analytics_hop_dev') as target:
  target.execute('CREATE EXTENSION IF NOT EXISTS postgres_fdw')
  target.execute('CREATE SCHEMA IF NOT EXISTS hop_source')
  if not target.execute("SELECT 1 FROM pg_foreign_server WHERE srvname='hop_restore_source'").fetchone():
   target.execute("CREATE SERVER hop_restore_source FOREIGN DATA WRAPPER postgres_fdw OPTIONS(host '127.0.0.1',port '5432',dbname 'dbabsen_restore',fetch_size '10000',use_remote_estimate 'true',options '-c work_mem=128MB')")
  exists=target.execute("SELECT 1 FROM pg_user_mappings WHERE srvname='hop_restore_source' AND usename=current_user").fetchone()
  if not exists:
   target.execute(sql.SQL('CREATE USER MAPPING FOR CURRENT_USER SERVER hop_restore_source OPTIONS(user {},password {})').format(sql.Literal(h['HOP_SOURCE_USER']),sql.Literal(h['HOP_SOURCE_PASSWORD'])))
  for table,definition in TABLES.items():
   target.execute(sql.SQL('CREATE FOREIGN TABLE IF NOT EXISTS hop_source.{} ({}) SERVER hop_restore_source OPTIONS(schema_name {},table_name {})').format(sql.Identifier(table),sql.SQL(definition),sql.Literal('public'),sql.Literal(table)))
  for filename in ['fact_kehadiran_stage.sql','fact_kehadiran_ingest.sql']:
   target.execute((ROOT/'sql/hop'/filename).read_text())
  target.execute('INSERT INTO hop_etl.fact_checkpoint(singleton,first_id,next_id,last_id) VALUES(true,%s,%s,%s) ON CONFLICT DO NOTHING',(lo,lo,hi))
  for filename in ['fact_kehadiran.sql','fact_kehadiran_rules.sql','fact_kehadiran_steps.sql','fact_kehadiran_views.sql']:
   path=ROOT/'sql/hop'/filename
   if path.exists():target.execute(path.read_text())
  target.execute('GRANT USAGE ON SCHEMA hop_etl TO hop_presensi_writer')
  target.execute('GRANT SELECT ON hop_etl.fact_checkpoint,hop_etl.fact_batches,hop_etl.fact_days TO hop_presensi_writer')
  target.execute('GRANT EXECUTE ON FUNCTION hop_etl.ingest_fact_events() TO hop_presensi_writer')
  if target.execute("SELECT to_regprocedure('hop_etl.fact_step()')").fetchone()[0]:
   target.execute('GRANT EXECUTE ON FUNCTION hop_etl.fact_step() TO hop_presensi_writer')
  print('Target staging ready; source ID limits:',lo,hi)
if __name__=='__main__':main()
