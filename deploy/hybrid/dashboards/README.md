Current layout uses **one dashboard container** with daily KPI cards, a trend
with **3D / 7D / 1M / 3M / 6M / 1Y / Custom** controls, and the daily table below.
Daily and trend filters remain independent. Top management sees its department
summary and department rankings; employee daily records remain only in the
manager view. [Current layout and checks](../../../tests/unified_dashboard_20261030/README.md).
Earlier layout notes below are retained for context.

Current filters are separated into **Daily attendance** (one date for cards,
rankings and detail tables) and **Attendance over time** (a date range for the
line chart). Each section has an independent department-name search. Table
search remains local to the daily detail tables. See the
[filter update and evidence](../../../tests/daily_period_filters_20261030/README.md).
Earlier shared-date notes below describe the preceding layout.

> **Dashboard repair:** the website now selects preserved test runs explicitly,
> with separate overview/detail embeds and table-only search. The new 30–31 October
> simulation is paused after batch 1 (30 October morning check-ins).
> [Current workflow and evidence](../../../tests/dashboard_revision_20261030/README.md).
> The top-10 rankings show counts, denominators and percentages in tables;
> lateness assessment coverage has been removed. Earlier single-dataset notes
> below are historical context.

> Current Metabase/website dataset: 82,119 currently active source employees, 4,298 departments,
> simulated attendance on 2 November 2026; check-in-only checkpoint, zero checkouts.
> See [test evidence](../../../tests/checkin_20261102/README.md). The 30 October
> evidence below describes the previous preserved test dataset.
>
> The analytical dashboard includes a top-10 department chart by percentage of
> distinct active employees with valid approved leave in the selected period.
> A person who changes departments can be counted once in each department. The ranking is
> provisional, like the underlying test data. To restore the card after rebuilding
> the Metabase dashboards, run `python3 deploy/hybrid/dashboards/add_analytical_leave_ranking.py`.
> Prior bulk test records were removed. See [the source-to-dashboard rerun](../../../tests/source_to_dashboard_20261030/README.md)
> for the earlier cohort's counts, filters, full-department verification, and performance limits.
> The older baseline counts below are historical evidence.

# Attendance GUI comparison dashboards

Originally created 30 October 2026 for the authorized bulk test source
`mart_bkd_bulk_20261029`. Metabase now reads `mart_bkd_checkin_20261102`;
the separate Superset comparison remains on the previous dataset.

| Engine | Operational | Organization |
|---|---|---|
| Metabase | http://localhost:3101/dashboard/1 | http://localhost:3101/dashboard/2 |
| Superset | http://localhost:3102/superset/dashboard/attendance-operational-test/ | http://localhost:3102/superset/dashboard/attendance-organization-test/ |

Sign in with the existing local BI administrator accounts described in
[the environment guide](../README.md). These dashboards support authenticated GUI review and signed guest embedding
in the local Next.js website. No unauthenticated public shares are enabled.

## Default scope

Metabase and the website default to 2 November 2026 using `DASHBOARD_TEST_DATE`.
Operational dashboards default to source department ID 30114; organization
dashboards include all departments. Metabase uses inclusive start/end dates.
The Superset comparison retains its earlier dataset and period settings.

Each dashboard contains six sum cards, a check-in/check-out daily trend, a role
appropriate table, a coverage/publication panel, and a provisional test-data
notice. The organization table includes weighted coverage and required-fulfillment
percentages. Summary charts read the approved department serving view; the
operational table reads active daily facts. Department filters use source IDs.
Names are absent in this fixture, so department labels fall back to source IDs.

Period counts are employee-days. SUM is not coalesced to zero: an unloaded date
returns null cards, empty trend/detail tables, and NO DATA in the status panel.
Coverage and completeness must be read together; available data does not prove
that every selected date is published. Only one date is loaded, so trend and
previous-period analysis are not established by this fixture.

GUI filters are preview controls, not authorization. The Next.js prototype now assigns roles server-side and locks the manager embed
to department 30114. Direct BI administrator GUI filters remain ordinary filters.
Production identity integration and a broader isolation audit remain later work.

## Reproduce

From the repository root, with Python requests installed and the BI engines running:

```bash
python3 deploy/hybrid/dashboards/create.py
```

The scripts update only their named collection, datasets, questions/charts, and
dashboards. They preserve existing IDs when rerun. They deliberately restore the
baseline definitions and layouts, so export any manual GUI edits you want to keep
before rerunning. Manifests record the saved object IDs and GUI URLs. Both scripts
check the selected database before creating dashboard content.

Superset's virtual datasets introduce a timestamp representation of the reporting
date to keep time-series bucket rendering aligned with the calendar date. This
changes BI metadata only. Metric formulas remain sums of the serving measures.

## Validation

Browser checks confirmed both operational and organization dashboards render all
nine query-backed visuals. Organization cards matched:

| Active | Check-in | Check-out | Missing check-in | Missing check-out | Leave |
|---:|---:|---:|---:|---:|---:|
| 2400 | 1000 | 1000 | 1000 | 600 | 1200 |

The default department 30114 matched `[4, 1, 1, 3, 2, 1]`. Changing to department
30187 matched `[4, 2, 2, 1, 1, 2]` in both engines, and both employee tables returned
its same four employee-days. Unloaded-date checks (29 October) passed for all nine
operational visuals in each engine; Superset's empty-date check replayed the
actual browser-generated chart requests with the changed time range.

The Metabase employee query returns at most 1,000 ordered rows; its visual table
pagination is not database-side pagination. Superset's employee query was checked
to use `row_limit=25`, `row_offset=0`, and a separate row-count query. Its page-size
control can display 0 when all four filtered rows fit on one page; that display
is not evidence of an unlimited SQL query. Larger-volume navigation is still a
benchmark task. Organization summary queries are capped at 1,000 groups and the
fixture contains 757. No concurrency or production capacity claim is made.

[Reference SQL](reference.sql) reproduces the KPI totals without BI rendering.

## User selection and ID display — 30 October 2026

The user selected Metabase for its readability. Dimension name loading is deferred.
Employee and department ID columns display whole IDs without grouping separators;
the saved question settings and recreation script both preserve this formatting.
This selection reflects GUI preference, not completion of performance or embedded
isolation validation.
