# Validasi pembuatan pipeline tanpa load

Pengguna melarang menjalankan load curated→fact dan seterusnya. Tidak ada fixture
atau eksekusi fungsi delivery/bootstrap pada tahap ini, termasuk rollback load.

- install_definitions.txt: pemasangan DDL kontrol/fungsi, tanpa invocation.
- deploy_metadata.txt: deployment file dan metadata Hop, tanpa engine.
- ValidatePipeline.java / hop_metadata_validation.txt: parser Hop asli memuat
  workflow, dua pipeline, plugin dan koneksi metadata; tidak membuka koneksi DB,
  memanggil getFields, prepareExecution, atau menjalankan engine.
- validate_plans.py / sql_plan_validation.txt: EXPLAIN 16 statement inti terhadap
  temporary relations kosong. Tanpa ANALYZE; INSERT/UPDATE/DELETE hanya direncanakan.
  Temporary relation di-rollback, tabel bisnis tidak disentuh.
- no_load_verification.txt: fact, agregasi, batch, receipt, cursor, date_state nol.
- outbox_inactive_verification.txt: outbox kosong, sequence 0, bootstrap false,
  tidak ada capture trigger pada curated daily.

Pengulangan pemeriksaan SQL tanpa load:

```bash
python3 tests/mart_pipeline_20261028/validate_plans.py
```

Metadata validator dijalankan pada runtime Hop dengan project path dan plugin
folder yang sesuai. Ia tidak menggunakan hop-run. Validasi ini tidak membuktikan
hasil bisnis, rollback/retry runtime, concurrency atau performa; uji integrasi
terisolasi tetap perlu dilakukan setelah diizinkan menjalankan load uji.
