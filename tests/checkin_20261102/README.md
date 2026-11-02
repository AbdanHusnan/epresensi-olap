# Active-shift check-in-only test — 2 November 2026

Status: **PASSED; stopped before checkout.** This is a future-date simulation
using every employee currently active in `dbabsen_restore`, not proof of their
actual future attendance, active status or personal roster assignment.

The source has 82,119 employees with status 1/2/3/4. All were retained in the
test population across 4,298 departments, including people without a usable
direct active Monday schedule. Employee, department, active shift and Monday
schedule masters were loaded with actual Hop pipelines and business-field
fingerprints checked against the read-only source. User identity extraction
copied only ID and employee ID. Source business records were not modified.

| Result | Count |
|---|---:|
| All currently active employees | 82,119 |
| Employees with usable direct active Monday schedules / check-ins | 72,249 |
| Assessed for lateness | 69,102 |
| Late on first recorded active shift | 27,647 |
| On time | 41,455 |
| Approved simulated check-in exemptions | 3,570 |
| Unassessed, without check-in | 9,447 |
| Checkout events | **0** |

Lateness is **27,647 / 69,102 = 40.01%**. These percentages describe intentionally
generated test scenarios, not real attendance behavior. There are 9,870 people
without a usable direct Monday schedule; 423 of them have a simulated exemption,
so they are counted in the excused group rather than the 9,447 unassessed group.
Everyone remains in the population; no parent/shared schedule was guessed.

## Data and rules

Databases: `staging_bkd_checkin_20261102` and `mart_bkd_checkin_20261102`.
The existing analytical/operational test dashboards now read this mart and
default to 2 November. The prior test databases were preserved. The main
staging raw history and empty main mart were not loaded by this test.

Simulated transactions were created only in the isolated raw staging tables,
with complete bounds copied from actual active Monday schedules. The test
chooses an ordinary non-wrapping check-in window and the earliest usable active
department schedule. That fixture choice is not a production roster resolver.
Metadata is in `test_checkin.cohort`, `test_checkin.events` and
`test_checkin.leave_ids`; all fixtures carry `CHECKIN_ONLY_20261102` markers.

Because the requested date is in the future, the test seeds explicit population
fixtures with `EXTRACTION_SNAPSHOT` provenance and zero-event daily baseline
rows. It does not bypass the production procedure's current-day snapshot guard
or claim a historical/as-of population. Attendance then follows the real
manifest-based curated Hop pipeline, outbox, mart Hop workflow and serving view.

All test event references have shift status TRUE. The revised curated flow
preserves the status used for evaluation. It excludes inactive shifts before
first-shift selection, keeps unknown status unassessed, and retains raw events
for audit. Only the first recorded valid shift determines daily lateness; an
employee's earliest check-in on that shift is used. Before the early boundary
and exactly at the start are on time; after the start is late. Approved check-in
exemptions are excluded from the denominator. Checkout bounds are retained,
but there are no checkout events or checkout-window classifications in this run.

## Gradual loading and verification

1. Loaded 72,249 initial check-ins. Verified every employee/date, recorded
   window, first-shift event ID, department numerator and denominator.
2. Delivered the committed snapshot to the mart through Hop. Both website
   dashboards passed HTTP and browser checks, including manager department
   restrictions and the independent expected top-10 lateness ranking.
3. Only after the first browser checkpoint, inserted 12,350 additional check-ins:
   repeats plus on-time-first/late-second and late-first/on-time-second cases.
   The saved audit checks that their extraction timestamps follow that browser
   checkpoint. No checkout was inserted.
4. Reprocessed through Hop. The final 84,599 event rows still represent 72,249
   checked-in employees. All first-shift classifications and percentages stayed
   unchanged, and every selected first-shift event/schedule matched the oracle.
5. Replayed identical manifests: no pending delivery or changed mart row
   versions. Final HTTP/browser checks passed for 13 analytical and 9 operational
   cards. Checkout count, `has_pulang` and last-checkout timestamp remained
   zero/false/NULL for every fact. Data publication remains provisional.

Evidence: [summary](summary.json), [first checkpoint](verification_first.json),
[later check-ins](verification_later_checkins.json), [final verification](verification_final.json),
[replay](replay.json), [HTTP checks](http_verification.json),
[first browser checkpoint](browser_first.json), [final browser checks](browser_final.json),
and [analytical screenshot](browser_final_director.png).

The harness has guarded phases `setup`, `masters`, `fixtures`, `first`, `names`,
`later_checkins`, `replay`, `verify` and `report`. It refuses to reset existing
databases, and the later-check-in phase requires the initial dashboard evidence.
Do not rerun fixture/setup phases on the existing data. No checkout phase is
implemented or scheduled. Continue with checkout only when requested.
