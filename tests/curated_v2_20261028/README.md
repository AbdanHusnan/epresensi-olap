# Validasi schema curated v2

Migrasi dan hasil pemeriksaan ada di
[laporan](../../docs/penyesuaian-curated-staging-20261028.md).
`contract.sql` memuat fixture sintetis ID negatif dan harus dijalankan dalam
transaksi rollback. Tidak ada fixture tersisa setelah pengujian.

```bash
{ printf '\\set ON_ERROR_STOP on\nBEGIN;\n'; cat tests/curated_v2_20261028/contract.sql; printf '\nROLLBACK;\n'; } | docker exec -i epresensi-staging-postgres psql -X -U admin_staging -d staging_bkd
```

SQL migrasi bersifat sekali jalan dan menolak rerun bila schema arsip ada.
Artefak inventaris tidak memuat record pribadi atau kredensial.
