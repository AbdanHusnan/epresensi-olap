# Uji schema mart/serving

Target yang digunakan: epresensi-mart-postgres / mart_bkd, awalnya kosong.
contract.sql memakai fixture sintetis dan BEGIN/ROLLBACK. Hanya jalankan pada
schema kosong atau database uji, karena ID fixture ditentukan eksplisit.

```bash
docker exec -i epresensi-mart-postgres sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d mart_bkd' < tests/mart_serving_20261028/contract.sql
```

verify.sql adalah pemeriksaan read-only yang aman setelah pemuatan; jumlah baris
akan berbeda dari verification.txt jika data bisnis sudah dimuat kemudian.

Dry-run awal menguji DDL dan fixture dalam satu transaksi rollback. apply.txt
mencatat commit DDL, contract_results.txt menguji schema committed. Tidak ada
load bisnis, uji Hop downstream, benchmark, atau cutover dashboard pada tahap ini.
