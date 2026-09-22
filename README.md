# ePresensi OLAP ETL

Python ETL for PostgreSQL attendance and leave analytics. Source and warehouse
connections are configured with `OLTP_*` and `OLAP_*` variables in `.env`.

## Dummy 82.000 pegawai — satu bulan

Profil yang disepakati: [Jawa Timur, Agustus 2026](docs/dummy-jatim-202608.md),
25 departemen, 4 pola shift, proporsi WFO tepat waktu/WFH/terlambat/izin/tidak absen
60/10/10/10/10. Generator: `--profile jatim-202608`.

## Initial load requirements

Lihat [requirement dan langkah initial load](docs/initial-load-requirements.md)
untuk kondisi OLTP kosong, pemetaan seluruh dimensi/fakta, dan mode `--check-only`.

## Replace dummy data and run an initial load

See [the initial-load runbook](docs/initial-load.md) for the complete procedure,
backup requirements, exact commands, validation queries, and recovery steps.

The replacement workflow supports 82,000 fictional employees and six months of
attendance through compressed source batches and daily warehouse batches:

- `python -m etl.dummy.generate`: generate reproducible source data.
- `python -m etl.dummy.seed`: preview or replace source records.
- `python -m etl.pipeline.initial_load`: preview or atomically replace warehouse data.

Both database commands default to previews. Writes require `--apply`, the exact
`--confirm-db` name, and a fresh `--backup` path. Source replacement additionally
requires `--all-public-records`, which clears all public source table records;
review the scope in the runbook before using it.

Existing standalone pipelines live in `etl/pipeline/`. Their upserts update or
insert records but do not remove obsolete records from an earlier dataset.

## Phase 10 — Master orchestration

See [the master runbook](docs/master-orchestration.md) for ordered dimension/fact
loading, atomic checkpoints and rollback, reruns, and the daily scheduler.
Preview: `.venv/bin/python -m etl.pipeline.master --recent-days 2`.

## Dashboard analytics / Superset

Instance Superset khusus proyek, akun OLAP read-only, dua dataset dan empat KPI:
lihat [panduan koneksi dashboard](deploy/superset/README.md).
Target KPI dibiarkan kosong sampai kebijakan bisnis tersedia.

## Web app dashboard

Kerangka Next.js berada di [attendance-dashboard](attendance-dashboard/README.md).
Jalankan `npm run dev` dari folder tersebut untuk pratinjau lokal pada port 3002.
