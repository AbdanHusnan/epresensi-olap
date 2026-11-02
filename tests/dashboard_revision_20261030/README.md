# Dashboard repair and gradual October simulation

The 2 November test repointed the shared Metabase connection from
`mart_bkd_bulk_20261029` to `mart_bkd_checkin_20261102`. It did not delete the
original 30 October facts. A date filter cannot query a different database;
each isolated dataset contained just one reporting date, so neither established
a two-day trend.

`deploy/hybrid/dashboards/configure_test_runs.py` now creates a permanent
connection binding for each test and provisions separate overview and detail
embeds. The website's test-run selector selects an allowlisted dashboard pair.
Original October and November results remain selectable. The bootstrap script
refuses to repoint its existing connection to a different database.

Search is below the overview, immediately above the detail tables. It refreshes
only the tables embed. Overview SQL and mappings omit search; the token signer
ignores a search submitted for the overview. Manager department restrictions
are signed for both sections and each test run. Shared date controls apply to
both sections, with dates validated on the server.

The two top-10 rankings use tables with rank, full department name, source ID,
affected employee count, denominator and percentage. This makes a 1/1 (100%)
result distinguishable from a large department. The percentage remains the
primary ranking, with affected count and denominator breaking ties; no small
departments are silently excluded. These period rankings count distinct people,
while the six overview totals count employee-days. The unrequested lateness
assessment coverage card is removed; underlying lateness eligibility rules
remain unchanged.

## Authorized gradual simulation

Use a new isolated pair, never reset or overwrite existing test databases:

- `staging_bkd_gradual_20261030`
- `mart_bkd_gradual_20261030`

Four batches represent ordinary daily ingestion:

1. 30 October morning check-ins — loaded now, pause for user review.
2. 30 October afternoon checkouts — pending review/request.
3. 31 October morning check-ins — pending; append the second date.
4. 31 October afternoon checkouts — pending.

All currently active source employees are retained in the simulated population.
Usable direct active schedules determine check-in fixtures; no personal or
shared roster is guessed. Current source master status is an extraction snapshot,
not a historical assertion. Source business tables are read-only. Fixtures go
only into isolated staging raw tables and then through actual curated/outbox/
mart Hop processing. Batch 1 has zero checkout events. The default period is
30–31 October; the unloaded 31 October is not filled with zeros.

The harness currently enables only setup, batch1 and verify. It refuses to reset
existing databases or repeat fixture insertion. Later phases must be implemented
and executed only when the user requests the next batch.

```sh
python3 tests/dashboard_revision_20261030/run_batches.py setup
python3 tests/dashboard_revision_20261030/run_batches.py batch1
python3 deploy/hybrid/dashboards/configure_test_runs.py
```

Setup and batch1 have already run; do not repeat them. Read-only verification:

```sh
python3 tests/dashboard_revision_20261030/run_batches.py verify
python3 tests/dashboard_revision_20261030/verify_web.py
node tests/dashboard_revision_20261030/browser.cjs
```

Evidence is stored beside this document: `batch1_verification.json`,
`web_verification.json`, `browser_verification.json`, and screenshots.
