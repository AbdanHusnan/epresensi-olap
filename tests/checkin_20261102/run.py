"""November 2 check-in-only simulation from all currently active source employees.

No writes to dbabsen_restore. Isolated raw attendance fixtures only. No checkout.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
STAGE = 'staging_bkd_checkin_20261102'
MART = 'mart_bkd_checkin_20261102'
DAY = '2026-11-02'
MARK = 'CHECKIN_ONLY_20261102'
HOP = 'epresensi-hop-web'
PROJECT = '/usr/local/tomcat/webapps/ROOT/config/projects/epresensi-staging'
RUNTIME = PROJECT + '/pipelines/validation/checkin_20261102'


def command(args, content=None):
    result = subprocess.run(args, input=content, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-3500:] or result.stdout[-3500:])
    return result.stdout


def sql(query, target='stage', database=None):
    container, default = {'stage': ('epresensi-staging-postgres', STAGE),
                          'mart': ('epresensi-mart-postgres', MART),
                          'source': ('epresensi-olap-postgres', 'dbabsen_restore')}[target]
    return command(['docker', 'exec', '-i', container, 'sh', '-c',
                    'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"',
                    'sql', database or default], query).strip()


def data(query, **kwargs):
    return json.loads(sql(query, **kwargs) or 'null')


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def save(name, value):
    (OUT / (name + '.json')).write_text(json.dumps(value, indent=2) + '\n')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def runtime(path, content):
    # Generated runtime artifacts travel on stdin; connection secrets are not logged.
    command(['docker', 'exec', '-i', HOP, 'tee', path], content)
    command(['docker', 'exec', HOP, 'chmod', '600', path])


def pipeline(tree, name):
    ET.indent(tree)
    root = tree.getroot() if hasattr(tree, 'getroot') else tree
    text = ET.tostring(root, encoding='unicode', xml_declaration=True)
    (OUT / name).write_text(text)
    runtime(RUNTIME + '/' + name, text)


def hop(name):
    started = time.monotonic()
    result = subprocess.run(['docker', 'exec', HOP, 'sh', '-c',
        'cd /usr/local/tomcat/webapps/ROOT && exec ./hop-run.sh -j epresensi-staging -e presensi-staging-local -r local -f "$1" -l BASIC',
        'hop', RUNTIME + '/' + name], text=True, capture_output=True)
    (OUT / (name + '.log')).write_text(result.stdout + result.stderr)
    save(name + '_timing', {'seconds': round(time.monotonic() - started, 3), 'exit_code': result.returncode})
    require(result.returncode == 0, 'Hop failed: ' + name + '; inspect its log')
    print('Hop complete:', name, flush=True)


def import_script(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup():
    for target, database in [('stage', STAGE), ('mart', MART)]:
        require(sql('SELECT count(*) FROM pg_database WHERE datname=' + quote(database),
                    target=target, database='postgres') == '0', 'Database already exists; do not reset: ' + database)
    save('source_population', data("SELECT jsonb_build_object('active',count(*),'departments',count(DISTINCT departemen),"
         "'date_basis','current source master, simulated for 2026-11-02') FROM public.m_pegawai WHERE status IN(1,2,3,4)", target='source'))
    for target, database in [('stage', STAGE), ('mart', MART)]:
        sql('CREATE DATABASE ' + database, target=target, database='postgres')
    ddl = command(['docker', 'exec', 'epresensi-staging-postgres', 'sh', '-c',
        'exec pg_dump -U "$POSTGRES_USER" -d staging_bkd --schema-only --schema=raw --schema=curated --no-owner --no-privileges'])
    sql(ddl + '\nCREATE SCHEMA etl_control;\n')
    sql(import_script('curated_installer', 'hop/scripts/install_curated_etl.py').installation_sql())
    sql((ROOT / 'sql/staging/20261028_mart_outbox.sql').read_text())
    sql((ROOT / 'sql/mart/20261028_attendance_daily.sql').read_text(), target='mart')
    sql((ROOT / 'sql/mart/20261028_mart_incremental_etl.sql').read_text(), target='mart')
    sql((ROOT / 'sql/mart/20261030_lateness_serving.sql').read_text(), target='mart')
    command(['docker', 'exec', HOP, 'mkdir', '-p', RUNTIME])
    for template, alias, database in [('presensi_source', 'checkin_nov02_source', 'dbabsen_restore'),
                                      ('presensi_staging', 'checkin_nov02_stage', STAGE),
                                      ('presensi_mart', 'checkin_nov02_mart', MART)]:
        meta = json.loads(command(['docker', 'exec', HOP, 'cat', PROJECT + '/metadata/rdbms/' + template + '.json']))
        meta['name'] = alias
        meta['rdbms']['POSTGRESQL']['databaseName'] = database
        runtime(PROJECT + '/metadata/rdbms/' + alias + '.json', json.dumps(meta))
    tree = ET.parse(ROOT / 'hop/pipelines/curated/curated_incremental_batch.hpl')
    tree.find('./transform/connection').text = 'checkin_nov02_stage'
    pipeline(tree, 'curated.hpl')
    for path in (ROOT / 'hop/pipelines/mart').glob('*.hpl'):
        tree = ET.parse(path)
        for connection in tree.findall('./transform/connection'):
            connection.text = {'presensi_staging': 'checkin_nov02_stage', 'presensi_mart': 'checkin_nov02_mart'}[connection.text]
        pipeline(tree, path.name)
    tree = ET.parse(ROOT / 'hop/workflows/mart/curated_to_serving.hwf')
    for filename in tree.findall('./actions/action/filename'):
        filename.text = RUNTIME + '/' + Path(filename.text).name
    pipeline(tree, 'mart.hwf')
    print('Isolated databases and Hop definitions ready', flush=True)


MASTER_QUERIES = {
 'pegawai': 'SELECT p.* FROM public.m_pegawai p WHERE p.status IN(1,2,3,4)',
 'departemen': 'SELECT d.* FROM public.m_departemen d',
 'shift': 'SELECT s.* FROM public.m_shift s WHERE s.status IS TRUE',
 'jadwal': "SELECT j.* FROM public.m_jadwal j JOIN public.m_shift s ON s.id=j.jenis WHERE s.status IS TRUE AND lower(trim(j.hari)) IN ('mon','senin')",
 'user': 'SELECT u.id,u.pegawai_id FROM public.m_user u JOIN public.m_pegawai p ON p.id=u.pegawai_id WHERE p.status IN(1,2,3,4)',
 'jenis_ijin': 'SELECT j.* FROM public.m_jenis_ijin j',
 'tipe_ijin': 'SELECT t.* FROM public.m_tipe_ijin t',
}


def masters():
    for name, query in MASTER_QUERIES.items():
        require(sql(f'SELECT count(*) FROM raw.raw_{name}') == '0', 'Master already loaded: ' + name)
        text = command(['docker', 'exec', HOP, 'cat', PROJECT + '/pipelines/raw/raw_' + name + '.hpl'])
        tree = ET.ElementTree(ET.fromstring(text))
        read, write = tree.findall('./transform')
        read.find('connection').text = 'checkin_nov02_source'
        read.find('sql').text = f"SELECT src.*,CURRENT_TIMESTAMP AS extracted_at,'{MARK}'::text AS pipeline_run_id FROM ({query}) src"
        write.find('connection').text = 'checkin_nov02_stage'
        write.find('truncate').text = 'N'
        filename = 'master_' + name + '.hpl'
        pipeline(tree, filename)
        hop(filename)
        projection = "jsonb_build_object('id',src.id,'pegawai_id',src.pegawai_id)" if name == 'user' else 'to_jsonb(src)'
        expected = data("SELECT jsonb_build_object('rows',count(*),'hash',md5(string_agg(md5((" + projection + ")::text),'' ORDER BY src.id))) FROM (" + query + ') src', target='source')
        projection = "jsonb_build_object('id',r.id,'pegawai_id',r.pegawai_id)" if name == 'user' else "to_jsonb(r)-'extracted_at'-'pipeline_run_id'"
        actual = data("SELECT jsonb_build_object('rows',count(*),'hash',md5(string_agg(md5((" + projection + ")::text),'' ORDER BY r.id))) FROM raw.raw_" + name + ' r')
        require(actual == expected, 'Source/raw mismatch: ' + name)
        save('master_' + name, actual)
    require(int(sql('SELECT count(*) FROM raw.raw_pegawai')) == json.loads((OUT / 'source_population.json').read_text())['active'], 'Active population mismatch')


def fixtures():
    require(sql('SELECT count(*) FROM raw.raw_checkinout') == '0', 'Events already exist')
    sql((OUT / 'fixtures.sql').read_text())
    save('fixture_summary', data("SELECT jsonb_build_object('population',(SELECT count(*) FROM test_checkin.cohort),"
        "'direct_usable_schedule',(SELECT count(*) FROM test_checkin.cohort WHERE j1 IS NOT NULL),"
        "'without_usable_schedule',(SELECT count(*) FROM test_checkin.cohort WHERE j1 IS NULL),"
        "'phase1_checkins',(SELECT count(*) FROM raw.raw_checkinout),'checkouts',(SELECT count(*) FROM raw.raw_checkinout WHERE checktype=2),"
        "'checkin_exemptions',(SELECT count(*) FROM raw.raw_perizinan),'expected_status',(SELECT jsonb_object_agg(expected_status,n) FROM (SELECT expected_status,count(*) n FROM test_checkin.cohort GROUP BY expected_status) x))"))
    print('Complete-window fixtures ready', flush=True)


def first():
    require(sql('SELECT count(*) FROM etl_control.curated_batch') == '0', 'First manifest already exists')
    sql(f"SELECT etl_control.enqueue_curated_batch('{MARK}_FIRST',p_event_ids=>(SELECT array_agg(id ORDER BY id) FROM raw.raw_checkinout),p_leave_ids=>(SELECT array_agg(id ORDER BY id) FROM raw.raw_perizinan));")
    hop('curated.hpl')
    sql('SELECT etl_control.prepare_mart_bootstrap();')
    hop('mart.hwf')
    verify('first')


def later_checkins():
    require((OUT / 'verification_first.json').exists(), 'First check-in checkpoint has not passed')
    require((OUT / 'browser_first.json').exists(), 'Verify the first check-in dashboard before adding more check-ins')
    sql((OUT / 'later_checkins.sql').read_text())
    hop('curated.hpl')
    hop('mart.hwf')
    verify('later_checkins')


def names():
    for source_table, source_id, source_name, target_table, target_id in [
        ('raw.raw_pegawai','id','nama','mart_kehadiran.dim_pegawai','pegawai_id_sumber'),
        ('raw.raw_departemen','id','nama_departemen','mart_kehadiran.dim_departemen','departemen_id_sumber'),
    ]:
        values = sql(f'SELECT jsonb_agg(jsonb_build_object(\'id\',{source_id},\'name\',{source_name})) FROM {source_table}')
        sql(f'UPDATE {target_table} d SET nama=x.name FROM jsonb_to_recordset({quote(values)}::jsonb) AS x(id integer,name text) WHERE d.{target_id}=x.id AND d.nama IS DISTINCT FROM x.name;', target='mart')
    save('dimension_names', data("SELECT jsonb_build_object('employees',(SELECT count(*) FROM mart_kehadiran.dim_pegawai WHERE nama IS NOT NULL),'departments',(SELECT count(*) FROM mart_kehadiran.dim_departemen WHERE departemen_key<>0 AND nama IS NOT NULL))", target='mart'))


def verify(label='final'):
    require(sql('SELECT count(*) FROM raw.raw_checkinout WHERE checktype IS DISTINCT FROM 1') == '0', 'Checkout or non-check-in found')
    require(sql("SELECT count(*) FROM raw.raw_checkinout WHERE created_at::date<>DATE '2026-11-02'") == '0', 'Wrong event date')
    mismatch = int(sql("SELECT count(*) FROM test_checkin.cohort c LEFT JOIN curated.cur_attendance_daily d ON d.pegawai_id=c.emp AND d.tanggal=DATE '2026-11-02' WHERE d.lateness_status IS DISTINCT FROM c.expected_status OR d.departemen_id IS DISTINCT FROM c.dep OR d.checkout_event_count IS DISTINCT FROM 0 OR d.last_checkout_at IS NOT NULL"))
    require(mismatch == 0, 'Curated/expected employee-day mismatch: ' + str(mismatch))
    require(sql("SELECT count(*) FROM test_checkin.cohort c JOIN curated.cur_attendance_daily d ON d.pegawai_id=c.emp AND d.tanggal=DATE '2026-11-02' WHERE c.expected_status IN('LATE','ON_TIME') AND (d.lateness_event_id IS DISTINCT FROM c.n*10+1 OR d.lateness_schedule_id IS DISTINCT FROM c.j1)") == '0', 'First-shift event lineage mismatch')
    require(sql("SELECT count(*) FROM curated.cur_event_attendance c JOIN raw.raw_checkinout r ON r.id=c.checkinout_id_sumber WHERE ROW(c.waktu_event,c.jadwal_id_sumber,c.jam_masuk_sumber,c.jam_masuk_awal_sumber,c.jam_keluar_sumber,c.jam_keluar_akhir_sumber) IS DISTINCT FROM ROW(r.created_at,r.jadwal_id,r.jam_masuk,r.jam_masuk_awal,r.jam_keluar,r.jam_keluar_akhir)") == '0', 'Event snapshot changed in curated')
    oracle = data("SELECT jsonb_agg(jsonb_build_array(emp,dep,expected_status) ORDER BY emp) FROM test_checkin.cohort")
    facts = data("SELECT jsonb_agg(jsonb_build_array(pegawai_id_sumber,departemen_id_sumber,lateness_status) ORDER BY pegawai_id_sumber) FROM mart_kehadiran.fact_kehadiran_daily WHERE tanggal=DATE '2026-11-02'", target='mart')
    require(facts == oracle, 'Mart/expected employee-day mismatch')
    require(int(sql('SELECT count(*) FROM mart_kehadiran.fact_kehadiran_daily', target='mart')) == len(oracle), 'Extra fact rows or dates')
    require(sql('SELECT sum(checkin_event_count) FROM mart_kehadiran.fact_kehadiran_daily', target='mart') == sql('SELECT count(*) FROM raw.raw_checkinout'), 'Check-in events lost or multiplied')
    require(sql('SELECT count(*) FROM curated.cur_event_attendance WHERE shift_is_active_sumber IS DISTINCT FROM TRUE') == '0', 'Non-active shift used')
    require(sql('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL') == '0', 'Pending outbox')
    require(sql('SELECT count(*) FROM mart_kehadiran.fact_kehadiran_daily WHERE checkout_event_count<>0 OR has_pulang OR last_checkout_at IS NOT NULL', target='mart') == '0', 'Checkout found in facts')
    result = data("SELECT jsonb_build_object('population',count(*),'active',sum(active_employee_days),'checkins',sum(checkin_days),'checkouts',sum(checkout_days),'leave',sum(leave_days),'statuses',(SELECT jsonb_object_agg(lateness_status,n) FROM (SELECT lateness_status,count(*) n FROM mart_kehadiran.fact_kehadiran_daily GROUP BY lateness_status) x)) FROM mart_kehadiran.fact_kehadiran_daily", target='mart')
    expected_departments = data("SELECT jsonb_agg(jsonb_build_array(dep,late,assessed) ORDER BY dep) FROM (SELECT dep,count(*) FILTER(WHERE expected_status='LATE') late,count(*) FILTER(WHERE expected_status IN('LATE','ON_TIME')) assessed FROM test_checkin.cohort GROUP BY dep) x")
    actual_departments = data("SELECT jsonb_agg(jsonb_build_array(departemen_id_sumber,late,assessed) ORDER BY departemen_id_sumber) FROM (SELECT departemen_id_sumber,count(*) FILTER(WHERE lateness_status='LATE') late,count(*) FILTER(WHERE lateness_status IN('LATE','ON_TIME')) assessed FROM serving.v_lateness_employee_daily GROUP BY departemen_id_sumber) x", target='mart')
    require(actual_departments == expected_departments, 'Department serving mismatch')
    require(sql("SELECT count(*) FROM curated.cur_event_attendance WHERE jam_masuk_awal_sumber IS NULL OR jam_keluar_akhir_sumber IS NULL") == '0', 'Incomplete retained window')
    save('verification_' + label, {'passed': True, 'date': DAY, 'results': result, 'departments': len(actual_departments), 'checkouts': 0})
    print(json.dumps({'checkpoint': label, **result}), flush=True)


def replay():
    before = sql("SELECT md5(string_agg(pegawai_id_sumber::text||'/'||tanggal::text||'/'||xmin::text,'|' ORDER BY pegawai_id_sumber,tanggal)) FROM mart_kehadiran.fact_kehadiran_daily", target='mart')
    sql(f"SELECT etl_control.enqueue_curated_batch('{MARK}_REPLAY',p_event_ids=>(SELECT array_agg(id ORDER BY id) FROM raw.raw_checkinout),p_leave_ids=>(SELECT array_agg(id ORDER BY id) FROM raw.raw_perizinan));")
    hop('curated.hpl')
    require(sql('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL') == '0', 'Replay unexpectedly changed daily facts')
    after = sql("SELECT md5(string_agg(pegawai_id_sumber::text||'/'||tanggal::text||'/'||xmin::text,'|' ORDER BY pegawai_id_sumber,tanggal)) FROM mart_kehadiran.fact_kehadiran_daily", target='mart')
    require(before == after, 'Replay changed mart row versions')
    save('replay', {'passed': True, 'mart_versions_unchanged': True})


def report():
    first = json.loads((OUT / 'verification_first.json').read_text())
    final = json.loads((OUT / 'verification_final.json').read_text())
    require(first['results'] == final['results'], 'Additional check-ins changed employee KPI totals')
    audit = data("SELECT jsonb_build_object('events',count(*),'checkout_events',count(*) FILTER(WHERE checktype=2),'first_date',min(created_at)::date,'last_date',max(created_at)::date,'phase1',(SELECT count(*) FROM test_checkin.events WHERE phase=1),'phase2',(SELECT count(*) FROM test_checkin.events WHERE phase=2),'phase2_extracted_epoch',(SELECT extract(epoch FROM min(r.extracted_at)) FROM raw.raw_checkinout r JOIN test_checkin.events e USING(id) WHERE e.phase=2),'non_active_shift_events',(SELECT count(*) FROM curated.cur_event_attendance WHERE shift_is_active_sumber IS DISTINCT FROM TRUE)) FROM raw.raw_checkinout")
    checkpoint_epoch = (OUT / 'browser_first.json').stat().st_mtime
    require(audit['phase2_extracted_epoch'] > checkpoint_epoch, 'Additional events preceded the first browser checkpoint')
    late = final['results']['statuses']['LATE']
    assessed = late + final['results']['statuses']['ON_TIME']
    save('summary', {'passed': True, 'date': DAY, 'weekday': 'Monday',
        'population': final['results']['population'], 'population_basis': 'All currently active source employees; simulated future date',
        'departments': final['departments'], 'assessed': assessed, 'late': late,
        'late_percentage': round(100 * late / assessed, 2),
        'excused': final['results']['statuses']['EXCUSED'], 'unassessed': final['results']['statuses']['NOT_ASSESSED'],
        'events': audit, 'first_dashboard_verified_before_additional_events': True,
        'checkout_loaded': False, 'replay': json.loads((OUT / 'replay.json').read_text()),
        'http': json.loads((OUT / 'http_verification.json').read_text())['passed'],
        'browser': json.loads((OUT / 'browser_final.json').read_text())['passed'],
        'stage_database': STAGE, 'mart_database': MART})
    print('PASS: all November check-in checkpoints; stop before checkout', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['setup', 'masters', 'fixtures', 'first', 'later_checkins', 'names', 'verify', 'replay', 'report'])
    args = parser.parse_args()
    globals()[args.phase]()
