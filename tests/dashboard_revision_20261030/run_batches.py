"""Four guarded simulation checkpoints: Oct 30 AM/PM, then Oct 31 AM/PM.

Batch 1 only is authorized for immediate execution. Source database is read-only.
Reuses the proven Hop adapter; raw fixtures live in a new isolated database pair.
"""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('checkin_adapter', ROOT/'tests/checkin_20261102/run.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.STAGE = 'staging_bkd_gradual_20261030'
base.MART = 'mart_bkd_gradual_20261030'
base.DAY = '2026-10-30'
base.MARK = 'GRADUAL_20261030_BATCH1'
base.OUT = OUT
base.RUNTIME = base.PROJECT + '/pipelines/validation/gradual_20261030'
# setup/masters use explicit connection aliases. Generate isolated aliases rather
# than replacing any connection definitions belonging to the November test.
import inspect
for name in ('setup', 'masters'):
    source = inspect.getsource(getattr(base, name)).replace('checkin_nov02', 'gradual_oct30').replace('2026-11-02', '2026-10-30')
    exec(compile(source, __file__, 'exec'), base.__dict__)
base.MASTER_QUERIES['jadwal'] = "SELECT j.* FROM public.m_jadwal j JOIN public.m_shift s ON s.id=j.jenis WHERE s.status IS TRUE AND lower(trim(j.hari)) IN ('fri','jumat','jum\u0027at','sat','sabtu')".replace("'jum'at'", "'jum''at'")


def setup():
    base.setup()
    base.masters()
    # Save fixed extraction totals; these are a simulation snapshot, not an
    # assertion that every current employee was active historically.
    base.save('setup_checkpoint', {'stage': base.STAGE, 'mart': base.MART, 'passed': True})


def batch1():
    base.require((OUT/'setup_checkpoint.json').exists(), 'Run setup first')
    base.require(base.sql('SELECT count(*) FROM raw.raw_checkinout') == '0', 'Batch 1 already exists; do not reset')
    text = (ROOT/'tests/checkin_20261102/fixtures.sql').read_text()
    text = text.replace('staging_bkd_checkin_20261102', base.STAGE).replace('2026-11-02', base.DAY).replace('20261102', '20261030')
    text = text.replace("('mon','senin')", "('fri','jumat','jum''at')")
    text = text.replace('CHECKIN_ONLY_20261030', base.MARK).replace('FUTURE_TEST_POPULATION_20261030', 'SIMULATION_SNAPSHOT_20261030')
    (OUT/'batch1_fixtures.sql').write_text(text)
    base.sql(text)
    base.sql(f"SELECT etl_control.enqueue_curated_batch('{base.MARK}',p_event_ids=>(SELECT array_agg(id ORDER BY id) FROM raw.raw_checkinout),p_leave_ids=>(SELECT array_agg(id ORDER BY id) FROM raw.raw_perizinan));")
    base.hop('curated.hpl')
    base.sql('SELECT etl_control.prepare_mart_bootstrap();')
    base.hop('mart.hwf')
    base.names()
    verify()


def verify():
    oracle = base.data("SELECT jsonb_agg(jsonb_build_array(emp,dep,expected_status) ORDER BY emp) FROM test_checkin.cohort")
    actual = base.data("SELECT jsonb_agg(jsonb_build_array(pegawai_id_sumber,departemen_id_sumber,lateness_status) ORDER BY pegawai_id_sumber) FROM mart_kehadiran.fact_kehadiran_daily WHERE tanggal=DATE '2026-10-30'", target='mart')
    base.require(actual == oracle, 'Fact population/department/lateness differs from fixture oracle')
    base.require(base.sql('SELECT count(*) FROM raw.raw_checkinout WHERE checktype<>1') == '0', 'Only morning check-ins allowed in batch 1')
    base.require(base.sql('SELECT count(*) FROM mart_kehadiran.fact_kehadiran_daily WHERE has_pulang OR checkout_event_count<>0 OR last_checkout_at IS NOT NULL', target='mart') == '0', 'Checkout found before batch 2')
    base.require(base.sql('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL') == '0', 'Pending delivery')
    totals = base.data("SELECT jsonb_build_object('population',count(*),'active',sum(active_employee_days),'checkins',sum(checkin_days),'checkouts',sum(checkout_days),'leave',sum(leave_days),'first_date',min(tanggal),'last_date',max(tanggal),'departments',count(DISTINCT departemen_id_sumber)) FROM mart_kehadiran.fact_kehadiran_daily", target='mart')
    base.save('batch1_verification', {'passed': True, 'batch': 1, 'date': base.DAY, 'totals': totals, 'next': 'Batch 2: 30 October afternoon checkout; wait for user review'})
    print(json.dumps(totals), flush=True)


if __name__ == '__main__':
    phase = sys.argv[1]
    if phase not in ('setup','batch1','verify'): raise SystemExit('Only setup, batch1 and verify are currently enabled; later batches wait for review.')
    globals()[phase]()
