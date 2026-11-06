#!/usr/bin/env python3
"""Load simulated November transactions into actual staging/mart using real masters.

Source is read-only. Existing raw history is preserved. Daily committed manifests
and an audit ledger make interruption/retry safe. Run phases in documented order.
"""
import argparse
import copy
import datetime as dt
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
MARK = 'SIMULATED_202611'
PROJECT = '/usr/local/tomcat/webapps/ROOT/config/projects/epresensi-staging'
OUT = ROOT / 'runtime/month_202611'
OUT.mkdir(parents=True, exist_ok=True)
TARGETS = {'stage': ('epresensi-staging-postgres', 'staging_bkd'),
           'mart': ('epresensi-mart-postgres', 'mart_bkd'),
           'source': ('epresensi-olap-postgres', 'dbabsen_restore')}


def command(args, content=None):
    # Preserve embedded CR/LF in master CSV fields; text mode normalizes them.
    p = subprocess.run(args, input=content.encode() if content is not None else None, capture_output=True)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).decode()[-5000:])
    return p.stdout.decode()


def sql(query, target='stage'):
    container, database = TARGETS[target]
    return command(['docker', 'exec', '-i', container, 'sh', '-c',
                    'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"',
                    'sql', database], query).strip()


def data(query, target='stage'):
    return json.loads(sql(query, target) or 'null')


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def runtime(path, content):
    command(['docker', 'exec', '-i', '-u', 'root', 'epresensi-hop-web', 'sh', '-c',
             'umask 077; cat > "$1" && chown hop:hop "$1"', 'write', path], content)


def hop(filename):
    p = subprocess.run(['docker', 'exec', 'epresensi-hop-web', 'sh', '-c',
        'cd /usr/local/tomcat/webapps/ROOT && exec ./hop-run.sh -j epresensi-staging -e presensi-staging-local -r local -f "$1" -l MINIMAL',
        'hop', PROJECT + '/' + filename], text=True, capture_output=True)
    with (OUT / 'hop.log').open('a') as f:
        f.write(p.stdout + p.stderr)
    if p.returncode:
        raise RuntimeError('Hop failed; inspect runtime/month_202611/hop.log: ' + (p.stderr + p.stdout)[-2500:])


def configure():
    # Refresh actual connection endpoints from the container configuration without
    # exposing credentials in process arguments, repository files, or output.
    config_path = '/usr/local/tomcat/webapps/ROOT/config/environments/presensi-staging-local.json'
    config = json.loads(command(['docker', 'exec', 'epresensi-hop-web', 'cat', config_path]))
    existing = {v['name']: v for v in config['variables']}
    for key, container, database in [('STAGING', *TARGETS['stage']), ('MART', *TARGETS['mart'])]:
        info = json.loads(command(['docker', 'inspect', container]))[0]
        env = dict(v.split('=', 1) for v in info['Config']['Env'] if '=' in v)
        for suffix, value in {'HOST': container, 'PORT': '5432', 'DB': database,
                              'USER': env['POSTGRES_USER'], 'PASSWORD': env['POSTGRES_PASSWORD']}.items():
            name = 'HOP_' + key + '_' + suffix
            if name in existing:
                existing[name]['value'] = value
            else:
                config['variables'].append({'name': name, 'value': value})
        path = PROJECT + '/metadata/rdbms/presensi_' + ('staging' if key == 'STAGING' else 'mart') + '.json'
        meta = json.loads(command(['docker', 'exec', 'epresensi-hop-web', 'cat', path]))
        for prop, suffix in [('hostname','HOST'),('port','PORT'),('databaseName','DB'),('username','USER'),('password','PASSWORD')]:
            meta['rdbms']['POSTGRESQL'][prop] = '${HOP_' + key + '_' + suffix + '}'
        runtime(path, json.dumps(meta, indent=2))
        networks = json.loads(command(['docker','inspect','epresensi-hop-web']))[0]['NetworkSettings']['Networks']
        network = 'epresensi_' + ('staging' if key == 'STAGING' else 'mart')
        if network not in networks:
            command(['docker','network','connect',network,'epresensi-hop-web'])
    runtime(config_path, json.dumps(config, indent=2))
    for folder in ['pipelines/curated', 'pipelines/mart', 'pipelines/operations', 'workflows/mart']:
        command(['docker','exec','epresensi-hop-web','mkdir','-p',PROJECT+'/'+folder])
        for path in (ROOT/'hop'/folder).iterdir():
            if path.suffix in ('.hpl','.hwf'):
                runtime(PROJECT+'/'+folder+'/'+path.name,path.read_text())
    print('Actual staging_bkd / mart_bkd Hop connections deployed', flush=True)


def masters():
    # COPY into a temporary table, then upsert. No TRUNCATE or source mutations.
    for name in ('pegawai','departemen','shift','jadwal','user','jenis_ijin','tipe_ijin'):
        columns = data("SELECT json_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='raw' AND table_name='raw_"+name+"' AND column_name NOT IN ('extracted_at','pipeline_run_id')")
        projection = ','.join('"'+c+'"' for c in columns)
        csv = sql('COPY (SELECT '+projection+' FROM public.m_'+name+') TO STDOUT WITH (FORMAT csv)', 'source')
        update = ','.join('"'+c+'"=EXCLUDED."'+c+'"' for c in columns if c != 'id')
        # COPY data uses CSV and explicit columns; source values never become SQL.
        sql('BEGIN; CREATE TEMP TABLE master_load (LIKE raw.raw_'+name+' INCLUDING DEFAULTS);\n'
            +"ALTER TABLE master_load ALTER COLUMN extracted_at SET DEFAULT now(); ALTER TABLE master_load ALTER COLUMN pipeline_run_id SET DEFAULT '"+MARK+"_MASTER';\n"
            +'COPY master_load ('+projection+') FROM STDIN WITH (FORMAT csv);\n'+csv+'\n\\.\n'
            +"UPDATE master_load SET extracted_at=now(),pipeline_run_id='"+MARK+"_MASTER';\n"
            +'INSERT INTO raw.raw_'+name+' SELECT * FROM master_load ON CONFLICT (id) DO UPDATE SET '+update
            +',extracted_at=EXCLUDED.extracted_at,pipeline_run_id=EXCLUDED.pipeline_run_id; COMMIT;')
        print('Master refreshed:',name,flush=True)
    check_masters()


def check_masters():
    result={}
    for name in ('pegawai','departemen','shift','jadwal','user','jenis_ijin','tipe_ijin'):
        columns=data("SELECT json_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='raw' AND table_name='raw_"+name+"' AND column_name NOT IN ('extracted_at','pipeline_run_id')")
        projection=','.join('"'+c+'"' for c in columns)
        prefix="SELECT jsonb_build_object('rows',count(*),'hash',md5(string_agg(md5(to_jsonb(t)::text),'' ORDER BY t.id))) FROM (SELECT "+projection+" FROM "
        expected=data(prefix+'public.m_'+name+') t','source')
        actual=data(prefix+'raw.raw_'+name+') t')
        assert expected==actual, 'Master/source mismatch: '+name
        result[name]={'rows':actual['rows'],'matches_source':True}
    (OUT/'master_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


def prepare():
    sql((ROOT/'hop/operations/month_202611.sql').read_text())
    sql("ALTER FUNCTION etl_control.apply_mart_delivery(jsonb) SET work_mem='128MB'; ALTER FUNCTION etl_control.apply_mart_delivery(jsonb) SET jit=off;",'mart')
    print(sql("SELECT jsonb_build_object('active_employees',(SELECT count(*) FROM etl_control.simulation_employee_202611),'schedule_day_combinations',(SELECT count(*) FROM etl_control.simulation_schedule_202611))"),flush=True)


def load():
    for n in range(1,31):
        day = f'2026-11-{n:02d}'
        batch = MARK+'_'+day.replace('-','')
        sql('SELECT etl_control.seed_simulated_day_202611('+quote(day)+'::date);')
        status = sql('SELECT status FROM etl_control.curated_batch WHERE batch_id='+quote(batch))
        if status != 'APPLIED':
            # Explicit manifest selection avoids consuming unrelated queued work.
            tree = ET.parse(ROOT/'hop/pipelines/curated/curated_incremental_batch.hpl')
            tree.find('./transform/sql').text = 'SELECT etl_control.apply_curated_batch('+quote(batch)+')::text AS batch_result'
            path = 'pipelines/curated/simulated_month_day.hpl'
            runtime(PROJECT+'/'+path,ET.tostring(tree.getroot(),encoding='unicode'))
            hop(path)
        print('Curated complete:',day,flush=True)
    if sql('SELECT bootstrap_prepared FROM etl_control.mart_outbox_stream') == 'f':
        sql('SELECT etl_control.prepare_mart_bootstrap();')
    drain()
    names()
    verify()


def drain():
    pending=int(sql('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL'))
    if not pending:return
    # Unroll exactly the current queue length in one Hop JVM. Every apply and ack
    # remains a separate finished pipeline, preserving independent connections.
    template=ET.parse(ROOT/'hop/workflows/mart/curated_to_serving.hwf')
    workflow=copy.deepcopy(template.getroot())
    workflow.find('name').text='drain_month_202611'
    workflow.find('description').text='Drain the committed monthly queue; each apply is followed by fresh-connection receipt confirmation and acknowledgement.'
    actions=workflow.find('actions');original=list(actions)
    for child in list(actions):actions.remove(child)
    start=copy.deepcopy(original[0]);actions.append(start)
    hops=workflow.find('hops')
    for child in list(hops):hops.remove(child)
    previous='Start'
    for n in range(1,pending+1):
        for index,source in enumerate(original[1:]):
            action=copy.deepcopy(source)
            name=f'{source.find("name").text} {n:02d}'
            action.find('name').text=name
            action.find('yloc').text=str(160+n*120)
            actions.append(action)
            h=ET.SubElement(hops,'hop')
            for tag,value in [('from',previous),('to',name),('enabled','Y'),('evaluation','Y'),('unconditional','Y' if previous=='Start' else 'N')]:
                ET.SubElement(h,tag).text=value
            previous=name
    ET.indent(workflow)
    content=ET.tostring(workflow,encoding='unicode',xml_declaration=True)
    (OUT/'drain_month_202611.hwf').write_text(content)
    runtime(PROJECT+'/workflows/mart/drain_month_202611.hwf',content)
    print('Draining',pending,'durable mart batches in one Hop workflow',flush=True)
    hop('workflows/mart/drain_month_202611.hwf')
    assert sql('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL')=='0','Queue grew or drain did not finish; rerun drain'
    print('All mart batches committed, confirmed and acknowledged',flush=True)


def names():
    for source, name, dest, key in [('pegawai','nama','dim_pegawai','pegawai_id_sumber'),
                                     ('departemen','nama_departemen','dim_departemen','departemen_id_sumber')]:
        csv = sql('COPY (SELECT id,'+name+' FROM raw.raw_'+source+') TO STDOUT WITH (FORMAT csv)')
        sql('BEGIN; CREATE TEMP TABLE display_names(id integer PRIMARY KEY,nama text);\nCOPY display_names FROM STDIN WITH (FORMAT csv);\n'+csv+'\n\\.\n'
            +'UPDATE mart_kehadiran.'+dest+' d SET nama=n.nama FROM display_names n WHERE d.'+key+'=n.id AND d.valid_from<=DATE \'2026-11-30\' AND (d.valid_to IS NULL OR d.valid_to>DATE \'2026-11-01\') AND d.nama IS DISTINCT FROM n.nama; COMMIT;', 'mart')


def verify():
    mismatches = int(sql("""SELECT count(*) FROM etl_control.simulation_day_employee_202611 s
      JOIN etl_control.simulation_employee_202611 p USING(emp)
      LEFT JOIN curated.cur_attendance_daily d ON d.pegawai_id=s.emp AND d.tanggal=s.tanggal
      WHERE d.pegawai_id IS NULL OR d.departemen_id IS DISTINCT FROM p.dep
      OR d.is_employee_active IS DISTINCT FROM true
      OR d.checkin_event_count IS DISTINCT FROM CASE WHEN scenario IN('ON_TIME','LATE','PARTIAL_AFTERNOON','MISSING_CHECKOUT') THEN 1 ELSE 0 END
      OR d.checkout_event_count IS DISTINCT FROM CASE WHEN scenario IN('ON_TIME','LATE','PARTIAL_MORNING','MISSING_CHECKIN') THEN 1 ELSE 0 END
      OR d.has_excused_checkin IS DISTINCT FROM (scenario IN('FULL_DAY_IZIN','PARTIAL_MORNING'))
      OR d.has_excused_checkout IS DISTINCT FROM (scenario IN('FULL_DAY_IZIN','PARTIAL_AFTERNOON'))
      OR d.has_full_day_leave IS DISTINCT FROM (scenario='FULL_DAY_IZIN')
      OR d.has_partial_day_leave IS DISTINCT FROM (scenario IN('PARTIAL_MORNING','PARTIAL_AFTERNOON'))
      OR d.lateness_status IS DISTINCT FROM CASE
        WHEN scenario IN('FULL_DAY_IZIN','PARTIAL_MORNING') THEN 'EXCUSED'
        WHEN scenario='LATE' THEN 'LATE'
        WHEN scenario IN('ON_TIME','PARTIAL_AFTERNOON','MISSING_CHECKOUT') THEN 'ON_TIME'
        ELSE 'NOT_ASSESSED' END"""))
    assert mismatches==0, 'Scenario oracle mismatch: '+str(mismatches)
    stage = data("SELECT jsonb_agg(x ORDER BY tanggal) FROM (SELECT tanggal,count(*) employees,sum(checkin_event_count) checkins,sum(checkout_event_count) checkouts,sum(leave_days) leaves,sum(no_checkin_days) missing_checkin,sum(no_checkout_days) missing_checkout,count(*) FILTER(WHERE lateness_status='LATE') late FROM curated.cur_attendance_daily WHERE tanggal BETWEEN DATE '2026-11-01' AND DATE '2026-11-30' GROUP BY tanggal) x")
    mart = data("SELECT jsonb_agg(x ORDER BY tanggal) FROM (SELECT tanggal,count(*) employees,sum(checkin_event_count) checkins,sum(checkout_event_count) checkouts,sum(leave_days) leaves,sum(no_checkin_days) missing_checkin,sum(no_checkout_days) missing_checkout,count(*) FILTER(WHERE lateness_status='LATE') late FROM mart_kehadiran.fact_kehadiran_daily WHERE tanggal BETWEEN DATE '2026-11-01' AND DATE '2026-11-30' GROUP BY tanggal) x", 'mart')
    population = int(sql('SELECT count(*) FROM etl_control.simulation_employee_202611'))
    assert stage == mart and len(mart)==30 and all(x['employees']==population for x in mart), 'Daily reconciliation failed'
    aggregate = data("SELECT jsonb_agg(x ORDER BY tanggal) FROM (SELECT tanggal,sum(active_employee_days) employees,sum(checkin_days) checkins,sum(checkout_days) checkouts,sum(leave_days) leaves,sum(no_checkin_days) missing_checkin,sum(no_checkout_days) missing_checkout FROM serving.v_kehadiran_departemen_harian GROUP BY tanggal) x", 'mart')
    expected = data("SELECT jsonb_agg(x ORDER BY tanggal) FROM (SELECT tanggal,sum(active_employee_days) employees,sum(checkin_days) checkins,sum(checkout_days) checkouts,sum(leave_days) leaves,sum(no_checkin_days) missing_checkin,sum(no_checkout_days) missing_checkout FROM mart_kehadiran.fact_kehadiran_daily GROUP BY tanggal) x", 'mart')
    assert aggregate==expected,'Serving reconciliation failed'
    shared=['tanggal','is_employee_active','population_basis','checkin_event_count','checkout_event_count',
            'first_checkin_at','last_checkout_at','has_manual_event','has_valid_leave','has_full_day_leave',
            'has_partial_day_leave','has_excused_checkin','has_excused_checkout','lateness_status',
            'lateness_event_id','lateness_schedule_id','lateness_reason','active_employee_days',
            'checkin_days','checkout_days','no_checkin_days','no_checkout_days','leave_days',
            'required_checkin_days','required_checkout_days','excused_checkin_days','excused_checkout_days',
            'required_checkin_present_days','required_checkout_present_days','perlu_review','alasan_review',
            'is_date_final','date_assignment_policy','source_snapshot_at']
    fingerprints={}
    for target,table,employee,department in [('stage','curated.cur_attendance_daily','pegawai_id','departemen_id'),
                                             ('mart','mart_kehadiran.fact_kehadiran_daily','pegawai_id_sumber','departemen_id_sumber')]:
        projection=','.join([employee,department]+shared)
        fingerprints[target]=data("SET TIME ZONE 'UTC'; SELECT jsonb_object_agg(tanggal,h) FROM (SELECT tanggal,md5(string_agg(md5(jsonb_build_array("+projection+")::text),'' ORDER BY "+employee+")) h FROM "+table+" WHERE tanggal BETWEEN DATE '2026-11-01' AND DATE '2026-11-30' GROUP BY tanggal) x",target)
    assert fingerprints['stage']==fingerprints['mart'],'Source/fact row fingerprints differ'

    assert sql('SELECT count(*) FROM etl_control.mart_outbox_batch WHERE delivered_at IS NULL')=='0'
    result = {'passed':True,'staging_database':'staging_bkd','mart_database':'mart_bkd','simulated':True,'active_employees':population,'employee_days':population*30,'daily':mart,'row_fingerprints':fingerprints['mart'],
              'scenarios':data('SELECT jsonb_object_agg(scenario,n) FROM (SELECT scenario,count(*) n FROM etl_control.simulation_day_employee_202611 GROUP BY scenario) x')}
    (OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['configure','masters','check_masters','prepare','load','drain','names','verify'])
    globals()[p.parse_args().phase]()
