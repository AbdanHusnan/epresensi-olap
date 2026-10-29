#!/usr/bin/env python3
"""Deploy Hop metadata/files only. No pipeline run, bootstrap or data load."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '/usr/local/tomcat/webapps/ROOT/config'
PROJECT = BASE + '/projects/epresensi-staging'
HOP = 'epresensi-hop-web'


def read_json(path):
    return json.loads(subprocess.check_output(['docker', 'exec', HOP, 'cat', path]))


def write_file(path, data):
    subprocess.run(['docker', 'exec', '-i', HOP, 'sh', '-c',
                    'umask 077; cat > "$1"', 'write-file', path],
                   input=data, text=True, check=True, stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply-metadata', action='store_true')
    args = parser.parse_args()
    if not args.apply_metadata:
        print('Plan: connect Hop to epresensi_mart; add presensi_mart metadata and deploy workflow and two pipelines. No execution.')
        return
    target = json.loads(subprocess.check_output(['docker', 'inspect', 'epresensi-mart-postgres']))[0]
    env = dict(v.split('=', 1) for v in target['Config']['Env'] if '=' in v)
    variables = {
        'HOP_MART_HOST': 'epresensi-mart-postgres', 'HOP_MART_PORT': '5432',
        'HOP_MART_DB': 'mart_bkd', 'HOP_MART_USER': env['POSTGRES_USER'],
        'HOP_MART_PASSWORD': env['POSTGRES_PASSWORD'],
    }
    # Preserve all unrelated settings and never print or write credentials locally.
    environment_path = BASE + '/environments/presensi-staging-local.json'
    configuration = read_json(environment_path)
    existing = {v['name']: v for v in configuration['variables']}
    for name, value in variables.items():
        if name in existing:
            existing[name]['value'] = value
        else:
            configuration['variables'].append({'name': name, 'value': value, 'description': 'Mart connection; downstream pipeline not scheduled'})
    write_file(environment_path, json.dumps(configuration, indent=2))
    connection = read_json(PROJECT + '/metadata/rdbms/presensi_staging.json')
    connection['name'] = 'presensi_mart'
    props = connection['rdbms']['POSTGRESQL']
    for key, var in [('hostname', 'HOST'), ('port', 'PORT'), ('databaseName', 'DB'), ('username', 'USER'), ('password', 'PASSWORD')]:
        props[key] = '${HOP_MART_' + var + '}'
    # Dedicated connection. Workflow boundary and receipt check guarantee committed target state.
    props['attributes'] = {
        'SUPPORTS_BOOLEAN_DATA_TYPE': 'Y', 'SUPPORTS_TIMESTAMP_DATA_TYPE': 'Y',
        'QUOTE_ALL_FIELDS': 'N', 'SQL_CONNECT': '', 'EXTRA_OPTION_POSTGRESQL.defaultRowFetchSize': '0',
    }
    write_file(PROJECT + '/metadata/rdbms/presensi_mart.json', json.dumps(connection, indent=2))
    networks = json.loads(subprocess.check_output(['docker', 'inspect', HOP]))[0]['NetworkSettings']['Networks']
    if 'epresensi_mart' not in networks:
        subprocess.run(['docker', 'network', 'connect', 'epresensi_mart', HOP], check=True)
    for folder in ['pipelines/mart', 'workflows/mart']:
        subprocess.run(['docker', 'exec', HOP, 'mkdir', '-p', PROJECT + '/' + folder], check=True)
        for source in (ROOT / 'hop' / folder).iterdir():
            if source.suffix in {'.hpl', '.hwf'}:
                write_file(PROJECT + '/' + folder + '/' + source.name, source.read_text())
    print('Pipeline and presensi_mart metadata deployed. No engine started; no data loaded.')


if __name__ == '__main__':
    main()
