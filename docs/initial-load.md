# Replace dummy data and perform an initial load

For the agreed 82,000-employee, one-month, 25-department fixture, use
[the August 2026 Jawa Timur profile](dummy-jatim-202608.md). The examples below
use the older `legacy` generator profile.

The example dataset has **82,000 fictional employees** across five departments.
These numbers are illustrative; choose the size and distributions from production aggregates.
The example period below is **2026-03-01 through 2026-08-31**, the last six complete
months: **15,088,000 attendance facts**, plus raw attendance events and leave requests.
The dates and random seed are explicit so the sample can be regenerated.

## What changes

1. Generate a compressed JSON Lines dataset in employee batches.
2. Back up the source, clear its records, and bulk-insert the new source data.
3. Back up OLAP, clear the analytical tables and relevant checkpoints, load
   dimensions, leave requests, user analytics, then attendance in daily batches.
4. Reconcile loaded counts before committing.

Both resets preserve existing tables, indexes, constraints, views, and grants.
The source and OLAP resets are **separate transactions**. Each rolls back its own
changes on failure. If OLAP fails after the source succeeds, rerun only the OLAP
initial load. Do not run ordinary ETL jobs, source writers, or dashboard refreshes
during replacement. The OLAP transaction holds table locks until it commits.
Allow disk space for the generated file, full backups, replacement tables,
indexes, and PostgreSQL transaction logs before running the full dataset.

The source reset explicitly clears **all public table records**, including old
application configuration/reference/log records. The eleven artifact tables are populated, plus `m_previleges` when present
in the source schema. The seed inserts ID 1 (`Pegawai Dummy`) before employees
to satisfy the application default `m_pegawai.status = 1`. This is an ETL/dashboard fixture, not a full
working application seed: geographic reference data, authentication credentials,
roles, and unrelated application configuration are not generated. Inspect the
preview table list before choosing `--all-public-records`.

The warehouse reset includes `dim_departemen`, `dim_pegawai`, `dim_calendar`,
`dim_jadwal_kerja`, `dim_jenis_izin`, `fact_perizinan`, `fact_kehadiran`, and
`analytical_user`. Existing ETL run history is retained, with an `initial_load`
success entry added on commit. Checkpoints for the affected pipelines are removed.
There is no `TRUNCATE ... CASCADE`; unexpected foreign-key dependencies stop the
transaction. A failed initial-load run rolls back its run-log entry too; retain
command output for failure details.

## Prerequisites

Run commands from the repository root using the existing `.venv` and `.env`.
The existing connectors read `OLTP_*` and `OLAP_*`; no credentials belong in Git.
The commands require the existing source and warehouse schemas. `source.sql` is
only a minimal schema for isolated integration testing, not a migration to run on
the existing application database.

Use a `pg_dump` client compatible with the connected server version. Check the
server with `SHOW server_version;` and the client with `pg_dump --version`.
If needed, set `DUMMY_PG_DUMP` to the absolute path of the compatible executable.
The runbook does not assume a particular installed server/client version.

The commands invoke `pg_dump` automatically **before changing records**. Backups
use custom format and owner-only file permissions. Existing backup or dataset
files are never overwritten. A failed dump prevents the reset; its incomplete
file must not be treated as a valid recovery backup. Choose a new output filename
when retrying after a failure.

## 1. Generate the new source data

```bash
.venv/bin/python -m etl.dummy.generate \
  --employees 82000 \
  --start-date 2026-03-01 --end-date 2026-08-31 \
  --seed 42 --output data/dummy-82000-202603-202608.jsonl.gz
```

Generation streams batches of 100 employees. Memory does not grow with the entire
dataset. A completion trailer detects truncated/interrupted output during loading.

## 2. Preview and replace source records

```bash
.venv/bin/python -m etl.dummy.seed data/dummy-82000-202603-202608.jsonl.gz

.venv/bin/python -m etl.dummy.seed data/dummy-82000-202603-202608.jsonl.gz \
  --apply --all-public-records --confirm-db epresensi_clean \
  --backup backups/oltp-before-replacement.dump
```

The first command validates the artifact and lists the source tables to clear.
The second performs backup, truncate, bulk insert, identity sequence alignment,
and count reconciliation. All foreign-key checks remain enabled. The schema is
not recreated. Do not seed the warehouse directly with source-shaped records.

## 3. Preview and perform the warehouse initial load

```bash
.venv/bin/python -m etl.pipeline.initial_load \
  --start-date 2026-03-01 --end-date 2026-08-31

.venv/bin/python -m etl.pipeline.initial_load \
  --start-date 2026-03-01 --end-date 2026-08-31 \
  --apply --confirm-db epresensi_analytics \
  --backup backups/olap-before-initial-load.dump
```

Preview runs the transformations read-only against the source snapshot. It does
not temporarily modify OLAP. At full scale, both preview and load can take time.
The write command repeats validation while bulk-loading and rolls everything back
if any day fails. Only the requested attendance/calendar period is loaded; all
source leave requests are retained as request facts. Daily leave expansion is
clipped to the attendance period.

The initial load uses existing transformation rules, with bulk COPY in place of
row-by-row upserts because the destination has just been cleared. Rerunning with
`--apply` performs another full replacement and requires a new backup path.
Normal pipeline upserts alone will not remove obsolete employees or facts.

## 4. Check the result and refresh the dashboard

Run on OLAP:

```sql
SELECT count(*) FROM dim_pegawai;      -- 82000
SELECT count(*) FROM fact_kehadiran;   -- 15088000 for this date range
SELECT min(tanggal), max(tanggal) FROM fact_kehadiran;
SELECT status_kehadiran, count(*) FROM fact_kehadiran GROUP BY 1;
SELECT status_pengajuan, count(*) FROM fact_perizinan GROUP BY 1;
SELECT count(*) AS orphan_leave_references
FROM fact_kehadiran k LEFT JOIN fact_perizinan p USING (perizinan_id)
WHERE k.perizinan_id IS NOT NULL AND p.perizinan_id IS NULL; -- 0
ANALYZE dim_pegawai;
ANALYZE fact_perizinan;
ANALYZE fact_kehadiran;
```

Refresh the dashboard's dataset/cache and use the generated date range. No
dashboard code or dashboard connector is present in this repository.

## Recovery

Keep source and warehouse backup paths together. Restore custom-format backups
with a compatible `pg_restore`, preferably into separate recovery databases first
and verify them before switching connections. For an in-place restore, stop
writers and explicitly select the correct target database; `pg_restore --clean
--if-exists` replaces database objects and is different from the record-only
workflow above. If source replacement succeeds and OLAP fails, the existing OLAP
transaction rolls back: usually rerunning the initial load is sufficient.

## Data characteristics and limits

The sample has WFO/WFH, late arrivals, early departures, missing checkout events,
extra punches, absence, individual rotating days off, Saturday operations, and
single/multi-day approved, rejected, and pending leave. IDs are globally unique,
and employee names/NIPs/emails are unmistakably fictional. Organization closures
are synthetic and **not an official national holiday calendar**. Distribution
rates are illustrative, not calibrated against production measurements.

The current business rules support one schedule per department/weekday and
same-day shifts. They do not model overnight shifts, employee transfers over
time, employment start/end dates, or automatic flexible-shift penalties. Those
scenarios need ETL changes before adding them to the fixture.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
# Optional: real PostgreSQL COPY, foreign-key, sequence, and rollback checks
RUN_POSTGRES_TESTS=1 .venv/bin/python -m unittest discover -s tests -v
```

The PostgreSQL test creates isolated schemas in OLAP and rolls them back without
committing. It requires permission to create schemas; existing records are not changed.
