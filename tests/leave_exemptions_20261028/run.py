#!/usr/bin/env python3
"""Synthetic leave-contract tests. No source or active raw writes."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DB = 'staging_bkd_leave_v3_test_20261028'
BASE = ['docker', 'exec', 'epresensi-staging-postgres']


def hop_check(psql):
    project = '/usr/local/tomcat/webapps/ROOT/config/projects/epresensi-staging'
    connection = 'leave_v3_test_20261028'
    metadata = json.loads(subprocess.check_output(['docker', 'exec', 'epresensi-hop-web',
        'cat', project + '/metadata/rdbms/presensi_staging.json']))
    metadata['name'] = connection
    metadata['rdbms']['POSTGRESQL']['databaseName'] = DB
    # Connection secrets remain in memory/container, never in local artifacts.
    subprocess.run(['docker', 'exec', '-i', 'epresensi-hop-web', 'tee',
        project + '/metadata/rdbms/' + connection + '.json'],
        input=json.dumps(metadata).encode(), stdout=subprocess.DEVNULL, check=True)
    tree = ET.parse(ROOT / 'hop/pipelines/curated/curated_incremental_batch.hpl')
    tree.find('./info/name').text = 'leave_exemptions_test'
    tree.find('./transform/connection').text = connection
    ET.indent(tree)
    tree.write(OUT / 'leave_exemptions_test.hpl', encoding='UTF-8', xml_declaration=True)
    runtime = project + '/pipelines/validation/leave_exemptions_20261028'
    subprocess.run(['docker', 'exec', 'epresensi-hop-web', 'mkdir', '-p', runtime], check=True)
    subprocess.run(['docker', 'cp', str(OUT / 'leave_exemptions_test.hpl'),
        'epresensi-hop-web:' + runtime + '/leave_exemptions_test.hpl'], check=True)
    subprocess.run(psql, input=b"UPDATE raw.raw_perizinan SET approval=false WHERE id=5;\n"
        b"SELECT etl_control.enqueue_curated_batch('HOP_LEAVE_REVOKE',p_leave_ids=>ARRAY[5]);\n",
        stdout=subprocess.DEVNULL, check=True)
    with (OUT / 'hop.log').open('wb') as output:
        subprocess.run(['docker', 'exec', '-w', '/usr/local/tomcat/webapps/ROOT',
            'epresensi-hop-web', './hop-run.sh', '-j', 'epresensi-staging', '-e',
            'presensi-staging-local', '-r', 'local', '-f', runtime + '/leave_exemptions_test.hpl',
            '-l', 'BASIC'], stdout=output, stderr=subprocess.STDOUT, check=True)
    with (OUT / 'hop_result.txt').open('wb') as output:
        subprocess.run(psql, input=b"SELECT assert_true((SELECT no_checkin_days=1 AND no_checkout_days=1 "
            b"AND leave_days=0 FROM curated.cur_attendance_daily WHERE pegawai_id=5),'Hop revoked exemption');\n"
            b"SELECT assert_true((SELECT status='APPLIED' FROM etl_control.curated_batch "
            b"WHERE batch_id='HOP_LEAVE_REVOKE'),'Hop batch committed');\n"
            b"SELECT result FROM etl_control.curated_batch WHERE batch_id='HOP_LEAVE_REVOKE';\n",
            stdout=output, check=True)
    print('PASS: actual Hop pipeline revoked leave and restored both attendance requirements')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reset-synthetic', action='store_true')
    parser.add_argument('--hop-only', action='store_true', help='Run Hop check on the completed SQL fixture')
    args = parser.parse_args()
    psql = ['docker', 'exec', '-i', 'epresensi-staging-postgres', 'psql', '-X', '-v',
            'ON_ERROR_STOP=1', '-U', 'admin_staging', '-d', DB]
    if args.hop_only:
        hop_check(psql)
        return
    exists = subprocess.check_output(BASE + ['psql', '-X', '-U', 'admin_staging', '-d', 'postgres',
        '-Atc', f"SELECT count(*) FROM pg_database WHERE datname='{DB}'"], text=True).strip()
    if exists == '1':
        if not args.reset_synthetic:
            parser.error('Test database exists; use --reset-synthetic only to recreate this synthetic fixture')
        subprocess.run(BASE + ['dropdb', '-U', 'admin_staging', DB], check=True)
    subprocess.run(BASE + ['createdb', '-U', 'admin_staging', DB], check=True)
    ddl = subprocess.check_output(BASE + ['pg_dump', '-U', 'admin_staging', '-d', 'staging_bkd',
        '--schema-only', '--schema=raw', '--schema=curated', '--no-owner', '--no-privileges'])
    spec = importlib.util.spec_from_file_location('installer', ROOT / 'hop/scripts/install_curated_etl.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    subprocess.run(psql, input=ddl + b'\nCREATE SCHEMA etl_control;\n' +
                   installer.installation_sql().encode(), stdout=subprocess.DEVNULL, check=True)
    with (OUT / 'results.txt').open('wb') as output:
        subprocess.run(psql, input=(OUT / 'integration.sql').read_bytes(), stdout=output, check=True)
    print('PASS: leave transaction-type integration tests in ' + DB)
    hop_check(psql)


if __name__ == '__main__':
    main()
