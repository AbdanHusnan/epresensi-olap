# Hybrid dashboard prototype plan and review report

Date: 29 October 2026  
Status: Draft for user review before implementation

Build a custom website that embeds attendance dashboards from Metabase and Apache Superset, compare both implementations, and select the engine using measured performance and usability. The prototype will run on the existing Docker build-and-test server. Production will run on a separate server later.

The first implementation should compare self-hosted open-source editions. Superset is an initial candidate for flexible embedded department restrictions; Metabase is a candidate for straightforward dashboard authoring. Neither is the performance winner until the comparison is complete.

## 1. Agreed direction and scope

| Item | Direction |
|---|---|
| Delivery approach | Hybrid website with embedded BI dashboards |
| Candidates | Metabase and Apache Superset |
| Environment | New prototype containers on the existing Docker test server |
| Data | Existing PostgreSQL mart and serving layer |
| Main priorities | Dashboard usability, performance, and information appropriate to each role |
| Users | Department head and head of the organization |
| Login | Deferred during the prototype |
| Final deployment | Separate live server after prototype evaluation and production preparation |
| Alternative | Custom charts remain an option if neither BI engine meets requirements |

The governing references are the [current KPI data-lineage document](data-lineage-dashboard-kpi.md) and [curated-to-serving contract](sttm-curated-to-serving-kehadiran.md). The older `dashboard.md` blueprint is obsolete for this plan; its layout, KPI selection, and stack constraints do not apply.

This phase produces a reviewable prototype and comparison report. Production login, final organizational permission mapping, public deployment, new KPI definitions, and changes to ETL business rules are outside this phase.

## 2. Role-oriented dashboard design

The role determines information scope. The dashboard type determines how that information is presented.

| Property | Department head | Head of the organization |
|---|---|---|
| Dashboard type | Operational | Analytical |
| Main question | What is happening today and what needs follow-up? | How are attendance patterns changing across departments? |
| Proposed default period | Today in Asia/Jakarta | Current month in Asia/Jakarta |
| Scope | Assigned department | All departments |
| Summary | Daily attendance measures | Period totals and rates with correct labels |
| Charts | Daily attendance trend | Organization trends and department comparisons |
| Table | Employee daily records | Department summary |
| Initial drill-down boundary | Employee daily details within the department | Department daily summaries |

Employee-level access for the organization head remains a review decision. It is not assumed merely because the role can see all department summaries.

Both dashboards should show freshness and provisional status. A missing current-day check-out must remain distinguishable from a finalized outcome. Period sums must be labeled as employee-days where applicable, rather than unique employees.

The first comparison will use the same six main measures from the current serving contract, one comparable trend, and one table per role in each engine. Additional visualizations follow review of this shared baseline.

## 3. Division of responsibilities

```text
Browser
  |
  v
Next.js website
  |-- Navigation and page layout
  |-- Role and department preview controls
  |-- BI engine comparison selector
  |-- Backend embedding-token endpoints
  |
  +---------------------+
  |                     |
  v                     v
Metabase             Superset
  |                     |
  +----------+----------+
             |
             v
Existing PostgreSQL mart_bkd
  |-- serving summaries and trends
  |-- department filter data
  |-- employee daily facts and dimensions
  |-- date completeness and publication state
             ^
             |
         Existing ETL
```

Next.js, React, and TypeScript provide the website shell and backend token handling. The selected BI engine initially owns cards, charts, tables, date filters, and analytical department filters. The shell's department preview control simulates an assigned scope; it is different from an ordinary dashboard filter.

The website backend keeps signing secrets and BI service credentials on the server. The browser receives short-lived embed tokens. It receives no PostgreSQL credentials.

There will be a small integration module for each engine, covering dashboard identifiers, token issuance, initialization, renewal, loading, and errors. Dashboard definitions remain engine-specific; they are not automatically portable between tools.

## 4. Metabase and Superset comparison

| Area | Metabase | Superset | Prototype decision |
|---|---|---|---|
| Embedding | Guest embeds available in OSS | Embedded SDK and guest tokens | Test each supported embedding flow |
| Department scope | Signed locked parameters on guest embeds | Row-level restrictions in guest tokens | Verify every dataset and visual |
| Exploration | Guest mode excludes drill-through menus and query builder | Embedded interactions depend on configuration and chart support | Test exact required interactions |
| Authoring experience | Evaluate building and editing the two views | Evaluate building and editing the same views | Record effort and user feedback |
| Runtime | Application plus metadata database | Application, metadata database, and configured cache | Measure total resource use |
| Paid features | SSO embedding and full-app embedding require Pro or Enterprise | Proposed SDK and guest-token flow does not require a commercial embedding tier | Start with OSS; flag gaps before considering paid options |
| Performance | Unmeasured for this workload | Unmeasured for this workload | Select using equivalent benchmarks |

Metabase guest embeds support dashboards and filters, but do not provide the same interaction set as SSO embeds. Its current documentation deprecates legacy static embedding in favor of guest embeds. Use the supported flow for the pinned release. [Metabase embedding options](https://www.metabase.com/docs/latest/embedding/introduction)

Guest embeds do not apply Metabase account permissions or row-and-column security. Department segregation must use locked parameters, configured on every relevant card and filter path. [Metabase embedded security](https://www.metabase.com/docs/latest/embedding/securing-embeds)

Superset's SDK obtains guest tokens through the host backend, and tokens can include row-level security rules. Configure allowed embedding origins and token renewal. The linked documentation is marked “Next”; verify the supported behavior against the stable release selected for implementation. [Superset embedding documentation](https://superset.apache.org/user-docs/using-superset/embedding/)

The operational employee table is a specific evaluation point: verify that required filtering, row limits, navigation, and detail access work in the embedded OSS mode. A visually paginated table does not necessarily imply database-side pagination; inspect queries and response sizes.

## 5. Proposed Docker infrastructure

| Service | Purpose | Persistence |
|---|---|---|
| Dashboard web | Next.js shell and token endpoints | Versioned application image |
| Metabase prototype | First BI candidate | Metadata in PostgreSQL |
| Superset prototype | Second BI candidate | Metadata in PostgreSQL |
| BI metadata PostgreSQL | Separate databases and credentials for each engine | Named persistent volume |
| Redis for Superset | Filter state and cache infrastructure | Configure according to selected release |
| Existing mart PostgreSQL | Attendance source | Existing managed storage |

Connect BI services to the existing `epresensi_mart` network for read-only access. Keep metadata on a separate internal network. The web container needs access to the BI services, not direct attendance-database access in this initial design.

Use distinct service names, ports, volumes, and secrets. Check current containers and host capacity before selecting resource limits or reusing anything. Existing Superset-related files are references; their presence does not prove a working deployment or compatibility with the current data contract.

Use pinned image versions and environment-based configuration. The browser must be able to reach the BI embed address; Docker-only service names are not browser addresses. Use controlled test addresses or an existing reverse proxy as appropriate. Production domains and HTTPS are configured when preparing the live deployment.

Metabase should store application metadata in PostgreSQL rather than the default embedded H2 database. This preserves dashboard definitions across container replacement. [Metabase Docker documentation](https://www.metabase.com/docs/latest/installation-and-operation/running-metabase-on-docker)

Superset also maintains a separate metadata database. Its caching supports Redis; cache configuration and optional worker services will follow the chosen release and enabled features. Alerts, scheduled reports, and asynchronous query workers are not part of the initial comparison. [Superset architecture](https://superset.apache.org/admin-docs/installation/architecture/), [Superset caching](https://superset.apache.org/docs/configuration/cache/)

## 6. Data integration

| Dashboard use | Source |
|---|---|
| Cards, trends, department comparisons | `serving.v_kehadiran_departemen_harian` and underlying approved aggregates |
| Department choices | `serving.v_departemen_filter`, limited to the preview scope |
| Employee records | `mart_kehadiran.fact_kehadiran_daily` with required dimensions |
| Freshness and completeness | Serving quality fields and `serving.attendance_date_state` |

Scope by stable source department ID so historical dimension versions are handled consistently. Confirm the necessary scope field is present in each BI dataset. Do not use organization-wide preaggregated data for department-restricted views.

Use equivalent metric definitions, date boundaries, null handling, and query limits in both engines. Summary queries should read serving aggregates; employee detail should read daily facts only when needed. SQL reference queries provide the correctness baseline.

Verify the active mart's data readiness before building the charts. If realistic data is unavailable, use an isolated representative test dataset and identify it clearly. Do not populate or modify business tables merely to demonstrate the interface. Missing data, a zero population, and an undefined percentage must remain distinct.

## 7. Role preview and scope verification

The prototype exposes “Department head” and “Organization head” previews. Department-head preview includes a department selection that stands in for the assignment a future authenticated session would provide.

Because anyone permitted to use the preview can switch roles, this is a test mechanism rather than user authentication. Limit the unauthenticated prototype to the controlled testing environment. Production must replace preview-derived scope with trusted session-derived scope.

Test a scoped token independently of the role switch: altering a normal filter, URL, chart request, or export must not expose another department. Include filter-option lists, token expiry, token renewal, and switching between departments after cache warm-up. Missing or invalid scope should deny the scoped request rather than default to all departments.

Both engines use dedicated read-only mart credentials. Secrets remain outside Git and client bundles. Available exports must respect the same scope; disable them during the prototype if that behavior cannot be demonstrated.

## 8. Implementation stages

| Stage | Work | Reviewable result |
|---|---|---|
| 1. Environment inspection | Check ports, resources, Docker network, data readiness, and supported versions | Recorded versions and deployment configuration |
| 2. Shared shell | Create navigation, role preview, engine selector, and integration modules | Website opens with clear loading and error states |
| 3. BI infrastructure | Deploy isolated candidates and persistent metadata; configure read-only data sources | Both engines reach the same approved data |
| 4. Equivalent dashboards | Build operational and analytical views in each engine | Four embedded dashboard implementations |
| 5. Correctness and scope | Compare results to SQL and exercise restricted-access paths | Recorded pass or fail evidence |
| 6. Usability and performance | Review tasks with the user and run controlled benchmarks | Comparative measurements and observed limitations |
| 7. Selection and handover | Score candidates, explain tradeoffs, document operation and migration | Engine recommendation and next implementation plan |

The first review milestone is the shared website with the department-head baseline embedded from both engines. Review this before completing the organization-wide view and expanding visual content.

## 9. Performance test design

Use the same database snapshot, filters, chart count, time ranges, table limits, browser, and network path. Run one engine's load test at a time, with comparable resource budgets. Record background ETL activity and server utilization so interference is visible.

| Scenario | Measurement |
|---|---|
| Initial dashboard open | Time until every required visual has finished rendering |
| Date filter change | Time until every affected visual reflects the new date |
| Department selection | Scope transition and updated visual completion |
| Employee table navigation | Response time, SQL workload, and response size |
| Sustained use | Response times and errors under repeated representative actions |
| Data refresh | Delay between mart publication and visible updated results |

Start with 1, 10, 25, and 50 simulated concurrent users. These are exploration levels, not known demand or a promised production capacity. Stop escalation if the test host or shared database is overloaded and report the observed limit.

Measure first-visit browser loading separately from repeat visits. First compare with BI query-result caching disabled where supported. Then compare tuned settings under the same permitted freshness window. Record cache settings and warm-up procedures; do not describe an uncached BI result as proof that PostgreSQL's buffers were cold.

Use browser automation for user-visible timings and a repeatable load script for concurrency. For each concurrency level, propose two minutes of warm-up followed by ten minutes of measured traffic, repeated three times where host capacity allows. Record sample counts, median, 95th percentile, failures, CPU, memory, database connections, and query durations. Low-sample exploratory runs should not be treated as stable percentile estimates.

Proposed initial goals are a usable dashboard within 3 seconds and completed filter updates within 1 second at the 95th percentile. These are review targets, not measured results. Report outcomes separately for every tested concurrency level and record the largest level that meets them. Freshness tolerance must be agreed before the tuned-cache comparison.

## 10. Selection criteria

Correct data and demonstrated department isolation are mandatory. A candidate that fails either cannot win by receiving a higher performance score.

| Criterion | Proposed weight |
|---|---:|
| User-visible performance | 40% |
| Operational and analytical usability | 25% |
| Embedding and future role integration | 15% |
| Deployment and maintenance effort | 10% |
| Licensing and required paid features | 10% |

Score each criterion from 1 to 5, with 1 meaning poor fit, 3 meaning acceptable with limitations, and 5 meaning a strong demonstrated fit. Total score out of 100 is the sum of `weight × score / 5`. Attach measurements or concrete observations to every score.

Choose Metabase if its guest embedding supports the required experience and it provides the better measured balance. Choose Superset if its scope controls, interactions, performance, and operating effort provide the better balance. If both miss essential requirements, identify whether the cause is the data queries, hosting capacity, or BI rendering before proposing custom charts.

## 11. Deliverables and migration path

The prototype will deliver the shared website, two role-oriented dashboards in each engine, reproducible container configuration, reference queries, scope tests, benchmark scripts and results, and an operating guide. Dashboard definitions and metadata backups must be recoverable; rehearse restoring them to a clean test environment using the selected edition's supported mechanisms.

After selecting an engine, prepare the live-server configuration, identity integration, trusted role-to-department mapping, HTTPS, backups, and release rollback. Keep the test server available for updates. Removing the unused prototype engine is a separate cleanup step after its findings and configuration have been retained.

If custom rendering is selected later, reuse the website shell, data contract, role model, reference SQL, and test scenarios. Replace the embed integration with application query endpoints and chart components. Charts, filter interactions, and permission enforcement will require implementation and testing; this is not a zero-cost toggle.

## 12. Review decisions

The following proposals are open for correction before implementation:

| Decision | Proposed starting point |
|---|---|
| Editions | Compare self-hosted OSS editions; record paid-feature gaps |
| Default periods | Today for department head; current month for organization head |
| Organization-head detail | Department summaries initially; employee access pending |
| Filter ownership | BI controls ordinary analytical filters; website controls preview scope |
| Performance goals | 3 seconds initial completion and 1 second filter response, evaluated by concurrency level |
| Cache freshness | Agree an acceptable delay before tuned testing |
| Scorecard | Use the proposed weights with correctness and isolation as mandatory gates |

Review of this report precedes implementation, as requested. No containers, application code, database permissions, or dashboards are created by this report.
