import json,subprocess,time
from pathlib import Path
out=Path(__file__).with_name('resources.jsonl')
names=['epresensi-olap-postgres','epresensi-hop-web','epresensi-mart-postgres','epresensi-staging-postgres','epresensi-hybrid-metabase-1','epresensi-hybrid-web-1']
for _ in range(360):
    p=subprocess.run(['docker','stats','--no-stream','--format','{{json .}}',*names],text=True,capture_output=True)
    with out.open('a') as f:f.write(json.dumps({'epoch':time.time(),'containers':[json.loads(l) for l in p.stdout.splitlines()],'meminfo':Path('/proc/meminfo').read_text(),'pressure':Path('/proc/pressure/memory').read_text()})+'\n')
    time.sleep(5)
