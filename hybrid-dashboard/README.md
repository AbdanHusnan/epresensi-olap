Current layout uses **one dashboard container** with daily KPI cards, a trend
with **3D / 7D / 1M / 3M / 6M / 1Y / Custom** controls, and the daily table below.
Daily and trend filters remain independent. Top management sees its department
summary and department rankings; employee daily records remain only in the
manager view. [Current layout and checks](../tests/unified_dashboard_20261030/README.md).
Earlier layout notes below are retained for context.

Current filters are separated into **Daily attendance** (one date for cards,
rankings and detail tables) and **Attendance over time** (a date range for the
line chart). Each section has an independent department-name search. Table
search remains local to the daily detail tables. See the
[filter update and evidence](../tests/daily_period_filters_20261030/README.md).
Earlier shared-date notes below describe the preceding layout.

The dashboard now has an explicit test-run selector for the original 30 October,
2 November check-in, and gradual 30–31 October simulations. Shared date controls
apply to overview and detail; search appears above, and filters only, the detail
tables. The first gradual morning batch is the current checkpoint. See
[repair and test evidence](../tests/dashboard_revision_20261030/README.md).

# e-Presensi website prototype

Three pages backed by the existing Metabase dashboards:

| Page | Access |
|---|---|
| `/login` | Public sign-in form |
| `/analytical` | Director; Metabase dashboard 2, organization summaries |
| `/operational` | Manager; Metabase dashboard 1, department 30114 |

Open http://localhost:3100. The local usernames are `director` and `manager`.
Passwords are generated and stored only in gitignored `.env.hybrid`, under
`DEMO_DIRECTOR_PASSWORD` and `DEMO_MANAGER_PASSWORD`. Roles and manager department
are assigned on the server; there is no client role selector or self-registration.
The test date is configured with `DASHBOARD_TEST_DATE`, currently 2 November 2026.
The current dataset retains all 82,119 active source employees and their display
names. The check-in-only simulation has 72,249 employees with active Monday
schedules and check-ins; checkout remains zero. See the
[November test evidence](../tests/checkin_20261102/README.md).

## Implementation

- Node crypto signs and verifies an eight-hour HttpOnly, SameSite=Lax session.
- Server-rendered pages check the session and role before returning content.
- `POST /api/auth/login` and `/api/auth/logout` handle account sessions.
- `POST /api/metabase-token` authenticates and authorizes the requested dashboard,
  issues a ten-minute signed guest JWT, and locks managers to their assigned ID.
- Mutating endpoints validate the request origin. Credential comparisons use
  constant-time hashes; no password or signing secret is bundled into client code.
- The supported Metabase guest web component loads from port 3101, with its token
  provider pointing to the authenticated website endpoint. Date filters remain
  editable; the manager department filter is locked and omitted from the widget.
- Loading, connection-error, retry, invalid-credential, and sign-out states are
  implemented. Metabase's OSS branding is preserved. Available CSV downloads use
  the same locked scope, checked in the integration verification.

This is a controlled-environment prototype. Full identity integration, password
management, brute-force protection, HTTPS, and server-side session revocation
remain future work. Signing out clears the application cookie; an already-issued
BI token remains valid until its short expiry. No production security claim is made.

## Build and run

From the repository root, after BI dashboards are created:

```bash
python3 deploy/hybrid/configure_embed.py
docker compose --env-file .env.hybrid -f docker-compose.hybrid.yml up -d --build --no-deps web
python3 deploy/hybrid/check.py
python3 tests/hybrid_website_20261030/verify.py
```

The Docker build runs TypeScript checks and a production Next.js build. It injects
runtime app settings through Compose; it never copies `.env.hybrid` into the image.
For local development, use Node 22 and `npm ci`, then supply the app environment
variables before `npm run dev`. Stop the web container first to free port 3100.

The browser needs both website port 3100 and Metabase port 3101. SSH-forward both
when accessing this loopback-bound server remotely. `METABASE_PUBLIC_URL` can
set a different browser-reachable Metabase address; its website origin must also
be allowed in Metabase's embedding settings.

[Environment operations](../deploy/hybrid/README.md) ·
[Dashboard definitions](../deploy/hybrid/dashboards/README.md) ·
[Integration verification](../tests/hybrid_website_20261030/README.md)
