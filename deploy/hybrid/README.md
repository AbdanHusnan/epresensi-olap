# Hybrid dashboard environment

Environment-only implementation of [the prototype plan](../../docs/hybrid-dashboard-prototype-plan.md).
The Next.js page is plain HTML; no KPI, metric, chart, dashboard, styling, preview controls,
or embedding-token endpoints are implemented. BI administrator accounts are infrastructure
accounts; application login remains deferred.

## Start

Run from the repository root. Requires Docker Compose, Python 3, and the existing
`epresensi-mart-postgres` container (`mart_bkd`) on `epresensi_mart`.

```bash
python3 deploy/hybrid/configure.py
python3 deploy/hybrid/provision_mart.py
docker compose --env-file .env.hybrid -f docker-compose.hybrid.yml up -d --build --wait --wait-timeout 600
# Wait until Metabase is healthy before initialization:
python3 deploy/hybrid/bootstrap_metabase.py
python3 deploy/hybrid/check.py
```

Secrets are generated in gitignored `.env.hybrid` with mode 0600. The configuration
script preserves existing secrets. Superset initializes its metadata, administrator,
and source automatically. Metabase initialization is safe to rerun and creates only
an administrator and source connection. No sample content is loaded.

## Access

| Service | Browser URL | Administrator |
|---|---|---|
| Next.js | http://localhost:3100 | No login |
| Metabase | http://localhost:3101 | `BI_ADMIN_EMAIL` in `.env.hybrid` |
| Superset | http://localhost:3102 | `admin` |

Both BI administrators use `BI_ADMIN_PASSWORD` in `.env.hybrid`. Read the local file
to retrieve it; credentials are deliberately omitted from documentation and chat.
All ports bind to host loopback. From another machine, forward them over SSH:

```bash
ssh -N -L 3100:127.0.0.1:3100 -L 3101:127.0.0.1:3101 -L 3102:127.0.0.1:3102 USER@SERVER
```

Keep these local port numbers so the configured Metabase site URL remains correct.
Future embedding must distinguish these browser addresses from the Docker names
`http://metabase:3000` and `http://superset:8088`. Dashboard IDs, allowed embedding
origins, scoped credentials, and token renewal belong to the later integration stage.

## Isolation and persistence

Compose project `epresensi-hybrid` has its own containers and metadata volume.
Existing Superset deployments and ETL containers are untouched. Web joins only the
frontend network. BI engines also join `epresensi_mart`; metadata PostgreSQL and Redis
are on a separate internal network with no published ports.

PostgreSQL stores separate `hybrid_metabase` and `hybrid_superset` databases, each with
its own owner/password and PUBLIC database access revoked. Redis is an expendable,
bounded cache for filter/form state; query-result caching is disabled in Superset.
Workers, reports, and alerts are not enabled.

The mart accounts `hybrid_metabase_reader` and `hybrid_superset_reader` have SELECT
on existing relations in `serving` and `mart_kehadiran`, a read-only transaction default,
a 30-second statement timeout, and a 10-connection limit each. Rerun provisioning
after approved new relations are created; it does not change ETL owner defaults or data.
These accounts provide engine-level read access, not department-level isolation;
that must be implemented and tested with future dashboard embedding.

Resource ceilings: web 512 MiB/1 CPU; each BI application 2 GiB/2 CPUs; metadata
768 MiB/1 CPU; Redis 256 MiB/0.5 CPU. The transient Superset initializer also has
2 GiB/2 CPUs. These are prototype guardrails, not benchmark results.

```bash
# Inspect service status or logs
docker compose --env-file .env.hybrid -f docker-compose.hybrid.yml ps
docker compose --env-file .env.hybrid -f docker-compose.hybrid.yml logs --tail=100
# Stop; metadata persists
docker compose --env-file .env.hybrid -f docker-compose.hybrid.yml down
# Backup metadata (contains private account/configuration information)
mkdir -p backups
umask 077
docker compose --env-file .env.hybrid -f docker-compose.hybrid.yml exec -T metadata pg_dumpall -U hybrid_admin > backups/hybrid-metadata.sql
```

Do not use `down -v` unless intentionally deleting prototype metadata. Preserve
`.env.hybrid` securely with backups: Superset needs its existing secret to decrypt
stored source credentials. Credential rotation requires changing stored database
passwords and application settings together; editing the env file alone is insufficient.

## Application development

The production Docker build installs from `package-lock.json`, checks TypeScript,
and builds Next.js standalone. For local development, use Node from `.nvmrc`:

```bash
cd hybrid-dashboard
nvm use
npm ci
npm run dev
```

Stop the web container first if port 3100 is occupied. `npm run typecheck` and
`npm run build` perform the application checks. `/api/health` reports web process
health only; `check.py` checks all environment services.

## Pinned versions and references

Next.js 16.4.3, React 19.3.1, TypeScript 7.0.2, Node 22.22.2,
Metabase OSS 0.64.3, Superset 6.1.0, PostgreSQL 16.14, Redis 7.4.9.
Superset installs explicit PostgreSQL/Redis driver versions in its derived image.

- [Next.js installation](https://nextjs.org/docs/app/getting-started/installation)
- [Metabase Docker and PostgreSQL metadata](https://www.metabase.com/docs/latest/installation-and-operation/running-metabase-on-docker)
- [Metabase sample-content environment settings](https://www.metabase.com/docs/latest/configuring-metabase/environment-variables)
- [Superset releases](https://github.com/apache/superset/releases/tag/6.1.0)
- [Superset cache configuration](https://superset.apache.org/docs/configuration/cache/)

## Verification on 29 October 2026 (Asia/Jakarta)

- Docker build completed, including TypeScript checking and Next.js production build.
- All five long-running containers healthy; Superset initialization exited successfully.
- All three HTTP health endpoints returned 200.
- Both mart reader accounts authenticated, read approved relations with LIMIT 0,
  defaulted to read-only transactions, and had no table-write privileges across the
  nine approved schema relations. No attendance records were modified.
- Metabase and Superset each had one source connection and zero dashboards;
  Metabase had zero questions, and Superset had zero charts.
- Both BI administrator logins succeeded.
- Compose validation, Python compilation, shell syntax, and Git whitespace checks passed.

Data freshness/completeness and dashboard-scope tests remain part of later analytical
implementation; these setup checks do not establish data readiness or department isolation.
