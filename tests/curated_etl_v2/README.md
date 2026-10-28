# Integrasi ETL curated v2

Jalankan `python3 tests/curated_etl_v2/run.py --reset-synthetic` dari root repo.
Nama database uji tetap `staging_bkd_etl_v2_test_20261028`; flag reset hanya
menghapus/membuat ulang database sintetis ini. Tanpa flag, runner menolak bila
database sudah ada. Source/raw aktif tidak diubah dan tidak disalin datanya.

Cakupan: populasi tanpa event, aktif/nonaktif/unknown, multi-shift tanpa keyword,
manual, MIN/MAX, no-op dengan pembandingan xmin, koreksi pegawai/tanggal,
penghapusan checkout terakhir, missing raw dan retry, lintas malam unresolved,
izin overlap, pemendekan rentang, pencabutan approval, invalid range, perubahan
status aktif tanpa event, manifest immutable, penolakan snapshot historis,
rollback setelah penulisan event, dan wrapper antrean batch.

`integration_results.txt` berisi keluaran PostgreSQL. `hop_smoke_status.txt`
menunjukkan batch kosong yang diproses pipeline Hop aktual di staging aktif.
Pipeline Hop berhasil dengan E=0; tidak memuat data bisnis pada smoke test.
