# Source → dashboard rerun — 30 October 2026

**Source-to-dashboard correctness passed with 72,259 real source employees.**
The ten-user concurrency test still fails under the existing database reader limit.
This replaces the earlier 82,000-employee synthetic-ID load test.

The user explicitly requested actual employees and shifts, up to 82,000, deletion
of the previous test records, and creation of tagged test attendance/leave
transactions in `dbabsen_restore`.

## What was loaded

| Item | Count |
|---|---:|
| Actual source employees | 72,259 |
| Departments | 3,829 |
| Actual source schedules / shifts | 5,195 / 5,195 |
| Source user identities | 72,259 |
| Tagged source attendance transactions | 135,146 |
| Tagged source leave transactions | 5,054 |
| Final employee-day facts | 72,259 |
| Serving department-day aggregates | 3,829 |

Date: **30 October 2026**, required by the pipeline's current-day population snapshot
contract. The source has 82,119 active employees. The selected 72,259 have source
user accounts and active department schedules for Friday with checkout later than
check-in. The 82,000 cap was not binding. Overnight schedules and employees without
these prerequisites are outside this cohort. These are real department schedules,
not proof of a historical personal roster assignment.

No employees, user accounts, shifts, or schedules were created or modified.
Attendance and leave transactions are **simulated test data**, explicitly authorized,
with marker `SOURCE_DASHBOARD_20261030` and exact ID manifests in source schema
`test_source_dashboard_20261030`. Their event times come from actual source schedules.
The test mix is approximately 88% both events, 3% check-in only, 1% checkout only,
1% absent, 3% full leave, 2% exempt check-in with checkout, and 2% exempt checkout
with check-in. Some employees with a second real schedule have two event pairs.
The source fixture creation and manifest writes commit atomically.

## Actual path exercised

`dbabsen_restore` → **Hop TableInput/TableOutput** →
`staging_bkd_mart_bulk_20261029.raw` → **standard curated Hop pipeline** →
curated/outbox → **standard mart Hop workflow** →
`mart_bkd_bulk_20261029` → **Metabase dashboards 1/2** → **Next.js website**.

All seven master datasets and both transaction datasets were freshly extracted
from the source through Hop. This did not copy the old backfilled raw masters.
Every loaded business-field fingerprint matched the source. `m_user` extraction
includes only ID and employee ID; credentials and unrelated account fields were
not copied. Explicit event/leave manifests were published after raw verification.
This exercises the existing loader and consumer contracts, not an automatic
production CDC/scheduler implementation. Snapshot completeness applies to the test
cohort, and publication remains **PROVISIONAL**, not organization-wide complete.

## Previous data removed

- Deleted exactly 2,400 old tagged source attendance events and 1,600 tagged leave
  records, constrained by both their manifests and `BULK_CURATED_20261028` marker.
- Dropped the old bulk raw/curated database `staging_bkd_bulk_20261028`.
- Recreated the paired staging and mart test databases, removing the previous
  82,000 facts, generated employee IDs, aggregates, outbox, receipts, and test schemas.
- Final checks found zero old source manifest IDs, zero synthetic employee IDs
  at or above 1,000,000,000 in the mart, and only the new test date.

Pre-removal backups are retained under `backups/source_to_dashboard_20261030/`.
Old reports/scripts remain as superseded audit evidence. Unrelated historical test
sets were not deleted. Active `staging_bkd` and `mart_bkd` remained unchanged;
source employee/shift/schedule fingerprints also remained unchanged.

## Correctness and results

An independent oracle aggregates the actual tagged transactions directly in the
source database, then compares every selected employee's date, department, event
counts/timestamps, attendance/leave flags, and all 12 measures against curated data.
A separate cohort-mix check confirms the generated transactions match the intended
scenarios. Ordered fingerprints compare 34 shared curated/fact fields. All 3,829
source-derived department aggregates and percentage formulas match serving data.
Dimension business IDs/effective intervals and population assignment also pass.

One mart batch and receipt are APPLIED, with zero pending deliveries. A second
curated manifest containing the same source IDs produced zero event, leave,
population, summary, or daily changes. The empty mart rerun and curated replay
preserved daily/fact/aggregate row versions. There is still only one mart receipt.

| KPI | Organization | Manager department 30114 |
|---|---:|---:|
| Active employees | 72,259 | 85 |
| Check-in | 67,205 | 78 |
| Check-out | 65,761 | 73 |
| Missing check-in | 1,444 | 4 |
| Missing check-out | 2,888 | 9 |
| Leave | 5,054 | 4 |

All **54 website checks passed**, including role authorization, locked department
scope, CSV scope, forged/expired tokens, overrides, and logout. Browser checks
passed for both roles on desktop and 390-pixel mobile, with matching KPI/status text,
no page errors, and no outer-page horizontal overflow. The production website
build passed TypeScript and Next.js compilation. All five hybrid services were
healthy after testing.

## Timing and responsiveness

| Measured component | Wall time, including Hop startup |
|---|---:|
| Nine source → raw phases, summed | 184.716 s |
| Curated processing | 24.733 s |
| Mart delivery of 72,259 rows | 51.910 s |
| Sum of measured ETL components | 261.359 s |

This is **not uninterrupted end-to-end elapsed time**: it excludes verification,
pauses, manifest/bootstrap overhead, setup, and fixture creation. One initial
user-identity phase completed but lost its timing capture when its runner was
stopped. Its 17.020-second measurement was repeated through equivalent Hop I/O
into a fresh scratch table, verified against the source, then the scratch table
was deleted. The component sum includes this clearly identified remeasurement.

Successful source fixture creation took 172.460 seconds. The first attempt hit a
180-second statement timeout and rolled back completely; sequence gaps remain.
The retry used a longer fixture-only timeout. A harness error initially parsed the
text manifest ID as JSON after enqueue committed; the READY manifest was resumed
without duplicate enqueue. These setup/orchestration issues are retained in the
report rather than counted as successful ETL throughput.

Repeated SQL p95 (nine repeated executions after a separate first execution):
institution 9.625 ms, department comparison 11.005 ms, trend 6.057 ms,
manager detail 65.271 ms, and unscoped first 1,000 employee rows 44.248 ms.
These are local administrative EXPLAIN ANALYZE/BUFFERS measurements on one date,
not cold-cache or historical-scale results.

Each virtual user signs in, gets a scoped token, and fetches all nine charts with
three concurrent requests. Four waves per level; mixed roles, no think time.

| Concurrent users | Visits | Visit p95 | Failed visits | Failed charts |
|---:|---:|---:|---:|---:|
| 1 | 4 | 2.786 s | 0 | 0 / 36 |
| 5 | 20 | 4.322 s | 0 | 0 / 180 |
| 10 | 40 | 10.662 s | 8 | 12 / 360 |

PostgreSQL and Metabase logs confirm `too many connections for role
"hybrid_metabase_reader"`. The role still permits ten connections; the ten-user
burst can have thirty chart requests in flight. No connection-limit tuning or
retry hides the failure. Failed scalar responses can also produce a harness KPI
mismatch because no value was returned; successful values matched the oracle.
Aligning the connection pool/concurrency budget and retesting remains future work.

Real browser nine-chart completion ranged **4.55–6.21 seconds**; DOM content checks
completed in **5.54–8.00 seconds**, including polling/scroll overhead. These four
observations are not percentile estimates. All measurements are on a shared local
host; they do not establish a sustained or WAN-facing production SLA.

## Dashboard corrections made

The broader source cohort exposed truncation: the old SQL limited department rows
to 1,000, and Metabase then capped native results at 2,000. Department SQL and the
test instance's `unaggregated-query-row-limit` are now 5,000. The corrected check
confirms **all 3,829 departments** return. Employee detail retains its 1,000-row
limit and authorization checks. The companion Superset department-table limit was
aligned to 5,000; full chart correctness/performance measurements here cover Metabase.
Website banners, embed defaults, and BI dashboard date filters now use 30 October.

## Evidence and rerunning verification

- [Machine-readable summary](summary.json), [source inventory](source_inventory.json)
- [Cleanup](cleanup.json), [final cleanup checks](final_cleanup_integrity.json)
- [Full reconciliation](verification.json), [unchanged replay](replay.json)
- Per-table `raw_*_verification.json`, Hop `.hpl/.hwf` files, logs, and timing JSON
- [HTTP runs](source_daily_http.json), [connection-limit diagnosis](error_diagnosis.json)
- [Browser evidence](browser.json), [website checks](website_security_results.json)
- [SQL plans](sql_benchmark.json), [resource samples](resources.jsonl)

```bash
python3 tests/source_to_dashboard_20261030/verify.py
python3 tests/source_to_dashboard_20261030/website_verify.py
python3 tests/source_to_dashboard_20261030/sql_benchmark.py
python3 tests/source_to_dashboard_20261030/benchmark.py --users 1,5 --label repeat
node tests/source_to_dashboard_20261030/browser.cjs
```

These commands read business data and overwrite local evidence files; HTTP checks
create ordinary application sessions. The browser harness uses the existing
`/tmp/olap-dashboard-browser/node_modules/playwright` installation. Mutating phases
in `run.py` and `replay.py` are not inspection commands and should not be rerun
blindly. The new source fixtures and resulting dashboard dataset remain available
for inspection and later manifest-scoped cleanup.
