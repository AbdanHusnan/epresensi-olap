# 82,000 employee load test — 30 October 2026

Target explicitly confirmed by user: expand `mart_bkd_bulk_20261029`.
Live Metabase source ID 1 and the website already point to this database.
Writes flow from paired `staging_bkd_mart_bulk_20261029` through the existing Hop
outbox/apply/commit-confirm/ack workflow. No direct fact inserts or re-bootstrap.

1. Save baseline evidence and pre-load database backups. Preserve the original
   2,400 records and fingerprint protected reference/active databases.
2. Expand the existing 28 October population through 10,000, 40,000, and 82,000
   distinct employees, with reserved synthetic IDs and deterministic reuse of the
   original 2,400 curated records. Preserve all 757 departments, the 12 existing
   scenarios, leave exemptions, two-shift and cross-midnight timing. This is a
   scenario-heavy capacity fixture, not an estimate of real attendance rates.
3. Measure fixture/capture time separately from Hop wall time (includes JVM
   startup), workflow internal duration, rows/sec, payload/storage growth, and
   resource usage. Verify every row/measure and every department aggregate after
   each ramp. Stop escalation on failure, OOM, or unacceptable service impact.
4. Final user constraint: retain one date and exactly 82,000 employee-day facts.
   The proposed 22-weekday historical expansion was rejected by automatic review
   and then declined by the user. It was not executed. Historical capacity and a
   single full 82,000-row delivery remain untested.
5. Independently reconcile source/fact values, Boolean-derived measures,
   dimension identities/effective intervals, source-grouped department totals,
   ratios, committed receipts, and empty pending queue. Test an empty-queue rerun.
6. Benchmark institution, department, trend, and paginated employee queries over
   one day and the reporting window; preserve EXPLAIN ANALYZE/BUFFERS. Separate
   initial from repeated timings; do not call OS caches cold without evidence.
7. Exercise real signed Metabase embeds with both roles, all nine charts, and
   1/5/10 concurrent virtual users (bounded chart fanout). Record failures,
   throughput, p50/p95/max, cached responses, and all-chart completion time.
   Compare six KPI values and detail scope against database references. Check
   actual Chromium page-to-chart rendering for both roles and mobile layout.

Provisional engineering targets (not agreed production SLAs): zero correctness
errors; zero failed chart requests; warm SQL p95 below 500 ms; nine-chart HTTP
p95 below 5 s at 10 users; browser chart completion below 8 s. Report failures
and observed capacity honestly; no automatic production tuning or cutover.
Raw-to-curated ingestion, production SSO, network/WAN latency, annual retention,
and real-world attendance distributions are outside this downstream benchmark.
