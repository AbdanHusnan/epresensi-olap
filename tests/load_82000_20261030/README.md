# Load test: 82,000 employees, 30 October 2026

> Superseded: this bulk test dataset and its tagged source fixtures were removed
> on 30 October 2026 at the user’s request. The current dataset and verification
> are documented in [the source-to-dashboard rerun](../source_to_dashboard_20261030/README.md).
> Historical scripts and reports below are audit evidence, not current database state.

**Data correctness passed. The current configuration failed the ten-user dashboard test.**
The user confirmed expansion of `mart_bkd_bulk_20261029`, then explicitly limited
this test to one date and 82,000 records. No historical dates were added.

## Scope and final state

- Curated source: `staging_bkd_mart_bulk_20261029` in `epresensi-staging-postgres`.
- Fact/serving target: `mart_bkd_bulk_20261029` in `epresensi-mart-postgres`.
- Metabase source ID 1, dashboards 1/2, and the existing website use this target.
- Final population: **82,000 distinct employees / 82,000 facts, 757 departments,
  one date (28 October 2026)**. All results remain provisional.
- The original 2,400 records were retained. Added 79,600 synthetic employee IDs
  `1000000001` through `1000079600`, cycling through the original 2,400 curated
  records in employee-ID order. Population and attendance assignments match.
- This retains the 12 existing attendance/leave/two-shift scenarios and department
  distribution. It is a scenario-heavy capacity fixture, not a representative
  estimate of production leave/absence rates. Raw-to-curated processing was not tested.

The live configuration and source were checked before loading. The old Superset-only
`dashboard.md` blueprint is stale relative to the current Metabase website.
Pre-load custom-format backups of both test databases are in the gitignored
`backups/load_82000_20261030/` directory. No database was dropped or reset.
Protected active `mart_bkd`, active `staging_bkd`, and the original bulk reference
were unchanged. All five hybrid services passed final health checks.

## Loading time

Actual existing Hop workflow, immutable outbox, atomic target apply, fresh-connection
commit confirmation, and staging acknowledgement were used without pipeline changes.
There was no direct fact insert or re-bootstrap.

| Final employees | New rows | Fixture + capture | Hop wall time | Internal workflow | Rows / Hop second |
|---:|---:|---:|---:|---:|---:|
| 10,000 | 7,600 | 2.782 s | 27.755 s | 8.906 s | 274 |
| 40,000 | 30,000 | 4.449 s | 34.569 s | 18.057 s | 868 |
| 82,000 | 42,000 | 7.598 s | 53.530 s | 30.497 s | 785 |

The three Hop calls total **115.854 seconds**, plus **14.829 seconds** for fixture
creation/capture: **130.683 seconds of measured loading work** for 79,600 new rows.
This excludes verification, pauses, backups, and the original 2,400-row load.
Hop wall time includes JVM startup. These are single observations per batch size,
not a repeated throughput distribution. A single 82,000-row delivery was not tested.

## Correctness

All three stages compared every fact against curated data, including shared fields,
timestamps, flags, department assignments, and all 12 measures. The verifier derives
measure expectations independently from Boolean business flags.

Final verification also checked ordered fingerprints of 34 shared source/fact fields,
all 757 source-grouped department totals, four percentage formulas per department,
row/review/nonfinal counts, dimension business identities and effective intervals,
and provisional publication state. Original source records remained unchanged.

There are **four APPLIED batches / four committed receipts**, cursor sequence 4,
and **zero pending deliveries**. An empty-queue Hop rerun preserved fact/aggregate
values, PostgreSQL row versions, and receipt count.

| KPI | Organization | Manager department 30114 |
|---|---:|---:|
| Active employees | 82,000 | 136 |
| Check-in | 34,179 | 34 |
| Check-out | 34,173 | 34 |
| Missing check-in | 34,159 | 102 |
| Missing check-out | 20,496 | 68 |
| Leave | 41,002 | 34 |

All **54 website checks passed**, including role access, server-assigned department
scope, rejected parameter overrides, CSV scope, tampered/expired tokens, and logout.
The original test scripts with fixed 2,400-row expectations are historical evidence;
use this directory's adapted checks for the expanded dataset.

## Serving and dashboards

SQL measurements use EXPLAIN ANALYZE/BUFFERS, ten executions per query, with first
execution separated from nine repeated executions. No cache flush was performed.
These use the administrative verification connection; HTTP tests exercise the
actual restricted Metabase reader. Repeated one-day SQL p95:

| Query | Execution p95 |
|---|---:|
| Institution | 2.308 ms |
| Department comparison | 3.816 ms |
| Daily trend | 5.330 ms |
| Manager employee detail | 82.781 ms |
| Unscoped first 1,000 employee rows | 68.860 ms |

The `month_*` entries in `sql_benchmark.json` only widen the requested date filter;
there is still one available date. They are **not historical-scale benchmarks**.
Manager detail scans all 82,000 facts and filters out 81,864 rows because the existing
indexes use surrogate department keys while the dashboard filters source department
IDs. A source-department/date/employee index is a candidate for a separately measured
optimization; no index or production configuration was changed here.

HTTP virtual users log in, obtain an application-issued scoped token, retrieve
metadata, and request all nine charts with three requests in flight per user.
Four synchronized waves per stage, mixed director/manager roles, no think time.
Visit times include login, token/metadata, chart work, and logout. This is a bounded
burst test, not a sustained production SLA or concurrent browser rendering test.

| Run | Users | Visits | Visit p50 | Visit p95 | Failed visits | Failed charts |
|---|---:|---:|---:|---:|---:|---:|
| Initial | 1 | 4 | 2.082 s | 2.263 s | 0 | 0 / 36 |
| Initial | 5 | 20 | 10.154 s | 15.047 s | 0 | 0 / 180 |
| Repeat | 5 | 20 | 2.099 s | 2.431 s | 0 | 0 / 180 |
| Later | 10 | 40 | 3.840 s | 6.255 s | 9 | 17 / 360 |

The initial five-user run crossed the stop threshold; escalation was paused, then
resumed after a successful five-user repeat. Both observations are retained.
Latency variation is unresolved; warming/resource contention may contribute, but
this test does not isolate their effects. Cache indicators were absent from query
responses, so no hit-rate or cold-cache claim is made.

**Ten-user failure cause:** PostgreSQL logged `too many connections for role
"hybrid_metabase_reader"`. The role permits ten connections; this test allows up to
thirty concurrent chart requests. Seventeen chart requests failed with HTTP 400 /
query status `failed`, affecting nine visits. Some visits also report `kpi_mismatch`
because a failed scalar returned no value; this is an availability failure, not
observed corruption of successfully returned values. No automatic retry hid errors.
The five-user repeat also recorded CPU throttling in 89/95 scheduling periods under
Metabase's two-CPU cap. Do not claim ten-user readiness from the SQL timings alone.

Next performance work should align Metabase pool/concurrency with the reader's
connection budget, then repeat the same burst plus a longer sustained test. Any
increase to the reader connection limit should be budgeted against PostgreSQL and
other BI clients; this test did not change those limits.

Real Chromium sessions after the burst confirmed recovery for both roles on desktop
and 390-pixel mobile. All nine chart responses completed in **3.77–4.91 seconds**;
DOM content checks completed in **4.70–5.97 seconds**, including polling overhead.
KPI/status text rendered, no page errors occurred, and the outer website had no
horizontal overflow. Viewport screenshots are retained. Four browser observations
are not a percentile benchmark. Earlier browser observations were 4.6–6.4 seconds
for chart completion while other verification activity was running.

## Resources and evidence

Sampled peaks (monitoring started during the 40,000 stage): Hop ~1.85 GiB of 3 GiB;
Metabase ~1.49 GiB of 2 GiB; mart PostgreSQL 684 MiB; staging PostgreSQL ~1.20 GiB.
No Hop/Metabase OOM or restart was observed. Metabase reached approximately its
200% CPU ceiling. The host runs other applications and started with swap full,
although approximately 35 GiB of memory was available. These are shared-host results.

Observed database sizes after expansion: mart 52,460,567 bytes; staging 137,034,775
bytes. Staging outbox items account for 98,639,872 bytes; target receipts 5,840,896
bytes. This test does not establish long-term audit-retention storage requirements.

- [Machine-readable summary](summary.json), [final reconciliation](final_reconciliation.json)
- [Baseline inventory/timings](preflight.json), [SQL plans](sql_benchmark.json)
- [Initial HTTP run](daily_82000_http.json), [five-user repeat](five_user_repeat_http.json), [ten-user failure](ten_user_warm_http.json)
- [Sanitized error evidence](error_diagnosis.json), [CPU delta](metabase_cpu_delta.json)
- [Browser evidence](browser.json), [website authorization checks](website_security_results.json)
- [Empty-queue integrity](empty_queue_integrity.json), [resource samples](resources.jsonl)

The initial HTTP diagnostic incorrectly treated Metabase HTTP 202/completed results
as errors. `daily_initial_http_status_diagnostic.json` preserves that harness issue;
all reported runs accept any 2xx status and require query status `completed`.

To repeat read-only business-data verification and bounded measurements:

```bash
python3 tests/load_82000_20261030/reconcile.py
python3 tests/load_82000_20261030/website_verify.py
python3 tests/load_82000_20261030/sql_benchmark.py
python3 tests/load_82000_20261030/benchmark.py --users 1,5 --label repeat
node tests/load_82000_20261030/browser.cjs
```

These overwrite their local output files and create ordinary application sessions.
`load.py init` and `load.py ramp` mutate data and must not be rerun as inspection.
They reject the already-initialized/fully-expanded state. The Chromium harness
currently uses the existing `/tmp/olap-dashboard-browser/node_modules/playwright`
installation. No historical-load runner remains in the final harness.
