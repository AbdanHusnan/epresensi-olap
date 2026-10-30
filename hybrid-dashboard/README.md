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
Dimension name loading is deferred. Test date defaults to 30 October 2026. The current dataset contains 72,259 real
source employees with tagged simulated transactions loaded through the full Hop
pipeline; see [source-to-dashboard evidence](../tests/source_to_dashboard_20261030/README.md).

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
