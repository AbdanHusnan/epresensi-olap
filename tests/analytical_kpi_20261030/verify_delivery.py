"""Verify lateness delivery on the dedicated synthetic staging and mart DBs."""
import json
import subprocess


def sql(container, database, query):
    result = subprocess.run([
        'docker', 'exec', '-i', container, 'sh', '-c',
        'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"', 'psql', database,
    ], input=query, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def source(query):
    return sql('epresensi-staging-postgres', 'staging_bkd_window_test_20261030', query)


def mart(query):
    return sql('epresensi-mart-postgres', 'mart_bkd_window_test_20261030', query)


def deliver():
    payload = source('SELECT batch_payload FROM etl_control.next_mart_delivery();')
    assert payload, 'Expected an outbox payload'
    literal = "'" + payload.replace("'", "''") + "'"
    receipt = mart(f'SELECT etl_control.apply_mart_delivery({literal}::jsonb);')
    assert mart(f'SELECT etl_control.apply_mart_delivery({literal}::jsonb);') == receipt, 'Replay changed receipt'
    source("SELECT etl_control.ack_mart_delivery('" + receipt.replace("'", "''") + "'::jsonb);")


source('SELECT etl_control.prepare_mart_bootstrap();')
deliver()
initial = json.loads(mart("SELECT jsonb_object_agg(pegawai_id_sumber,lateness_status) FROM mart_kehadiran.fact_kehadiran_daily;"))
assert initial == {'1': 'ON_TIME', '2': 'LATE', '3': 'ON_TIME', '4': 'UNKNOWN'}, initial
assert mart('SELECT SUM(checkin_days),SUM(checkout_days),SUM(leave_days) FROM mart_kehadiran.fact_kehadiran_daily;') == '4|0|0'

# A correction to the first shift must change the employee's KPI; replays are safe.
source("UPDATE raw.raw_checkinout SET created_at='2026-08-03 07:05' WHERE id=1;\n"
       "SELECT etl_control.enqueue_curated_batch('WINDOW_CORRECTION',ARRAY[1]);\n"
       "SELECT etl_control.apply_curated_batch('WINDOW_CORRECTION');")
deliver()
assert mart('SELECT lateness_status FROM mart_kehadiran.fact_kehadiran_daily WHERE pegawai_id_sumber=1;') == 'LATE'
assert mart('SELECT SUM(checkin_days),SUM(checkout_days),SUM(leave_days) FROM mart_kehadiran.fact_kehadiran_daily;') == '4|0|0'

# Removing that first shift makes the later shift the first recorded shift.
source("DELETE FROM raw.raw_checkinout WHERE id=1;\n"
       "SELECT etl_control.enqueue_curated_batch('WINDOW_DELETE',p_deleted_event_ids=>ARRAY[1]);\n"
       "SELECT etl_control.apply_curated_batch('WINDOW_DELETE');")
deliver()
assert mart('SELECT lateness_status FROM mart_kehadiran.fact_kehadiran_daily WHERE pegawai_id_sumber=1;') == 'LATE'
assert mart('SELECT lateness_event_id FROM mart_kehadiran.fact_kehadiran_daily WHERE pegawai_id_sumber=1;') == '2'
print('PASS: first shift, outbox delivery, correction, deletion, replay and existing attendance totals')
