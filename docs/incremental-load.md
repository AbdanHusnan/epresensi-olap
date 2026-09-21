# Incremental attendance and leave

Run from the repository root with the existing `.venv` and `.env`:

```bash
# Read-only preview, including recomputation and validation
.venv/bin/python -m etl.pipeline.incremental

# Commit facts, both source checkpoints, and SUCCESS together
.venv/bin/python -m etl.pipeline.incremental --apply

# Replay all existing source transactions to recover missed changes
.venv/bin/python -m etl.pipeline.incremental --reconcile
.venv/bin/python -m etl.pipeline.incremental --reconcile --apply
```

No database writes occur during preview. The implementation does not modify OLTP.
Use `--batch-size` (default 1000 employees per date) and `--overlap-minutes`
(default 5). Delta records and affected keys remain in memory; recomputation is
batched, but writes remain one OLAP transaction. A large first replay requires
capacity planning. Existing loaders issue per-row attendance upserts.

## Processing contract

- `t_checkinout` is insert-only, with positive increasing IDs that are not reused.
  New `work_code = 1` events identify employee-days; the ID checkpoint advances
  over all work codes. `created_at` defines the business date.
- `t_perizinan` changes are selected using `COALESCE(updated_at, created_at)` and
  an inclusive overlap. NULL timestamps are replayed on every run. Every approval,
  employee, date, or other relevant change must update the timestamp.
- Old approved coverage is read from `fact_perizinan` before upsert and combined
  with new approved coverage. Rejected/pending ranges add no new coverage.
- Recompute reads all attendance events, days off, and approved permissions for
  each affected key from the same OLTP snapshot. Existing transforms are reused.
  Two approved overlapping permissions fail validation, as in the original ETL.
- Dimensions must already exist, including every impacted calendar date, even
  dates in historical corrections or future approved permissions. Missing
  dimensions fail the run; checkpoints do not advance.
- A missing checkpoint pair triggers replay from ID zero and all permissions.
  It does not assume that MAX(id) was included in the previous initial load.
  States use existing `fact_kehadiran` and `fact_perizinan` names, so subsequent
  initial loads clear them. A partial or incompatible state pair fails explicitly.
- A shared advisory lock prevents concurrent master, incremental and initial-load
  runs. Standalone dimension/fact writers do not share this lock. A crash can leave
  a RUNNING log; uncommitted facts/state roll back. The next applying master
  marks abandoned master/incremental RUNNING logs FAILED while holding the lock.
- Run-log inserted/updated counts describe attendance facts; permission rows read
  and other details are returned in the JSON report. Permission replay may update
  `etl_loaded_at` even when business values are unchanged.

## Watermark limits and reconciliation

PostgreSQL sequence allocation order is not commit order. For example, ID 10 can
commit after ID 11 was checkpointed. A plain ID watermark can miss ID 10 even when
events are immutable. The timestamp overlap also cannot guarantee capture of
transactions delayed beyond the overlap, or updates with unchanged/backdated
timestamps. Snapshot isolation alone does not solve either issue.

Run `--reconcile` periodically (for example nightly, subject to measured workload)
to replay all existing events/permissions and recover these cases. Strict capture
without full replay requires a commit-ordered CDC/audit mechanism or a verified
source writer contract. Do not describe watermark-only operation as lossless.
Reconciliation cannot recover hard-deleted records; deletes remain out of scope.

This command only responds to attendance/permission changes. It does not create
every employee-day for a newly opened date: employees with neither event nor leave
need a separate daily population job to produce TIDAK_ABSEN rows. It does not sync
dimensions or analytical_user, and master/schedule/day-off edits are not independent
triggers. Recompute uses current dimensions; historical transfers are not modeled.
Keep OLTP/OLAP timestamp conventions consistent with the existing initial load;
this command does not reinterpret stored timestamps.

Tests (no live database writes):

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_incremental.py' -v
```
