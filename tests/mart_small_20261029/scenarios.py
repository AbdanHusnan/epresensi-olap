#!/usr/bin/env python3
"""Resumable scenarios; mutations confined to dedicated small test databases."""
import json
from datetime import date,timedelta
import run as t

sample=json.loads((t.OUT/'sample_manifest.json').read_text())
bycase={x['scenario']:x for x in sample}
DAY=bycase[0]['daily']['tanggal']
D1=(date.fromisoformat(DAY)+timedelta(days=1)).isoformat()
D2=(date.fromisoformat(DAY)+timedelta(days=2)).isoformat()
D3=(date.fromisoformat(DAY)+timedelta(days=3)).isoformat()
D4=(date.fromisoformat(DAY)+timedelta(days=4)).isoformat()
NEWDEP=2147000001
UNKNOWN=2147000101
INACTIVE=2147000102
MOVED=2147000103

def done(label):return t.scalar(f'SELECT count(*) FROM test_small.results WHERE phase={t.q(label)}')=='1'

def init():
    t.sql('CREATE TABLE IF NOT EXISTS test_small.actions(label text PRIMARY KEY,before_versions jsonb,before_agg jsonb);')

def mutation(label,statement):
    if t.scalar(f'SELECT count(*) FROM test_small.actions WHERE label={t.q(label)}')=='0':
        before=t.versions();agg=t.aggregate_versions()
        t.sql('BEGIN;'+statement+f"; INSERT INTO test_small.actions VALUES({t.q(label)},{t.q(json.dumps(before))}::jsonb,{t.q(json.dumps(agg))}::jsonb); COMMIT;")
    return t.data(f'SELECT before_versions FROM test_small.actions WHERE label={t.q(label)}')

def unchanged_except(before,allowed):
    after=t.versions()
    for key,version in before.items():
        if key not in allowed:t.require(after.get(key)==version,'Unrelated fact rewritten: '+key)

def insert_statement(table,items):
    cols=','.join(t.columns(table))
    return f'INSERT INTO {table} ({cols}) SELECT {cols} FROM jsonb_populate_recordset(NULL::{table},{t.q(json.dumps(items))}::jsonb);'

def straightforward(label,statement,allowed,check=lambda:None):
    if done(label):return
    before=mutation(label,statement)
    t.hop(label)
    unchanged_except(before,allowed)
    check()
    t.verify(label)


def history_check():
    person=bycase[1]['employee'];olddep=bycase[1]['department']
    history=t.data(f"SELECT jsonb_agg(jsonb_build_object('date',tanggal,'department',departemen_id_sumber) ORDER BY tanggal) FROM mart_kehadiran.fact_kehadiran_daily WHERE pegawai_id_sumber={person}",target=True)
    t.require(history==[{'date':DAY,'department':olddep},{'date':D1,'department':NEWDEP}],'Mutation rewrote historical department')
    t.save('department_history',{'employee':person,'history':history,'passed':True})


def target_state():
    return t.data("""SELECT jsonb_build_object(
      'fact',(SELECT md5(COALESCE(string_agg(to_jsonb(f)::text,'|' ORDER BY pegawai_id_sumber,tanggal),'')) FROM mart_kehadiran.fact_kehadiran_daily f),
      'agg',(SELECT md5(COALESCE(string_agg(to_jsonb(a)::text,'|' ORDER BY tanggal,departemen_key),'')) FROM serving.agg_kehadiran_departemen_harian a),
      'batches',(SELECT count(*) FROM etl_control.mart_batch),
      'receipts',(SELECT count(*) FROM etl_control.mart_delivery_receipt),
      'sequence',(SELECT last_sequence FROM etl_control.mart_delivery_cursor))""",target=True)


def main():
    init()
    person=bycase[2]['employee']
    straightforward('incremental_checkout',f"UPDATE curated.cur_attendance_daily SET checkout_event_count=1,last_checkout_at={t.q(DAY+' 21:00:00')} WHERE pegawai_id={person} AND tanggal={t.q(DAY)}",{f'{person}/{DAY}'})

    # The employee assignment changes only in the NEW date snapshot.
    original=bycase[1]
    population={**original['population'],'tanggal':D1,'departemen_id':NEWDEP}
    daily={**original['daily'],'tanggal':D1,'departemen_id':NEWDEP,'checkin_event_count':0,'checkout_event_count':0,'first_checkin_at':None,'last_checkout_at':None}
    straightforward('department_new_snapshot',insert_statement('curated.cur_employee_population_daily',[population])+insert_statement('curated.cur_attendance_daily',[daily]),set(),history_check)
    person=original['employee']
    straightforward('late_event_old_date',f"""UPDATE curated.cur_attendance_daily d SET checkin_event_count=2,first_checkin_at={t.q(DAY+' 06:55:00')},departemen_id=p.departemen_id
      FROM curated.cur_employee_population_daily p WHERE d.pegawai_id={person} AND d.tanggal={t.q(DAY)} AND (p.pegawai_id,p.tanggal)=(d.pegawai_id,d.tanggal)""",{f'{person}/{DAY}'},history_check)

    person=bycase[5]['employee']
    straightforward('leave_direction_correction',f'UPDATE curated.cur_attendance_daily SET has_excused_checkin=false,has_excused_checkout=true WHERE pegawai_id={person}',{f'{person}/{DAY}'})

    # A failed target refresh must roll back fact, dimensions, aggregates and checkpoints.
    if not done('rollback_retry'):
        person=bycase[0]['employee']
        before=mutation('rollback_retry',f"UPDATE curated.cur_attendance_daily SET checkin_event_count=1,first_checkin_at={t.q(DAY+' 08:00:00')} WHERE pegawai_id={person}")
        state=target_state()
        t.sql("""CREATE SCHEMA IF NOT EXISTS test_small;
          CREATE OR REPLACE FUNCTION test_small.fail_refresh() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'TEST_INJECTED_REFRESH_FAILURE'; END $$;
          DROP TRIGGER IF EXISTS fail_refresh ON serving.agg_kehadiran_departemen_harian;
          CREATE TRIGGER fail_refresh BEFORE INSERT ON serving.agg_kehadiran_departemen_harian FOR EACH STATEMENT EXECUTE FUNCTION test_small.fail_refresh();""",target=True)
        result=t.hop('rollback_injected_failure',expect_failure=True)
        t.require('TEST_INJECTED_REFRESH_FAILURE' in result.stdout+result.stderr,'Failure did not reach refresh injection')
        t.require(target_state()==state,'Target partially committed on failure')
        t.require(t.scalar('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL')=='1','Failed batch acknowledged')
        t.sql('DROP TRIGGER fail_refresh ON serving.agg_kehadiran_departemen_harian;',target=True)
        t.hop('rollback_retry')
        unchanged_except(before,{f'{person}/{DAY}'})
        t.verify('rollback_retry')
        t.save('rollback_evidence',{'target_unchanged_after_failure':True,'outbox_remained_pending':True,'retry_passed':True})

    # Source rollback must also roll back the outbox and sequence allocation.
    if not done('source_rollback'):
        state=t.data('SELECT to_jsonb(s) FROM etl_control.mart_outbox_stream s')
        person=bycase[0]['employee']
        t.sql(f'BEGIN; UPDATE curated.cur_attendance_daily SET checkin_event_count=9 WHERE pegawai_id={person}; ROLLBACK;')
        t.require(t.data('SELECT to_jsonb(s) FROM etl_control.mart_outbox_stream s')==state,'Source rollback left sequence gap')
        t.verify('source_rollback')

    if not done('commit_before_ack_retry'):
        person=bycase[3]['employee']
        before=mutation('commit_before_ack_retry',f"UPDATE curated.cur_attendance_daily SET checkin_event_count=1,first_checkin_at={t.q(DAY+' 07:30:00')} WHERE pegawai_id={person}")
        t.hop('apply_without_ack',apply_only=True)
        t.require(t.scalar('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL')=='1','Apply-only unexpectedly acknowledged')
        committed=target_state();versions=t.versions();agg=t.aggregate_versions()
        t.hop('commit_before_ack_retry')
        t.require(target_state()==committed and t.versions()==versions and t.aggregate_versions()==agg,'Replay rewrote target')
        unchanged_except(before,{f'{person}/{DAY}'})
        t.verify('commit_before_ack_retry')

    # Two committed source versions must remain distinct even if delivery is delayed.
    if not done('immutable_queued_payloads'):
        person=bycase[0]['employee']
        mutation('immutable_payload_first',f'UPDATE curated.cur_attendance_daily SET checkin_event_count=2 WHERE pegawai_id={person}')
        mutation('immutable_payload_second',f'UPDATE curated.cur_attendance_daily SET checkin_event_count=3 WHERE pegawai_id={person}')
        pending=t.data(f"SELECT jsonb_agg((payload->>'checkin_event_count')::integer ORDER BY batch_sequence) FROM etl_control.mart_outbox_item WHERE pegawai_id={person} AND batch_sequence IN(SELECT batch_sequence FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL)")
        t.require(pending==[2,3],'Queued payloads lost earlier version')
        t.hop('immutable_first_version')
        t.require(t.scalar(f'SELECT checkin_event_count FROM mart_kehadiran.fact_kehadiran_daily WHERE pegawai_id_sumber={person}',target=True)=='2','First delivery read newer mutable source')
        t.hop('immutable_second_version')
        t.verify('immutable_queued_payloads')

    # Isolated synthetic edge fixtures, never real assignment corrections.
    base=bycase[0]
    up={**base['population'],'pegawai_id':UNKNOWN,'tanggal':D2,'departemen_id':None,'perlu_review':True,'alasan_review':'TEST_UNKNOWN_DEPARTMENT'}
    ud={**base['daily'],'pegawai_id':UNKNOWN,'tanggal':D2,'departemen_id':None,'perlu_review':True,'alasan_review':'TEST_UNKNOWN_DEPARTMENT'}
    ip={**base['population'],'pegawai_id':INACTIVE,'tanggal':D3,'departemen_id':None,'is_employee_active':False,'status_sumber':5}
    ind={**base['daily'],'pegawai_id':INACTIVE,'tanggal':D3,'departemen_id':None,'is_employee_active':False,'checkin_event_count':1,'first_checkin_at':D3+'T07:00:00','perlu_review':True,'alasan_review':'TEST_INACTIVE_EVENT'}
    straightforward('unknown_and_inactive',insert_statement('curated.cur_employee_population_daily',[up,ip])+insert_statement('curated.cur_attendance_daily',[ud,ind]),set())
    straightforward('synthetic_key_correction',f"""UPDATE curated.cur_employee_population_daily SET pegawai_id={MOVED},tanggal={t.q(D4)} WHERE pegawai_id={UNKNOWN};
      UPDATE curated.cur_attendance_daily SET pegawai_id={MOVED},tanggal={t.q(D4)} WHERE pegawai_id={UNKNOWN};""",{f'{UNKNOWN}/{D2}'})
    straightforward('synthetic_delete',f'DELETE FROM curated.cur_attendance_daily WHERE pegawai_id={MOVED}; DELETE FROM curated.cur_employee_population_daily WHERE pegawai_id={MOVED}',{f'{MOVED}/{D4}'})
    t.require(t.scalar(f'SELECT count(*) FROM serving.agg_kehadiran_departemen_harian WHERE tanggal IN ({t.q(D2)},{t.q(D4)})',target=True)=='0','Empty partition left behind')

    if not done('rejected_deliveries'):
        payload=t.data('SELECT payload FROM etl_control.mart_delivery_receipt ORDER BY batch_sequence LIMIT 1',target=True)
        before=target_state()
        bad=json.loads(json.dumps(payload));bad['items'][0]['payload']['checkin_event_count']=999
        result=t.sql(f'SELECT etl_control.apply_mart_delivery({t.q(json.dumps(bad))}::jsonb)',target=True,check=False)
        t.require(result.returncode!=0 and 'Replay payload changed' in result.stderr,'Changed replay accepted')
        bad=json.loads(json.dumps(payload));bad['sequence']=int(before['sequence'])+2
        result=t.sql(f'SELECT etl_control.apply_mart_delivery({t.q(json.dumps(bad))}::jsonb)',target=True,check=False)
        t.require(result.returncode!=0 and 'out-of-order' in result.stderr,'Out-of-order delivery accepted')
        result=t.sql(f"SELECT etl_control.confirm_mart_delivery({t.q(json.dumps({'stream_id':payload['stream_id'],'sequence':99999}))}::jsonb)",target=True,check=False)
        t.require(result.returncode!=0 and 'not committed' in result.stderr,'Uncommitted receipt confirmed')
        result=t.sql("UPDATE etl_control.mart_outbox_item SET payload=payload WHERE batch_sequence=1",check=False)
        t.require(result.returncode!=0 and 'immutable' in result.stderr,'Committed outbox mutable')
        t.require(target_state()==before,'Rejected deliveries changed target')
        t.verify('rejected_deliveries')

    final=t.verify('final')
    after=t.guards();before=json.loads((t.OUT/'protected_before.json').read_text())
    t.require(after==before,'Reference or active database changed')
    t.save('protected_after',after)
    phases=t.data('SELECT jsonb_agg(phase ORDER BY phase) FROM test_small.results')
    t.save('summary',{'passed':True,'source':t.SOURCE,'target':t.TARGET,'reference':t.REFERENCE,'initial_employees':12,'final_fact_rows':final['fact_rows'],'phases':phases,'protected_databases_unchanged':True,'historical_department_preserved':True,'late_event_uses_old_snapshot':True,'scope':'downstream curated snapshot contract; upstream raw ETL not rerun'})

if __name__=='__main__':main()
