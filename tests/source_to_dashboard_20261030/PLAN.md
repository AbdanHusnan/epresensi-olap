# Source-to-dashboard rerun

User authorized deleting the previous bulk test and using real source employees
and shifts, with up to 82,000 employees. User explicitly chose creation of tagged
test transactions in `dbabsen_restore`, rather than existing real attendance.

Selected 72,259 real active employees across 3,829 departments, each with a source
user and an active department schedule for Friday 30 October 2026. Scheduled
checkout must be later than check-in: overnight attribution is outside this test.
These are real department schedules; this does not establish a historical personal
roster assignment. Population completeness applies only to the selected test cohort.

Previous test data removed: old tagged bulk source events/leaves, the 82,000-row
paired staging/mart databases, and the old bulk raw/curated test database. Exact
source IDs and markers constrain deletion. Pre-removal backups and old audit reports
are retained; unrelated test datasets and active databases are outside cleanup scope.

Create deterministic tagged source transactions: approximately 88% both events,
3% check-in only, 1% checkout only, 1% no events, 3% full-day leave, 2% exempt check-in
with checkout, 2% exempt checkout with check-in. A subset with another real schedule
has two event pairs. Timing comes directly from source schedules. No employee,
user, shift, or schedule master is created or modified.

Run actual Hop source-to-raw loaders for seven master datasets and two transaction
datasets, verifying source/raw business-field hashes. Only user ID/employee ID are
needed from m_user; credentials are not copied. Publish explicit manifests only
after all raw loads verify. Run the standard curated pipeline with today's population
snapshot, then standard mart bootstrap/apply/commit-confirm/ack workflow.

Check source transaction oracle against every curated employee/day, shared
curated/fact fields, all department totals/ratios, dimension identity/effectivity,
manifest/receipt completion, scope authorization, dashboard responses, real browser
rendering, loading times, SQL plans, and bounded concurrent requests. Existing
reader connection limits remain part of the measured configuration.

The first source-fixture creation attempt timed out at 180 seconds and rolled back;
this setup failure is retained separately from ETL measurements. Retry uses a longer
fixture-creation timeout. Source sequence gaps from a rolled-back insert are normal.
