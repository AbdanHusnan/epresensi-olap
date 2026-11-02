# Analytical KPI investigation — 30 October 2026

The authorized follow-up test is now complete for [2 November 2026](../checkin_20261102/README.md):
all 82,119 currently active source employees, active shifts only, check-ins loaded
and verified on the dashboard before additional check-ins, and zero checkouts.
The preparation plan below is retained as an earlier design; its inactive-shift
negative controls were not inserted into this active-only run.

The next test is specified in [checkin_only_plan.md](checkin_only_plan.md) with
[checkin_only_cases.csv](checkin_only_cases.csv). It is prepared, not executed:
check-ins must reach the dashboard before checkout fixtures are created. The
plan also records the currently missing curated shift-status eligibility check.

## First-shift lateness implementation

The user confirmed that the first shift determines lateness, a check-in before
the early boundary is not late, and a check-in exemption is excluded. Curated
events now preserve both early check-in and last checkout snapshot boundaries,
and classify each check-in or checkout window. The checkout classification
describes timing only; it is not a disciplinary decision or a new checkout KPI.
At daily grain, the first recorded shift is selected by scheduled start and
then its earliest check-in; a missing start, conflicting first-shift tie,
unresolved event, missing window, or cross-midnight window remains UNKNOWN.
The event/schedule identifiers and reason are retained. Without a complete
personal roster, this is the first **recorded** shift, not proof of the first
assigned shift or a rule for employees who did not check in.

The mart's additive fields and `serving.v_lateness_employee_daily` feed the
analytical first-shift lateness percentage. The chart counts distinct people
with a late assessed employee-day / distinct people with an assessed employee-day
in the chosen department and period. Approved check-in exemptions, missing
check-ins and unknown employee-days are excluded; coverage is shown separately.
During multi-day periods, coverage categories can overlap for the same person.

The schema and functions were installed in `staging_bkd` and `mart_bkd` and in
the isolated dashboard pair `staging_bkd_mart_bulk_20261029` and
`mart_bkd_bulk_20261029`. Definitions alone do not replay existing batches.
All 68,295 check-ins in the dashboard's synthetic October cohort lack a source
early boundary; the chart has no assessed rows. The coverage card reports
67,205 people pending/unknown, 3,610 excused, and 1,444 without a check-in.
These are test cohort figures, not historical or organization-wide statistics.
The active staging has raw history but no curated daily facts; the active mart
has no fact rows. A historical load needs an approved historical population and
department policy, and a producer for durable event manifests. It was not run.

Validation used dedicated synthetic databases `staging_bkd_window_test_20261030`
and `mart_bkd_window_test_20261030`: boundary values, first-vs-second-shift
selection, before-early on-time, missing windows, leave exemption, checkout
window capture, outbox delivery, corrections, deletion, replay, unchanged
attendance totals, and a 50% serving example passed. Existing facts default to
UNKNOWN until explicitly processed; old immutable payloads are accepted as
UNKNOWN. `add_analytical_lateness.py` restores the two new dashboard cards after
dashboard provisioning; `install_lateness_mart.py` installs the additive mart
definitions without a load.

**Correction:** The recent and prior-ID samples below include October 2026 and
are not valid evidence for the requested January 2024–September 2026 review.
Use `historical_schedule_review.sql` and the historical review below for that
period; the earlier observations are retained only as an audit trail.

## Historical review: 1 January 2024–30 September 2026

The query sampled 0.1% of physical blocks of `public.t_checkinout` with a fixed
seed, filtered check-ins by `created_at` to the requested period, and excluded
the known dashboard, bulk, and E2E test markers. A larger 2% sample timed out
after 180 seconds. This block sample is not a count of the full population or a
statistically representative estimate. The sample included 43,410 check-ins:
14,943 in 2024, 15,680 in 2025, and 12,787 in 2026. Its latest observed date
was 31 August 2026, so it does not establish September coverage.

| Event snapshot | 2024 | 2025 | 2026 through 31 Aug | Total |
|---|---:|---:|---:|---:|
| `jam_masuk_awal < jam_masuk` | 14,883 | 15,611 | 12,729 | 43,223 |
| Before `jam_masuk_awal` | 0 | 0 | 0 | 0 |
| In the inclusive window | 13,044 | 13,670 | 11,093 | 37,807 |
| After `jam_masuk` | 1,839 | 1,941 | 1,636 | 5,416 |
| Equal bounds | 59 | 67 | 58 | 184 |
| Missing either bound | 1 | 2 | 0 | 3 |

Across the sample, three schedule references could not be resolved. Of the
matched records, 1,065 transaction start snapshots and 1,193 early-bound
snapshots differed from the current master; these are overlapping counts, not
necessarily separate records. None of the 43,407 resolved events had a
`work_code` different from `m_jadwal.jenis`, and none had a schedule weekday
different from the event calendar weekday. A shift owner was absent in 32,213
records and differed from the event department in 1,047 other records. Missing
ownership does not prove the shift is shared.

The pattern is consistent with treating the event snapshot's `jam_masuk_awal`
through `jam_masuk` as a check-in window. It does not prove the application
rejects earlier check-ins, nor that all later check-ins are officially late;
the database views expose these fields without defining lateness. Repeated
check-ins, multiple shifts, exemptions, equal/reversed bounds, and historical
time changes still need rules before creating the KPI. The first attempt's
timeout and the sample's physical-block clustering limit conclusions.

The existing analytical izin ranking is a horizontal top-10 percentage chart.
Its numerator is distinct active employees with valid leave in the selected
period and department; its denominator is distinct active employees in that
period and department. Ties are ordered by department label. A person who moves
can count in both departments. The data is a provisional simulated test cohort.
In the current dataset each of the ten displayed departments has 1 of 1 people
with leave; the percentage does not imply a large number of employees.

The late-arrival KPI has not been created. `investigate_schedule.sql` performs
read-only aggregate checks against `dbabsen_restore`:

- `t_checkinout.jadwal_id` references `m_jadwal.id` in the observed data, and
  `m_jadwal.jenis` has an actual foreign key to `m_shift.id`. The event's
  `work_code` also normally matches that shift ID. An event's own `departemen`
  need not match the shift's owning department; the shift can be shared.
- `t_checkinout` stores snapshots of `jam_masuk` and `jam_masuk_awal` as well as
  the schedule ID. Current `m_jadwal` is not a proven historical snapshot.
- Among 106,616 schedule rows, 94,524 have `jam_masuk_awal < jam_masuk`, 11,971
  are equal, and 121 have the early value later than the start. The equal group
  includes 4,211 rows where scheduled start and end are both midnight. These
  patterns require separate interpretation; none proves roster assignment.
- Of the 100,000 greatest IDs, 33,149 are check-ins dated 30 October. All 33,149
  have a transaction start time but lack the transaction early-bound value.
  These are the recent test cohort and are not representative of production.
- Of the 100,000 IDs immediately preceding the tagged 30 October test cohort,
  23,278 are check-ins dated 24 August–28 October. Of these, 23,119 have an
  early bound before the start: zero check-ins were before the early bound,
  12,936 were within the inclusive bounds, and 10,183 were after the start.
  155 have equal bounds; four have at least one missing bound. Two do not resolve
  the referenced master. Two differ between event and current master bounds.
  The sample may include older test events and is not a representative survey.

These observations are consistent with the user's proposed check-in window,
but cannot prove validation behavior or whether after-start check-ins are
officially late. Multiple shifts, early or overnight windows, exemptions, and
historical schedule changes still need defined treatment. Current daily mart
facts do not carry the event schedule or the early boundary.

## Historical checkout review

The actual source fields in both `m_jadwal` and `t_checkinout` are `jam_keluar`
and `jam_keluar_akhir`; there are no `jam_pulang_awal` or `jam_pulang` columns.
`historical_checkout_review.sql` uses the same read-only 0.1% physical-block
sample and January 2024–September 2026 date filter and excludes the known test
markers. It contains 43,323 checkout events: 14,535 from 2024, 16,350 from 2025,
and 12,438 from 2026. The latest sampled date is 31 August 2026; September is
not observed. The sample is not a population total or representative estimate.

The sample has 42,100 events where the recorded shift start is before its
scheduled end and the checkout end is before the latest checkout bound. For
those ordinary same-day windows, 41,267 event times were within the inclusive
`jam_keluar`–`jam_keluar_akhir` window, 833 were before `jam_keluar`, and none
were after `jam_keluar_akhir`. Six were exactly at `jam_keluar` and one exactly
at `jam_keluar_akhir`. Among the 833 earlier events, 108 were within five minutes
of scheduled end, 390 were more than five through 60 minutes early, and 335 were
more than 60 minutes early; 40 were before the recorded shift start. None were
marked manual. Such events are not automatically proof of early departure:
multiple shifts, cross-day assignment, exceptions, and corrections need review.

Of all sampled checkout records, 1,141 have an overnight indicator
(`jam_keluar < jam_masuk`); the simple same-day window comparison above excludes
them. Nine records lack a matching master schedule and both checkout bounds.
The recorded `jam_keluar` differs from the current schedule in 2,236 matched
events; `jam_keluar_akhir` differs in 3,045, with possible overlap. Current
schedule values should not silently replace event snapshots for historical use.
In the current schedule master, 96,186 of 106,616 rows have `jam_keluar` before
`jam_keluar_akhir`, 10,078 have equal values, and 352 have the end later than
the last bound (which may involve midnight or invalid configuration). Master
counts are current snapshot counts, not historical assignments.

The observed times are consistent with `jam_keluar` being the scheduled end and
`jam_keluar_akhir` being an upper checkout boundary. They do not prove the
application enforces that window or define whether an early checkout is a
violation. The checkout event's daily `jadwal_id` can refer to the next day of
an overnight shift, so determining the intended session requires pairing with
its check-in and handling ambiguous cases explicitly.
