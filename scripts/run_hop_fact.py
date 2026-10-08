"""Run/resume the historical Hop workflow and audit it after successful completion."""
from datetime import datetime
import fcntl
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def main():
    logdir = ROOT / 'logs' / 'hop-fact'
    logdir.mkdir(parents=True, exist_ok=True)
    with (logdir / 'runner.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('A fact workflow runner is already active')
        stamp = datetime.now(ZoneInfo('Asia/Jakarta')).strftime('%Y%m%d-%H%M%S')
        logpath = logdir / (stamp + '.log')
        statepath = logdir / 'latest.json'
        state = {'started_at': stamp, 'status': 'running', 'log': str(logpath)}

        def save():
            statepath.write_text(json.dumps(state, indent=2) + '\n')

        save()
        with logpath.open('w', buffering=1) as log:
            command = ('cd /usr/local/tomcat/webapps/ROOT && ./hop-run.sh '
                       '--project=presensi --environment=presensi-local --runconfig=local '
                       '--file=/usr/local/tomcat/webapps/ROOT/config/projects/presensi/workflows/fact_kehadiran_all.hwf '
                       '--level=Minimal')
            try:
                result = subprocess.run(['docker', 'exec', 'epresensi-hop-web', 'bash', '-c', command],
                                        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                state['hop_exit_code'] = result.returncode
                state['status'] = 'validating' if result.returncode == 0 else 'failed'
                save()
                if result.returncode == 0:
                    result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate_hop_fact.py'), '--complete'],
                                            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                    state['validation_exit_code'] = result.returncode
                    state['status'] = 'complete' if result.returncode == 0 else 'validation_failed'
            except Exception as error:
                state['status'] = 'failed'
                state['error'] = type(error).__name__
                raise
            finally:
                state['finished_at'] = datetime.now(ZoneInfo('Asia/Jakarta')).isoformat()
                save()
        return 0 if state['status'] == 'complete' else 1


if __name__ == '__main__':
    if sys.argv[1:] == ['--detach']:
        logdir = ROOT / 'logs' / 'hop-fact'
        logdir.mkdir(parents=True, exist_ok=True)
        with (logdir / 'runner.log').open('a') as output:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve())],
                                       cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        print('Started fact runner PID', process.pid)
    else:
        sys.exit(main())
