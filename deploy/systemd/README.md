# Five-minute incremental ETL scheduler

These are user-level systemd units for `/home/piramida/OLAP`. The service uses
the project's virtual environment and the existing dotenv connection settings.
No credentials are embedded in these files. Adjust the two absolute service
paths when deploying elsewhere.

The timer fires at minutes 00, 05, 10, ..., 55. A still-running service is not
started again; missed ticks are not queued. Each execution uses `--apply` and
therefore writes to OLAP. The first run may replay the entire source when no
checkpoints exist. There is no automatic reconciliation schedule in this timer.

Install and activate as the project owner:

```bash
systemctl --user link /home/piramida/OLAP/deploy/systemd/olap-incremental.service /home/piramida/OLAP/deploy/systemd/olap-incremental.timer
systemctl --user daemon-reload
systemctl --user enable --now olap-incremental.timer
```

Inspect execution and disable the schedule:

```bash
systemctl --user list-timers olap-incremental.timer
journalctl --user -u olap-incremental.service -n 100 --no-pager
systemctl --user disable --now olap-incremental.timer
```

Disabling the timer does not stop an already running ETL transaction. Master,
incremental and initial load now share a lock; competing executions fail fast.
Avoid standalone dimension/fact writers while this scheduler is active.
For operation after logout and automatic start on boot, the account must have
systemd lingering enabled by the host administrator. Check using
`loginctl show-user piramida -p Linger`; without it, availability follows the
user manager/session lifecycle.

## Phase 10 daily master

`olap-master.timer` runs at 00:17 Asia/Jakarta every day. Its service refreshes
dimensions, reconciles existing events/permissions, and rebuilds yesterday and
today. Calendar dates are selected in Asia/Jakarta independently of host timezone.
Persistent scheduling catches a missed activation once, not every missed date;
backfill explicitly after an outage longer than two days.

The service retries after 60 seconds, with at most three starts per hour. It logs
to journald and leaves FAILED status visible in systemd after retries are exhausted.
It does not send external alerts. Investigate permanent validation errors before
retrying. After fixing the cause, use `systemctl --user reset-failed olap-master.service`
and restart the service if it was rate-limited.

Files are provided but are not enabled automatically. After validating the target
environment, deploy as the project owner:

```bash
systemd-analyze --user verify deploy/systemd/olap-master.service deploy/systemd/olap-master.timer
systemctl --user link /home/piramida/OLAP/deploy/systemd/olap-master.service /home/piramida/OLAP/deploy/systemd/olap-master.timer
systemctl --user daemon-reload
systemctl --user enable --now olap-master.timer
systemctl --user list-timers olap-master.timer
journalctl --user -u olap-master.service -n 100 --no-pager
```

An existing five-minute incremental timer can remain, but the shared lock means
its executions may fail while the daily master runs. No conflicting run is queued.
Use only the daily master if five-minute freshness is unnecessary. Do not change
the existing timer without accounting for the required data freshness.

Disable future daily runs with `systemctl --user disable --now olap-master.timer`.
This leaves a currently running service untouched. See the
[master runbook](../../docs/master-orchestration.md) for recovery and backfill.
