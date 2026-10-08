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

ETL Python lama, generator dummy, tes khusus ETL lama, dan unit schedulernya
sudah dihapus. Gunakan workflow Hop untuk pemrosesan data. Runner backfill dapat
dilanjutkan dengan:

```bash
.venv/bin/python scripts/run_hop_fact.py --detach
```

Jangan menjalankan runner baru bila masih ada proses aktif. Backfill memakai
checkpoint; penyelesaian diperiksa melalui laporan validasi lengkap.

## Dashboard

- [Panduan Superset](deploy/superset/README.md).
- [Mart agregasi](docs/attendance-marts.md).
- [Aplikasi Next.js](attendance-dashboard/README.md).

Utilitas Python dashboard memakai `scripts/dashboard_db.py` dan konfigurasi
`OLAP_*` pada `.env`, terpisah dari pipeline Hop. Jalankan utilitas ini sebagai
modul dari root repository, misalnya `python -m scripts.provision_dashboard`.
