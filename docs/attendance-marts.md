# Attendance marts: implementasi dan operasi

Tiga tabel mart fisik sudah aktif dan 20 chart pada empat dashboard Superset telah
dialihkan. View lama tetap tersedia untuk pembandingan dan pemulihan. Tidak ada
koneksi OLTP/database baru di Next.js; SSO tetap ditunda dan akses tetap preview lokal.

## Struktur

| Relasi analytics | Grain | Jumlah baris setelah backfill |
|---|---|---:|
| mart_attendance_department_daily | tanggal × departemen | 825 |
| mart_attendance_composition_daily | tanggal × departemen × status × mode kerja × expected-workday | 2.250 |
| mart_attendance_lateness_daily | tanggal × departemen × lateness bucket, hanya late_days > 0 | 1.425 |
| dashboard_departments | view dimensi departemen untuk opsi filter | 25 |

Nilai KPI dihitung dari SUM pembilang/penyebut. `count` pada dataset komposisi adalah
SUM(employee_days), bukan COUNT baris mart. Dataset lateness mempertahankan SUM(late_days).
Mart komposisi mempertahankan is_expected_workday agar semantik filter chart tetap sama.
Mart ini tidak cocok untuk distinct headcount lintas hari; dataset detail lama tetap ada.

## Alur transaksi ETL

Integrasi dilakukan pada PostgreSQL, sehingga master, incremental, initial-load,
dan pipeline standalone yang menulis fakta pada database yang sama tercakup tanpa
mengubah scheduler maupun duplikasi hook Python:

1. BEFORE STATEMENT memakai advisory lock yang sama dengan pipeline (`718392046`).
   Penulis yang bertabrakan gagal cepat, mengikuti kebijakan lock ETL existing.
2. AFTER STATEMENT dengan transition tables mencatat tanggal OLD dan NEW yang berubah.
   INSERT, UPDATE, DELETE, COPY dan TRUNCATE tercakup. Update nama dimensi menandai
   tanggal historis mart; upsert tanpa perubahan tidak menandai tanggal.
3. Distinct dirty dates dijadwalkan memakai constraint trigger DEFERRABLE INITIALLY
   DEFERRED. Menjelang COMMIT, callback pertama mengolah semua tanggal tersebut;
   bukan menghitung agregasi setiap baris fakta.
4. Fakta tanggal terdampak dibaca sekali ke staging temporer; tiga agregat dihitung
   untuk seluruh departemen pada tanggal tersebut. Tanggal yang menjadi kosong
   ikut dihapus dari mart, sehingga delete/perpindahan tidak meninggalkan baris lama.
5. Validasi employee-days, total keterlambatan, dan komponen KPI dilakukan sebelum
   DELETE/INSERT mart. Unique indexes menjaga grain, termasuk NULL keys.
6. Tiga mart dan `mart_refresh_state` diperbarui dalam transaksi fakta yang sama.
   Jika validasi gagal, COMMIT gagal dan fakta, checkpoints, SUCCESS log dalam
   transaksi tersebut, serta mart ikut rollback. Pipeline dapat mencatat FAILED
   melalui jalur error existing. Mart sebelumnya tetap terbaca.

Pembaca melihat versi lama sampai commit, lalu versi baru. Beberapa request chart
terpisah tetap dapat melintasi batas commit; ini bukan satu snapshot browser global.
Jangan disable trigger untuk maintenance data. Jika dilakukan pemulihan SQL yang
menonaktifkan trigger, wajib backfill ulang sebelum membuka dashboard.
Hak fungsi refresh hanya untuk owner ETL; dashboard_reader hanya diberi SELECT.
Jika akun ETL diganti, tinjau ownership/permission fungsi sebelum menjalankan ETL.

## Cache dan kesegaran

Cache hasil chart/dataset disetel `cache_timeout=-1`. Karena query mart kecil,
pada tahap ini request membaca mart committed langsung, sehingga tidak ada cache
hasil chart lama yang perlu diinvalidasi setelah ETL. Ini menggantikan kebutuhan
invalidation job pada tahap awal. Cache bersama dapat ditambahkan nanti dengan
strategi generation/invalidasi eksplisit. Filter departemen membaca dimensi kecil.

```sql
SELECT * FROM analytics.mart_refresh_state;
SELECT count(*) AS pending_dates FROM analytics.mart_dirty_dates;
```

`refreshed_at` adalah waktu refresh terakhir, `generation` naik setiap refresh yang
committed. `refreshed_dates` dan `source_employee_days` menjelaskan batch refresh
terakhir, bukan total histori. Timestamp tidak naik pada ETL tanpa perubahan.
Pending dates normalnya nol setelah commit sukses. Pantau juga log/timer ETL existing.
Informasi ini tersedia di database monitoring; belum ditambahkan sebagai widget UI.

## Validasi dan performa

- Backfill 33 tanggal dari 2.706.000 fakta; seluruh kolom view agregasi dibandingkan
  dengan mart menggunakan EXCEPT ALL dua arah dan sama.
- 41 query chart/filter dibandingkan sebelum cutover, termasuk semua 20 chart dan
  pemilihan departemen. Seluruh nilai sama (COUNT integer dan SUM numeric dibandingkan
  sebagai nilai, bukan representasi string). Lihat `dashboard-mart-validation.json`.
- Tujuh tes PostgreSQL terisolasi lulus: perubahan tanggal/departemen, delete/truncate,
  rename dimensi, no-op dan coalescing, koreksi nilai, NULL/zero denominators,
  visibility antar-koneksi, kegagalan commit/rollback. Schema uji dibersihkan.
- Suite regresi ETL: 35 test lulus; test opt-in dilewati pada invocation default.
- Satu refresh tanggal (82.000 employee-days pada data ini) sekitar 0,40 detik,
  diukur dalam transaksi yang di-rollback. Backfill/rebuild seluruh histori lebih mahal.

Median browser, detik, tiga pengulangan:

| Dashboard | Initial sebelum → sesudah | Apply filter sebelum → sesudah |
|---|---:|---:|
| overview | 24.62 → 3.86 | 6.27 → 1.94 |
| attendance | 21.23 → 4.13 | 5.28 → 1.46 |
| departments | 7.86 → 3.61 | 2.28 → 0.94 |
| lateness | 20.71 → 3.80 | 5.78 → 1.51 |

Department Performance memakai filter satu hari kerja; tiga halaman lain satu
departemen. Lingkungan tetap development, browser berjalan di server yang sama,
tanpa throttling, dengan readiness 500 ms stabil setelah request terakhir. Hasil
bukan SLA produksi atau pengukuran jaringan pengguna. Cache hasil chart dibypass;
perbaikan bukan berasal dari cache hasil query. Biaya Superset/iframe/assets/render
masih tersisa; tidak semua waktu load adalah SQL. Detail: `dashboard-mart-performance.json`.

## Provision, ulang validasi, dan recovery

Dari root repository (semua command memakai koneksi instance proyek ini):

```bash
.venv/bin/python -m scripts.provision_attendance_marts              # preview
.venv/bin/python -m scripts.provision_attendance_marts --apply       # install + full backfill + validate
.venv/bin/python -m scripts.migrate_superset_marts                  # preview
.venv/bin/python -m scripts.migrate_superset_marts --apply           # stage datasets + compare + cutover
RUN_POSTGRES_TESTS=1 .venv/bin/python -m unittest discover -s tests -p test_attendance_marts_postgres.py -v
```

DDL berada di `sql/dashboard/marts.sql`. View sumber harus sudah disiapkan oleh
provisioner dashboard lama. Provisioner mart idempotent dan memegang lock ETL;
bila ada writer lain, jadwalkan ulang setelah selesai. Jangan jalankan installer
bersamaan dengan ETL. Superset tidak perlu restart untuk perubahan dataset/chart.
Reinit bootstrap Superset mempertahankan dataset lama dan tidak mengubah pointer
chart baru; pada instance baru jalankan provision/migration setelah dashboard dibuat.

Snapshot pertama sebelum cutover berada di `backups/superset-before-marts.json`
(diabaikan Git). Konteks validasi chart baseline lokal disimpan dalam
`deploy/superset/mart-migration-contexts.json`; ID dataset/chart khusus instance ini.
API Superset tidak menyediakan transaksi lintas chart: saat kegagalan cutover,
script berusaha memulihkan snapshot run tersebut. Untuk rollback eksplisit:

```bash
.venv/bin/python -m scripts.migrate_superset_marts --rollback
```

Rollback ini mengembalikan pointer chart/filter sebelum migrasi; tabel mart dan
mekanisme refresh tetap ada, sehingga data/snapshot tidak dibuang. Simpan backup
sebelum memindahkan instance. Untuk merekonsiliasi mart setelah pemulihan eksternal,
jalankan provisioner --apply kembali. Default script hanya preview.

Rujukan perilaku deferred/transition triggers:
https://www.postgresql.org/docs/17/sql-createtrigger.html
Rujukan bypass chart cache:
https://superset.apache.org/docs/configuration/cache/
