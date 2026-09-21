# Phase 10 — Master orchestration

Entry point: `etl.pipeline.master`. Requires the existing OLAP tables and
`etl_control.pipeline_runs` / `pipeline_state`; no schema migration is required.
Run from the repository root using `.venv` and the existing `.env` settings.

## Execution and dependencies

1. Read and validate source references in one repeatable-read, read-only snapshot.
2. Upsert department, employee, schedule and leave-type dimensions, then calendar.
3. Run incremental facts: read OLD permission coverage, upsert permission changes,
   recompute affected employee-days, and update both source checkpoints.
4. Refresh permission facts and rebuild every employee-day in the requested date
   window, including employees with no attendance event.

Existing transforms and loaders supply the business rules. `analytical_user`
remains part of initial load; it is not refreshed by this master command.
Calendar coverage includes the requested window, existing calendar coverage and
source permission ranges. Events outside that coverage fail safely; extend the
requested dates and rerun. Dimension/schedule/day-off changes outside the daily
window require an explicit historical backfill. `--reconcile` replays existing
events/permissions but does not populate every historical employee-day.

## Run and preview

```bash
# Read-only source/daily validation for a known period
.venv/bin/python -m etl.pipeline.master --start-date 2026-08-03 --end-date 2026-08-05

# Apply that period, with complete event/permission reconciliation
.venv/bin/python -m etl.pipeline.master --start-date 2026-08-03 --end-date 2026-08-05 --reconcile --apply

# Scheduler window: yesterday and today, determined in Asia/Jakarta
.venv/bin/python -m etl.pipeline.master --recent-days 2 --reconcile --apply
```

Preview does not write dimensions, facts, checkpoints or run logs. Its JSON
explicitly marks the incremental stage `not_executed`: it validates the source
and requested daily facts, but cannot verify incremental joins against refreshed
dimensions without materializing them. Use the separate incremental preview on
an already synchronized warehouse when that validation is needed.

## Transaction, checkpoint and recovery contract

- Master and incremental hold the same session advisory lock through all commits.
  Initial-load CLI and replacement APIs use the same key with transaction locks.
  Old standalone dimension/fact commands do not participate: do not schedule
  them alongside these entry points. Low-level master/incremental functions are
  caller-owned transaction primitives; use `execute_pipeline` / CLI operationally.
- `RUNNING` is committed before data processing. All dimension/fact changes,
  both source checkpoints, and `SUCCESS` commit together at the end. There is no
  partial-stage commit or stage-resume checkpoint. A retry restarts the full master
  using the last committed source watermarks and the same requested daily window.
- An exception rolls back the entire data transaction. `FAILED` is then committed
  separately, with the failing stage in `error_message`. A disconnected database
  may prevent this final write; the original error is retained in stderr.
- A killed process can leave `RUNNING`. The next applying master, after obtaining
  the shared lock, marks abandoned master/incremental runs `FAILED` before starting.
- Reruns upsert by existing keys: no duplicate facts or dimensions. Permission
  loader timestamps can change even when business data stays the same.
- This is transaction rollback, not undo of an already committed run. Correct the
  source and rerun an explicit period for committed corrections. Database restore
  requires a separately reviewed backup/restore procedure.
- Watermark limitations from [incremental loading](incremental-load.md) still
  apply. Scheduled master uses `--reconcile` to recover late committed events.
  Hard deletes and historical employee transfers are not modeled.

The final JSON includes the date window, run ID, stage counts and incremental
report. Stage progress goes to stderr/journal; it is provisional until SUCCESS.
`pipeline_runs.rows_extracted` records prepared/processed rows, not distinct OLTP
rows; inserted/updated sum dimension and attendance operations and exclude the
permission loader (reported separately as `permission_rows_written`). A row
processed by both incremental and daily stages can contribute twice.

```sql
SELECT run_id, pipeline_name, status, finished_at,
       rows_extracted, rows_inserted, rows_updated, error_message
FROM etl_control.pipeline_runs
WHERE pipeline_name IN ('master_orchestration', 'incremental_facts')
ORDER BY run_id DESC LIMIT 20;

SELECT * FROM etl_control.pipeline_state
WHERE pipeline_name IN ('fact_kehadiran', 'fact_perizinan');
```

On failure, inspect the stage/error, correct the cause, and rerun the SAME explicit
date range. Do not manually advance watermarks. After downtime longer than the
scheduler's two-day window, backfill the missed dates explicitly before resuming.
Large windows hold one transaction and prepare up to one full employee-day batch
at a time (existing limit: 500,000 employees per day); benchmark before increasing
frequency. `--batch-size` controls incremental recomputation only.

## Scheduler and verification

See [systemd instructions](../deploy/systemd/README.md). The supplied master unit
runs daily at 00:17 Asia/Jakarta with bounded retries and journald logging.
Installing/enabling it is a deployment action; adding these files does not start
ETL or change the existing timer. External failure notifications belong to Phase 11.

```bash
.venv/bin/python -m unittest discover -s tests -v
RUN_POSTGRES_TESTS=1 .venv/bin/python -m unittest discover -s tests -v
systemd-analyze --user verify deploy/systemd/olap-master.service deploy/systemd/olap-master.timer
```

The opt-in PostgreSQL suite uses isolated, uncommitted schema copies and rolls
them back. Master tests exercise dependency order, read-only preview, lock
contention, transaction boundaries, and connection cleanup. Database tests cover
two profiles of 205 employees over three days: injected failure after both
checkpoints, complete rollback, rebuilding missing daily rows, and rerun equality
of business data/checkpoints. These are correctness tests, not production-volume
benchmarks or production cutover.
