# ePresensi OLAP — Apache Hop

Pipeline dimensi dan fakta presensi menggunakan Apache Hop dengan PostgreSQL.
Sumber aktif: `dbabsen_restore`; target pengembangan: `epresensi_analytics_hop_dev`.

## Acuan dan operasi

- [Kesepakatan mapping presensi](docs/kesepakatan-mapping-presensi-hop.md): aturan bisnis, grain, transformasi, dan keputusan review.
- [Panduan Apache Hop](hop/README.md): konfigurasi, pipeline dimensi, backfill fakta, dan resume checkpoint.
- [Mapping kolom](docs/oltp-mapping-review.csv) dan [inventaris sumber](docs/oltp-columns-hop.md).
- [Relasi sumber](docs/oltp-erd-hop.md).

Folder `hop/` berisi project, metadata koneksi, pipeline, dan workflow.
SQL transformasi berada di `sql/hop/`; skrip setup, audit, dan validasi berada di
`scripts/`. Laporan hasil eksekusi disimpan di `logs/reports/` dan log runner di
`logs/hop-fact/`, keduanya diabaikan Git. Kredensial lokal tidak disimpan dalam
repository.

Pipeline dan workflow fakta buatan sebelumnya beserta runner backfill telah dihapus
atas permintaan pengguna pada 9 Oktober 2026. Pipeline dimensi tetap tersedia;
pipeline fakta akan dibuat sendiri oleh pengguna melalui Apache Hop. SQL pendukung,
data database, checkpoint, dan laporan lama dipertahankan sebagai referensi.

## Hybrid dashboard

- [Environment setup and operations](deploy/hybrid/README.md).
- [Infrastructure and prototype plan](docs/hybrid-dashboard-prototype-plan.md).
- [Next.js application](hybrid-dashboard/README.md).

The hybrid project currently contains environment setup only. Start it with
`docker-compose.hybrid.yml`; the older `docker-compose.dashboard.yml` belongs to the
separate legacy Superset deployment.
