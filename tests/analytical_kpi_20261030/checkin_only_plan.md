# Next KPI test: gradual check-in delivery

Status: PREPARED, NOT EXECUTED. No fixtures have been inserted for this plan.
This supersedes the earlier all-at-once test proposal for the next test run.
The earlier isolated test scripts/results remain separate evidence.

## Purpose and execution boundary

Prepare complete-window check-ins, deliver them through raw -> curated ->
mart -> serving -> analytical dashboard, and inspect the dashboard before
creating any checkout. The current phase contains only checktype=1 events.
Checkout insertion and checkout-window verification belong to a later phase,
after the check-in dashboard checkpoint has been reviewed.

Use isolated staging/mart databases and explicit fixture manifests. Reuse raw
staging master snapshots where they meet the scenario; do not extract the full
source again or modify dbabsen_restore. Resolve scenario labels to employee,
department, shift and schedule IDs during setup. Synthetic status controls, if
needed, belong only to the isolated test master data. Record each copied or
synthetic master and every test event. Use the current Asia/Jakarta day if the
standard population snapshot procedure is used; a historical date needs a
separate population fixture and must not claim historical activity from today's
employee master. No reset, cleanup, data insertion or pipeline execution is
authorized by this preparation step.

## Confirmed rules and required eligibility change

- A valid shift has status TRUE. FALSE shifts are excluded from lateness
  assessment and first-shift selection. NULL or missing status is unknown and
  excluded from assessment until resolved.
- Filter valid shift candidates before selecting the first recorded shift;
  select that shift by its scheduled start, then its earliest check-in.
  A later shift's lateness does not change the employee-day result.
- Check-in at or before jam_masuk is ON_TIME, including before jam_masuk_awal;
  after jam_masuk is LATE. The first version still requires a complete usable
  recorded window; missing/ambiguous evidence remains UNKNOWN.
- Approved izin that excuses check-in is excluded from numerator and denominator.
  An izin that only excuses checkout does not automatically excuse arrival.
- A missing check-in is unassessed, not on time. Missing checkout in this phase
  is expected and must not prevent arrival classification.
- Preserve events linked to inactive/missing shifts in raw and audit evidence.
  Excluding a shift from lateness assessment is not permission to delete events
  or redefine the existing evidence-based attendance measures.

Implementation gap found during preparation: the earlier source-to-dashboard
fixture builder filters m_shift.status=true, but apply_curated_batch currently
joins raw.raw_shift without checking its status. An inactive referenced shift
can therefore still be classified as ON_TIME or LATE. Eligibility must be
implemented and verified before a passing result can be claimed for this test.
This plan has not changed or deployed that ETL logic.

Record the shift status and its snapshot time used for the test. Current master
status is not automatically proof of status in 2024-2026. Reprocessing after
reference changes must identify affected event IDs explicitly; merely changing
the master does not trigger the present manifest-based consumer.

## Fixture design

The accompanying checkin_only_cases.csv defines 18 distinct employee scenarios
in three department groups. Labels are placeholders, not fabricated production
identities. Use an ordinary first-shift window 06:00-07:30 with checkout bounds
16:00-20:00. The second shift, where applicable, uses a later non-overlapping
scheduled start with complete recorded bounds. The checkout bounds are retained
on the check-in records for future use, but there must be no checkout events.

Two independent cases require explicit controls: first-shift late followed by
second-shift on time, and first-shift on time followed by second-shift late.
For the earlier inactive-shift control, ensure the inactive scheduled start
precedes the active one; the inactive event must not become the KPI's selected
first shift. Missing status before a candidate active shift must be flagged
as ambiguous rather than silently assumed inactive.

| Department group | Late | On time | Assessed | Excused | Inactive-only | Unknown | No check-in | Late % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 2 | 4 | 6 | 1 | 1 | 0 | 0 | 33.33% |
| B | 3 | 1 | 4 | 0 | 1 | 1 | 0 | 75.00% |
| C | 0 | 0 | 0 | 1 | 1 | 1 | 1 | Undefined |

Expected organization total: 18 population rows, 10 assessed people, 5 late,
5 on time, 2 excused, 3 inactive-only, 2 unknown and 1 without a check-in.
The percentage is 5/10 = 50%. Do not sum department percentages. Department C
is omitted from a percentage ranking because the denominator is zero, but its
coverage remains visible. Expected ordering for the nonzero denominators: B, A.
Do not assign a final database status token for inactive-only until the ETL
eligibility change defines one; its required behavior is exclusion plus an
explicit inactive-shift reason. Coverage must expose that excluded group.

## Planned checkpoints

1. Baseline: capture protected dataset fingerprints and empty test fact/delivery
   state. Save fixture IDs, test date, all time bounds and status snapshots.
2. Population and leave: initialize only the isolated test population and the
   two approved check-in exemptions. Declare denominators before event delivery.
3. First batch: insert the first check-in per event-bearing scenario. Do not
   insert any checktype=2 row. Publish exact event/leave manifests and execute
   the real curated and mart Hop path when this test is later authorized.
4. Dashboard checkpoint: verify individual check-ins, first-shift arrival
   classification, department numerator/denominator, percentages, ranking and
   coverage. Record query responses and rendered chart evidence. Assert
   checkout_event_count=0, has_pulang=false and last_checkout_at IS NULL for
   all test employee-days. Publication is provisional. Any existing missing
   checkout measure must not be presented as a final early-departure decision.
5. Additional check-ins only: add the planned repeated/second-shift records in
   a separate manifest and repeat the dashboard checkpoint. The first-shift
   result and assessed-person denominator must not be inflated by event count.
6. Replay: resend unchanged IDs in a new committed batch and verify no duplicate
   people, stable percentages and unchanged business row versions for no-ops.
7. Stop: save the check-in checkpoint and its source/delivery manifests. No
   checkout is created automatically. The later checkout phase begins only
   after this check-in checkpoint is reviewed and continuation is requested.

## Acceptance criteria and evidence

- All 18 scenario outcomes match the fixture specification and eligibility rule.
- Inactive-only records cannot enter the lateness numerator or denominator;
  earlier inactive records cannot override the first active shift.
- Missing status/windows remain visible as unknown; zero assessed yields NULL.
- Check-in lateness is available before any checkout reaches the pipeline.
- Outbox, committed mart receipt and dashboard values agree for every batch.
- Duplicate, repeated and second-shift check-ins do not multiply people.
- Complete checkout bounds survive staging for later testing without a checkout
  event being fabricated.
- Existing unrelated facts, dashboards and raw/source records remain consistent
  with their baseline. Record simulated evidence as TEST, never as real activity.

Three department groups verify the calculation and incremental behavior. A
separate expansion to more than ten groups is needed for top-10 truncation and
tie ordering; it is not required to demonstrate this check-in-only checkpoint.
