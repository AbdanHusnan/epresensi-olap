"""Read-only evidence for fact mapping; transaction samples are explicitly bounded."""
from pathlib import Path
from report_paths import report_path
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import psycopg
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]

def main():
 c=dotenv_values(ROOT/'.env')
 def connect(db):return psycopg.connect(host=c['OLAP_HOST'],port=c['OLAP_PORT'],user=c['OLAP_USER'],password=c['OLAP_PASSWORD'],dbname=db,options='-c default_transaction_read_only=on -c statement_timeout=60000')
 report={'checked_at':datetime.now(ZoneInfo('Asia/Jakarta')).isoformat(),'source':'dbabsen_restore','target':'epresensi_analytics_hop_dev','sample_scope':'latest 10000 t_checkinout rows by id; not a full history audit'}
 with connect(report['target']) as x:
  report['target_columns']=x.execute("SELECT column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name='fact_kehadiran' ORDER BY ordinal_position").fetchall()
  report['target_constraints']=x.execute("SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='public.fact_kehadiran'::regclass").fetchall()
  report['target_rows']=x.execute('SELECT count(*) FROM public.fact_kehadiran').fetchone()[0]
 with connect(report['source']) as x:
  x.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
  report['sample_summary']=x.execute('''WITH e AS (SELECT * FROM t_checkinout ORDER BY id DESC LIMIT 10000)
   SELECT count(*),min(e.created_at),max(e.created_at),count(*) FILTER (WHERE e.created_at IS NULL),
   count(*) FILTER (WHERE j.id IS NULL),count(*) FILTER (WHERE e.work_code IS DISTINCT FROM j.jenis),
   count(*) FILTER (WHERE e.departemen IS DISTINCT FROM p.departemen),
   count(*) FILTER (WHERE e.jam_masuk IS DISTINCT FROM j.jam_masuk OR e.jam_keluar IS DISTINCT FROM j.jam_keluar)
   FROM e LEFT JOIN m_jadwal j ON j.id=e.jadwal_id LEFT JOIN m_pegawai p ON p.id=e.pegawai_id''').fetchone()
  report['sample_summary_columns']=['events','min_created_at','max_created_at','null_created_at','missing_schedule','work_code_schedule_mismatch','event_master_department_difference','event_master_times_difference']
  for key,col in [('sample_checktype','checktype'),('sample_timezone','timezone'),('sample_mode','is_wfh')]:
   report[key]=x.execute(f'WITH e AS (SELECT {col} FROM t_checkinout ORDER BY id DESC LIMIT 10000) SELECT {col},count(*) FROM e GROUP BY 1 ORDER BY 1').fetchall()
  report['leave_approval_sample']=x.execute('''WITH i AS (SELECT approval,approval_at,status FROM t_perizinan ORDER BY id DESC LIMIT 10000)
    SELECT approval,status,approval_at IS NOT NULL AS has_approval_time,count(*) FROM i GROUP BY 1,2,3 ORDER BY 1,2,3''').fetchall()
  report['leave_identity_sample']=x.execute('''WITH i AS (SELECT * FROM t_perizinan ORDER BY id DESC LIMIT 10000)
    SELECT count(*),count(*) FILTER(WHERE i.pegawai_id IS NULL),count(*) FILTER(WHERE p.id IS NULL),
    count(*) FILTER(WHERE i.pegawai_id IS DISTINCT FROM u.pegawai_id),
    count(*) FILTER(WHERE i.tgl_ijin_sampai<i.tgl_ijin),count(*) FILTER(WHERE i.tgl_ijin_sampai IS NULL)
    FROM i LEFT JOIN m_pegawai p ON p.id=i.pegawai_id LEFT JOIN m_user u ON u.id=i.user_id''').fetchone()
  report['leave_identity_sample_columns']=['rows','null_employee','missing_employee','user_employee_difference','reversed_range','null_end_date']
 out=report_path('audit-fact-mapping.json');out.write_text(json.dumps(report,indent=2,default=str)+'\n');print(out.read_text())
if __name__=='__main__':main()
