# Attendance Dashboard Specification

Date: 29 October 2026  
Scope: analytical dashboard for top management and operational dashboard for middle management  
Business contract: `ATTENDANCE_DAILY_V1`

The attendance dashboards share the same measures but serve different decisions. Top management needs institution-wide trends and department comparisons. Middle management needs the selected department’s daily attendance condition and a searchable employee list when follow-up is necessary.

The agreed scope is supported by the existing mart and serving schema without new fact columns or aggregation tables. Derived calculations and application queries are still required. Schema compatibility does not establish production data readiness or dashboard performance. This specification summarizes the agreed direction; it does not claim that the dashboards have been implemented.

## Contents

1. Audiences and purpose
2. Data model and dashboard sources
3. Metrics and KPI definitions
4. Analytical dashboard pages
5. Operational dashboard pages
6. Employee list conditions
7. Interpretation and data quality rules
8. Implementation boundaries and readiness
9. Acceptance criteria
10. References

## 1. Audiences and purpose

| Aspect | Analytical dashboard | Operational dashboard |
|---|---|---|
| Audience | Top management | Middle management |
| Main question | How are attendance patterns changing, and which departments need attention? | What is the department’s attendance condition today, and which records need follow-up? |
| Default time scope | Current month, with daily trends | Today, with a recent 7 or 14 day trend |
| Main level | Institution and department | Department, then employee list |
| Decisions supported | Prioritize attention and investigate persistent patterns | Follow up missing records and review exceptions |
| Navigation | Institution overview → department analysis | Department overview → employee list by condition |

Neither dashboard evaluates individual productivity or assigns disciplinary scores. Attendance recording is not a complete measure of employee performance. A missing event indicates a recording condition under this contract, not proof of misconduct.

The operational dashboard must remain usable for departments with hundreds or thousands of employees. Its main page contains summaries; employee lists are secondary, filtered and paginated. No individual ranking or employee performance page is included.

## 2. Data model and dashboard sources

Database: `mart_bkd`.

| Object | Grain or role | Dashboard use |
|---|---|---|
| `mart_kehadiran.fact_kehadiran_daily` | One employee × reporting date, across all shifts | Employee condition lists and record details |
| `mart_kehadiran.dim_pegawai` | Effective employee dimension version | Employee name and source ID |
| `mart_kehadiran.dim_departemen` | Effective department dimension version | Historical department association and labels |
| `mart_kehadiran.dim_calendar` | One date | Date coverage checks |
| `serving.agg_kehadiran_departemen_harian` | One date × department surrogate key | Stored additive measures |
| `serving.v_kehadiran_departemen_harian` | Department daily measures, rates and status | Department summaries, comparisons and trends |
| `serving.v_kehadiran_instansi_harian` | Institution daily measures, rates and status | Institution overview and trends |
| `serving.v_departemen_filter` | One option per source department ID, including UNKNOWN | Department selector |
| `serving.attendance_date_state` | Date completeness and closure | Distinguish incomplete or missing data from ready data |

Read summary data through the serving views, which incorporate date-state checks. Use the fact only when employee-level information is needed. Join employee names through the fact’s `pegawai_key` to avoid multiplying rows or substituting a current dimension version for the historical one.

There is no physical monthly aggregation. Monthly summaries can sum daily measures and calculate weighted rates. Performance must be measured against actual data volume before adding caches or new aggregations.

## 3. Metrics and KPI definitions

A metric describes a count or proportion. The primary KPIs here are required check-in and check-out fulfillment. Targets and red/amber/green thresholds have not been agreed and must not be invented from the database.

### 3.1 Six attendance counts

| Display label | Database measure | Meaning | Dashboard use |
|---|---|---|---|
| Pegawai Aktif | `active_employee_days` | Employee is active for the reporting date | Both |
| Absen Masuk | `checkin_days` | Active employee has at least one check-in | Both |
| Absen Pulang | `checkout_days` | Active employee has at least one check-out | Both |
| Tidak Absen Masuk | `no_checkin_days` | Active employee has no check-in and is not exempt from check-in | Both |
| Tidak Absen Pulang | `no_checkout_days` | Active employee has no check-out and is not exempt from check-out | Both |
| Pegawai Izin | `leave_days` | Active employee has valid leave | Both |

On a single date, these are employee counts. Across multiple dates, their sums are employee-days. Analytical period cards must use employee-day labels. A unique employee count over a period requires a separate `COUNT(DISTINCT pegawai_id_sumber)` fact query filtered to active records; it is not the sum of daily population.

For today, use **Belum Absen Masuk** and **Belum Absen Pulang**. Past dates that remain provisional must also visibly retain that status.

### 3.2 Fulfillment and supporting rates

In all formulas below, `SUM` covers the selected dates and departments. Multiply ratios by 100 and use `NULLIF(denominator, 0)`; display a null result as `—`.

| Metric or KPI | Formula | Interpretation | Main use |
|---|---|---|---|
| Required check-in fulfillment | `100 × SUM(required_checkin_present_days) / SUM(required_checkin_days)` | Share of required check-ins fulfilled after exemptions | Primary KPI, both |
| Required check-out fulfillment | `100 × SUM(required_checkout_present_days) / SUM(required_checkout_days)` | Share of required check-outs fulfilled after exemptions | Primary KPI, both |
| Missing required check-in rate | `100 × SUM(no_checkin_days) / SUM(required_checkin_days)` | Unfulfilled share of required check-ins | Analytical comparison |
| Missing required check-out rate | `100 × SUM(no_checkout_days) / SUM(required_checkout_days)` | Unfulfilled share of required check-outs | Analytical comparison |
| Check-in coverage | `100 × SUM(checkin_days) / SUM(active_employee_days)` | Share of active employee-days with check-in evidence | Supporting metric |
| Check-out coverage | `100 × SUM(checkout_days) / SUM(active_employee_days)` | Share of active employee-days with check-out evidence | Supporting metric |
| Leave proportion | `100 × SUM(leave_days) / SUM(active_employee_days)` | Share of active employee-days with valid leave | Analytical context |

The daily views already expose `required_checkin_rate`, `required_checkout_rate`, `checkin_rate` and `checkout_rate`. For a period or regrouped departments, recalculate from summed measures rather than averaging these rate columns.

Required denominators exclude the corresponding leave exemptions. An employee can record an event while exempt: that event contributes to coverage but not to fulfillment of a requirement they did not have. “Required” is the dashboard obligation after leave rules, not a verified work roster.

### 3.3 Comparisons and contextual measures

| Insight | Calculation or source | Interpretation |
|---|---|---|
| Previous-period KPI change | Current weighted rate minus previous weighted rate | Percentage-point change, not percentage growth |
| Department contribution to missing check-in | Department `SUM(no_checkin_days)` / institution `SUM(no_checkin_days)` × 100 | Department share of institution missing check-ins |
| Department contribution to missing check-out | Corresponding check-out calculation | Department share of institution missing check-outs |
| Exempt check-in or check-out | `SUM(excused_checkin_days)` or `SUM(excused_checkout_days)` | Context for the required denominator |
| Records needing review | `SUM(review_rows)` | Review workload across all fact rows, including audit records |
| Provisional status | Serving view `is_provisional` | Results may change or lack validated completeness/closure |
| Data completeness | Serving view `is_data_complete` | Population and curated delivery completeness |

Show department missing-event counts alongside rates: counts indicate follow-up workload, while rates account for population differences. These describe conditions, not their causes.

For period comparisons, use comparable date coverage. A proposed default is month-to-date versus the same elapsed portion of the previous month, with actual dates shown and differing available coverage disclosed. This comparison convention remains a UI choice, not a database rule.

## 4. Analytical dashboard pages

### 4.1 Institution Overview

Purpose: understand institution-wide attendance patterns and identify departments requiring attention.

| Page section | Contents |
|---|---|
| Filters | Reporting period; institution scope |
| Data status | Coverage, provisional status, oldest and latest partition refresh times |
| Summary | Six attendance totals, labeled employee-days for a multi-day selection |
| Primary KPIs | Required check-in and check-out fulfillment, with numerator and denominator |
| Period comparison | Fulfillment change in percentage points and explicit comparison dates |
| Daily trend | Check-in and check-out fulfillment over the selected period |
| Department comparison | Population, missing counts, missing rates, fulfillment and quality status |
| Context | Leave proportion and department contribution to missing events |

Clicking a department opens Department Analysis with the reporting period preserved. Institution totals include UNKNOWN departments; there is no extra ALL row to add.

### 4.2 Department Analysis

Purpose: inspect a department’s aggregate patterns without evaluating individual employee performance.

| Page section | Contents |
|---|---|
| Navigation | Back to Institution Overview, preserving filters |
| Filters | Department and reporting period |
| Summary | Six period totals and primary fulfillment KPIs |
| Trends | Daily fulfillment and missing-event counts |
| Comparison | Previous-period changes with comparable coverage |
| Context | Leave proportion and exemption counts |
| Data status | Completeness, provisional status and refresh information |

This page remains at department level. Employee lists are part of the operational workflow and are subject to application authorization.

## 5. Operational dashboard pages

### 5.1 Department Attendance Overview

Purpose: provide a simple daily overview before opening any employee list.

| Page section | Contents |
|---|---|
| Filters | Reporting date, default today in Asia/Jakarta; authorized department |
| Data status | Provisional/final status, completeness and last refresh |
| Clickable attendance cards | Active, checked in, checked out, missing required check-in, missing required check-out and valid leave |
| Required fulfillment | Check-in and check-out fulfilled/required counts and percentages |
| Recent trend | Last 7 or 14 days of required fulfillment |

Clicking any attendance card opens Employee List by Condition, retaining the date and department. The main page does not load a full employee table.

### 5.2 Employee List by Condition

Purpose: find employees matching a selected attendance condition and support record follow-up.

| Page section | Contents |
|---|---|
| Navigation | Back to overview, preserving date and department |
| Context | Selected date, department, condition, matching employee count and data status |
| Controls | Six-condition selector; employee name/source ID search; clear search |
| Table | Employee name/source ID, check-in yes/no, check-out yes/no, valid leave yes/no, exemption and review indicator |
| Expanded review information | `alasan_review` when available |
| Pagination | Server-side pagination with 25, 50 or 100 rows per page |

Use a stable sort with source employee ID as a tie-breaker. Missing names display the source ID. Search and pagination run on the server so large departments remain usable. The displayed result count reflects the selected condition and search; clearing search restores the card population.

No dedicated employee profile, individual ranking or performance score is included in the initial scope.

## 6. Employee list conditions

Use the same fact measure that feeds the clicked card. Apply the same reporting date and department scope to both summary and list.

| Selected condition | Fact predicate |
|---|---|
| Active Employees | `active_employee_days = 1` |
| Checked In | `checkin_days = 1` |
| Checked Out | `checkout_days = 1` |
| Missing Required Check-in | `no_checkin_days = 1` |
| Missing Required Check-out | `no_checkout_days = 1` |
| Valid Leave | `leave_days = 1` |

These predicates already incorporate active population and relevant exemptions. Filtering only on `has_masuk = false`, for example, would incorrectly include exempt or nonactive audit records.

Conditions overlap. An employee may appear in both Checked In and Valid Leave. Do not add missing check-in and missing check-out counts to obtain distinct affected employees. If that additional metric is introduced, use the fact predicate `no_checkin_days = 1 OR no_checkout_days = 1`.

Employee exemption display uses `has_excused_checkin` and `has_excused_checkout`. Review indicators use `perlu_review`. Aggregate review totals include audit rows outside the active population and therefore need not match reviews visible in an active-employee condition list.

## 7. Interpretation and data quality rules

1. **Respect the reporting grain.** Multiple shifts or events still produce one employee-day. Event counts are not employee counts.
2. **Keep leave and attendance separate.** Leave and recorded events can overlap; they cannot form an exclusive attendance pie chart.
3. **Use valid partitions for stacked charts.** For each side, fulfilled required + missing required + exempt = active population.
4. **Do not average rates.** Sum numerators and denominators first, then divide. A zero denominator displays `—`.
5. **Preserve calendar coverage.** Weekend and holiday dates do not automatically reduce population under this contract.
6. **Keep missing data distinct from zero.** Check calendar/date state for missing aggregate dates. Do not turn every missing row into zero or silently omit gaps from trends.
7. **Show provisional results clearly.** Completeness does not by itself imply finality; reviews, nonfinal facts and date closure also matter. For a multi-date selection, assess all selected dates, including dates absent from the aggregate.
8. **Use historical department attribution.** Source department ID filters must include relevant effective surrogate versions. Current master data must not rewrite past placement. UNKNOWN remains included in institution totals.
9. **Interpret refresh timestamps carefully.** Institution views expose oldest and latest partition refresh times. The latest timestamp alone does not prove all partitions are fresh; refresh time is not proof of upstream delivery completeness.
10. **Keep cards and lists consistent.** Apply identical scopes and account for publication changes between requests. If data refreshes during navigation, show the updated status rather than treating differing counts as employee discrepancies.

## 8. Implementation boundaries and readiness

### Supported by the existing schema

The agreed counts, fulfillment KPIs, period rates, daily trends, department comparisons, previous-period calculations and employee condition lists require no new fact columns or aggregate tables. New application queries or API endpoints will still be needed for derived metrics, search and pagination.

### Application responsibilities

- Enforce manager-to-department access and employee-data authorization. The mart does not provide a manager permission mapping.
- Handle filters, navigation, display labels, comparison periods and pagination.
- Represent missing data, provisional results and null denominators accurately.
- Provide consistent publication handling between summary and employee-list queries.
- Benchmark realistic employee volumes, historical ranges and concurrent use before choosing additional indexes, caching or aggregation.

### Outside the initial scope

- Individual performance scoring or disciplinary conclusions.
- Late-arrival KPIs, working duration, WFO/WFH or leave-type breakdowns; these require further business contracts.
- Team/subunit filters without reliable organizational mapping and suitable aggregation grain.
- Full event, shift and leave-application detail; investigation of these remains in curated data.
- Fixed KPI targets, warning thresholds or automated escalation rules before management defines them.

### Data readiness

The referenced STTM reports that isolated small and bulk downstream tests passed, but the active target was not yet loaded and large-history/concurrency benchmarks remained outstanding. This is the documented status, not a fresh live database inspection. Production readiness requires checking the deployed schema, actual loads, date coverage, dimension names, quality state and access controls.

## 9. Acceptance criteria

- Institution totals equal the sum of all departments, including UNKNOWN.
- Daily cards reconcile to the corresponding fact predicates for the same scope and publication.
- Period cards use employee-day labels; unique employees are never inferred from daily sums.
- Rates use summed numerators and denominators and display `—` for zero denominators.
- Full and partial exemptions affect the correct required denominators and employee lists.
- Leave/event overlap does not produce misleading exclusive categories.
- Missing dates, incomplete delivery and provisional results are visible.
- Department filters retain historical attribution across dimension versions.
- Employee lists support all six conditions, search, stable server-side pagination and missing-name fallbacks.
- Access checks apply to both overview queries and employee-list queries.
- Both navigation paths preserve selected filters when returning to the parent page.
- Performance is measured with representative data and concurrency before production rollout.

## 10. References

- [Curated to mart and serving contract](sttm-curated-to-serving-kehadiran.md)
- [Source to curated attendance contract](sttm-source-to-curated-kehadiran.md)
- [Mart and serving schema](../sql/mart/20261028_attendance_daily.sql)
- [Schema implementation report](penyesuaian-mart-serving-20261028.md)

The current attendance contract governs metric semantics if older dashboard documents use different population, workday or absence rules.
