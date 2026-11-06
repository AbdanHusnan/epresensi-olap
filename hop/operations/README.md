# November 2026 dashboard population

Actual targets: `epresensi-staging-postgres/staging_bkd` (`raw`, `curated`,
`etl_control`) and `epresensi-mart-postgres/mart_bkd` (`mart_kehadiran`, `serving`).
The source `epresensi-olap-postgres/dbabsen_restore` is read-only.

```bash
python3 hop/operations/fill_month.py configure
python3 hop/operations/fill_month.py masters
python3 hop/operations/fill_month.py prepare
python3 hop/operations/fill_month.py load
python3 deploy/hybrid/provision_mart.py
python3 deploy/hybrid/dashboards/configure_test_runs.py --actual-month
docker compose --env-file .env.hybrid -f docker-compose.hybrid.yml up -d --build --no-deps web
```

`configure` preserves other environment settings and installs the actual staging
and mart Hop connections and existing pipelines. Credentials stay in the Hop
volume. Reload `presensi-staging-local` in Hop Web if it is already open.

`masters` upserts the seven complete current master tables without truncating raw
history. `prepare` freezes the active employee snapshot and chooses the earliest
valid active, non-overnight department schedule separately for each weekday.
It does not assign invented schedules when the department has none.

`load` creates one committed raw manifest per calendar day, uses server-side bulk
COPY for event insertion, and runs that named batch through Hop. It bootstraps
mart capture once if necessary, then drains a generated monthly Hop workflow in
one JVM. Every batch retains the existing separate apply and confirm/ack
pipelines and commit boundaries. It fills display names from the master snapshot.
Both staging and mart are verified against the recorded scenarios, daily measures,
complete source/fact row fingerprints, and serving aggregates.
The audit and reconciliation report is `runtime/month_202611/verification.json`;
Hop execution details are in `runtime/month_202611/hop.log`. Full master count/hash
verification is saved to `runtime/month_202611/master_verification.json`.

After loading and rebuilding the website, verify both roles and daily/monthly embeds:

```bash
python3 hop/operations/fill_month.py verify
python3 hop/operations/verify_month_dashboard.py
```

For employees with a usable schedule, a stable hash of employee/date/seed selects
58% on time, 20% late, 5% full-day izin, 4% morning partial leave, 4% afternoon
partial leave, 3% missing checkout, 3% missing check-in and 3% absent. Actual
proportions vary by day. Leave uses real category IDs; transaction `tipe_ijin`
1/2/3 determines both-side/check-in/check-out exemptions. No-schedule employees
still have a daily population row and remain unassessed, with a review reason.
Weekends use actual weekend schedules where available.

This is simulated attendance, including future dates, with current master data
extrapolated explicitly for November 1–30. It is not observed attendance or proof
of historical/future employment. Population uses `EXTRACTION_SNAPSHOT`; facts
remain provisional. The website visibly labels the simulation.

Every new transaction carries `pipeline_run_id=SIMULATED_202611`. IDs are reserved
above existing raw IDs under locks. Existing raw history and source transactions
are preserved. Audit tables and the seed function use the
`etl_control.simulation_*_202611` names. Repeating `load` resumes the same run;
it does not regenerate committed days or reset databases. `prepare` does not
replace the frozen population. Use a separately reviewed run for another month
or seed; do not delete ledgers to force a rerun.

The website registry contains only November's dashboards bound to `mart_bkd`.
Old BI objects are retained but are no longer selectable in this website.
Daily summaries/details open November 1; the trend initially covers all 30 days.
Change the daily date to inspect another day. Existing manager department scope
remains enforced.

Dedicated staging and mart PostgreSQL `max_wal_size` was raised from the default
1 GB to 4 GB using `ALTER SYSTEM` and reload to reduce repeated bulk-load
checkpoints. No database restart or durability setting change is required.

Bulk COPY uses `/tmp/simulated_202611_events.csv` inside the staging container
under the run advisory lock. The PostgreSQL owner must be allowed server-side
COPY. This transient generated-event file contains no credentials and can be
removed after `load` completes. It is not a checkpoint; the database audit ledger
is the checkpoint.

The dedicated staging PostgreSQL `shared_buffers` setting is 1 GB (previously
128 MB). A brief staging restart applied it during the initial run; interrupted
transactions rolled back and resumed from the committed day ledger.

The curated consumer uses function-local `work_mem=64MB` and `jit=off` to
avoid temporary-sort spills. These settings do not change ETL business rules.
The read-only Hop pipeline `pipelines/operations/verify_actual_connections.hpl`
checks that source, staging and mart resolve to the intended actual databases.

The mart consumer similarly uses function-local `work_mem=128MB` and `jit=off`
for its wide per-day temporary tables. `prepare` applies these scoped settings.
