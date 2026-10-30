"""Recreate/update GUI comparison dashboards using the configured local BI engines."""
import json
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(HERE/'create_metabase.py')],check=True)
r=subprocess.run(['docker','exec','-i','epresensi-hybrid-superset-1','/app/.venv/bin/python','-'],input=(HERE/'create_superset.py').read_text(),text=True,capture_output=True)
if r.returncode:
    print(r.stderr[-6000:],file=sys.stderr)
    raise SystemExit('Superset dashboard creation failed.')
manifest=json.loads(next(line[9:] for line in r.stdout.splitlines() if line.startswith('MANIFEST=')))
(HERE/'superset-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for role,dashboard in manifest.items():print('Superset',role,dashboard['url'])
