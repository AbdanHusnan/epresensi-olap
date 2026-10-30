# Website integration verification — 30 October 2026

The three-page Next.js prototype embeds the existing Metabase dashboards using
`mart_bkd_bulk_20261029` data for 28 October 2026. All 54 HTTP checks passed;
see [results.json](results.json).

## Repeat the HTTP checks

With the local stack running and `.env.hybrid` configured:

```bash
python3 tests/hybrid_website_20261030/verify.py
```

The script reads local credentials without printing them. It checks anonymous
access, invalid credentials, both role logins, page and token authorization,
server-assigned department scope, all nine charts per dashboard, reference KPI
values, employee rows and CSV scope, rejected department overrides, session
signature tampering, logout, expired tokens, and missing department scope.
It writes the check summary to `results.json`.

## Browser verification

Playwright Chromium checks completed against the running website with fresh
browser contexts for each role:

- Login, invalid-password feedback, embedded dashboards, and logout worked.
- Director KPI values matched `[2400, 1000, 1000, 1000, 600, 1200]`.
- Manager KPI values matched `[4, 1, 1, 3, 2, 1]` for department `30114`.
- The manager department widget was absent; employee and department IDs had no
  thousands separators.
- Injecting an expired initial embed token triggered the authenticated token
  provider: two token requests and nine successful chart requests confirmed
  automatic recovery.
- Desktop and 390-pixel mobile layouts were checked. The mobile website had no
  horizontal overflow.

The production Docker build passed TypeScript checking and Next.js compilation.
The environment health check passed for all five services. These are prototype
verification results, not a production security audit.

## Dataset expanded after this baseline

The user-authorized 30 October load test expanded the same database to 82,000
employees on one date. The fixed 2,400-row expectations above describe historical
evidence. Use [the expanded-data checks and results](../load_82000_20261030/README.md)
for the current database; the original `verify.py` will fail its old count assertions.

The 82,000-record test has since been removed and superseded by the
[source-to-dashboard rerun](../source_to_dashboard_20261030/README.md): 72,259 real
source employees on 30 October 2026. Use that directory’s checks for current data.
