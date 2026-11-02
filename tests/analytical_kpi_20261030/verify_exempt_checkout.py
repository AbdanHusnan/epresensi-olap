"""Check checkout evidence and check-in exemption in isolated window test DBs."""
import json
import subprocess


def sql(container, database, query):
    return subprocess.run(['docker', 'exec', '-i', container, 'sh', '-c',
        'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"', 'psql', database],
        input=query, text=True, capture_output=True, check=True).stdout.strip()


def source(query):
    return sql('epresensi-staging-postgres', 'staging_bkd_window_test_20261030', query)


def mart(query):
    return sql('epresensi-mart-postgres', 'mart_bkd_window_test_20261030', query)


source("""
INSERT INTO raw.raw_user(id,pegawai_id,extracted_at,pipeline_run_id) VALUES(2,2,now(),'WINDOW_TEST');
INSERT INTO raw.raw_tipe_ijin(id,nama,extracted_at,pipeline_run_id) VALUES(4,'TEST',now(),'WINDOW_TEST');
INSERT INTO raw.raw_jenis_ijin(id,nama,tipe_id,setengah_hari,extracted_at,pipeline_run_id) VALUES(10,'TEST',4,false,now(),'WINDOW_TEST');
INSERT INTO raw.raw_perizinan(id,pegawai_id,user_id,jenis_ijin,tipe_ijin,approval,tgl_ijin,tgl_ijin_sampai,extracted_at,pipeline_run_id)
 VALUES(2,2,2,10,2,true,'2026-08-03','2026-08-03',now(),'WINDOW_TEST');
INSERT INTO raw.raw_checkinout(id,pegawai_id,created_at,checktype,work_code,jadwal_id,jam_masuk_awal,jam_masuk,jam_keluar,jam_keluar_akhir,extracted_at,pipeline_run_id)
 VALUES(7,3,'2026-08-03 14:30',2,100,1000,'06:00','07:00','14:00','15:00',now(),'WINDOW_TEST');
SELECT etl_control.enqueue_curated_batch('WINDOW_EXEMPT_CHECKOUT',ARRAY[7],ARRAY[2]);
SELECT etl_control.apply_curated_batch('WINDOW_EXEMPT_CHECKOUT');
""")
assert source('SELECT checkout_window_status FROM curated.cur_event_attendance WHERE checkinout_id_sumber=7;') == 'IN_WINDOW'
assert source('SELECT lateness_status FROM curated.cur_attendance_daily WHERE pegawai_id=2;') == 'EXCUSED'
payload = source('SELECT batch_payload FROM etl_control.next_mart_delivery();')
receipt = mart("SELECT etl_control.apply_mart_delivery('" + payload.replace("'", "''") + "'::jsonb);")
source("SELECT etl_control.ack_mart_delivery('" + receipt.replace("'", "''") + "'::jsonb);")
assert mart('SELECT lateness_status FROM mart_kehadiran.fact_kehadiran_daily WHERE pegawai_id_sumber=2;') == 'EXCUSED'
assert mart('SELECT SUM(checkin_days),SUM(checkout_days),SUM(leave_days) FROM mart_kehadiran.fact_kehadiran_daily;') == '4|1|1'
print('PASS: checkout window classified, excused check-in excluded, delivery preserves attendance measures')
