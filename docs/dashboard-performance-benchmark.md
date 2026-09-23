# Pengujian performa dashboard — 22 September 2026

Kelambatan terkonfirmasi dan agregasi ulang view merupakan faktor utama yang
terukur. Token Next.js bukan bottleneck utama. Mart fisik/pre-agregasi layak menjadi
prioritas, tetapi waktu SQL mart tidak boleh dianggap sebagai waktu load browser.
Tidak ada perubahan permanen pada database, dashboard Superset, atau kode aplikasi
selama pengujian ini.

## Initial load dan applying filter

Tiga pengulangan per halaman; seluruh angka dalam detik. Median dan rentang, bukan
p95. Initial load diukur sejak navigasi hingga seluruh request chart selesai dan
render stabil; apply filter sejak tombol Apply filters diklik hingga selesai.

| Dashboard | Initial median | Initial min–max | Filter median | Filter min–max |
|---|---:|---:|---:|---:|
| overview | 24.62 | 23.73–28.24 | 6.27 | 5.39–6.39 |
| attendance | 21.23 | 19.92–24.55 | 5.28 | 5.14–6.88 |
| departments | 7.86 | 7.58–7.95 | 2.28 | 2.24–2.31 |
| lateness | 20.71 | 20.69–21.86 | 5.78 | 4.76–6.10 |

Filter Overview, Attendance, dan Lateness memakai satu departemen: Badan Pendapatan
Daerah Provinsi Jawa Timur. Department Performance hanya memiliki filter tanggal,
diuji ke satu hari kerja `2026-08-03 <= tanggal < 2026-08-04`; jenis filter dan
jumlah baris berbeda sehingga durasinya tidak dapat dibandingkan sebagai operasi
identik. Pengukuran initial mengikuti konfigurasi dashboard existing: Overview
memiliki rentang waktu per-chart yang tidak seragam; tiga dashboard lain default
Agustus 2026.

Browser pertama memakai context baru, dua pengulangan berikutnya memakai context
yang sama dengan halaman baru. Cache database/server tidak dihapus dan tidak ada
restart untuk simulasi cold database. Browser headless berjalan di server yang sama,
1440×1100, satu pengguna sintetis, tanpa network/CPU throttling. Next.js tetap mode
development. Angka ini bukan SLA produksi dan tidak mencakup latensi SSH/internet
ke komputer pengguna. Benchmark browser dan SQL dijalankan terpisah; tidak ada load
test multiuser. Readiness browser utama mencakup 500 ms periode stabil dan dua
animation frames, sehingga sedikit lebih konservatif daripada request terakhir.

## Di mana waktu terpakai

- Median endpoint token per dashboard hanya 0,246–0,318 detik. Request HTML dasar
  Next.js yang diukur terpisah sekitar 0,065 detik.
- Request chart saat initial mencapai sekitar 24,8 detik pada Overview. Waktu
  tersebut mencakup Superset, pekerjaan database, antrean/concurrency, dan transfer;
  bukan waktu SQL murni. Superset dikonfigurasi 2 worker × 4 thread.
- Warm browser tidak membuat initial load cepat: Overview 23,73 / 24,62 / 28,24
  detik, Attendance 21,23 / 19,92 / 24,55 detik. Asset cache saja tidak cukup.
- Kedua dataset `analytics.attendance_daily` dan
  `analytics.attendance_department_daily` adalah ordinary view (`relkind=v`), bukan
  materialized view. View kedua melakukan GROUP BY tanggal/departemen di atas view
  detail; agregat belum disimpan.
- `fact_kehadiran` berisi 2.706.000 baris dan satu indeks `(pegawai_id, tanggal)`.
  EXPLAIN query aktual menunjukkan sequential scan paralel; misalnya 902.000 baris
  × 3 loop untuk seluruh fakta. Filter tanggal atau departemen tidak otomatis
  menghilangkan kebutuhan memindai fakta tersebut.
- Pengisian dropdown departemen juga membaca dan mengelompokkan view agregasi,
  padahal output hanya 25 opsi. SQL ini sendiri sekitar 1,48 detik.

## Bukti simulasi mart

Dibuat session temporary table dari **definisi view agregasi yang sama**, berisi
825 baris (tanggal × departemen). Pembuatan awal sekitar 2,97 detik, kemudian ANALYZE.
Tabel di-rollback/dibuang setelah pengujian. Tidak ada index tambahan pada mart
sementara. Query chart dihasilkan melalui API Superset `result_type=query`, lalu
EXPLAIN (ANALYZE, BUFFERS) diulang tiga kali secara serial pada PostgreSQL.

| Query aktual | View SQL median | Mart sementara SQL median |
|---|---:|---:|
| Opsi departemen | 1.476,73 ms | 0,415 ms |
| Attendance Rate | 2.204,32 ms | 0,921 ms |
| Attendance Rate, satu departemen | 990,65 ms | 0,168 ms |
| Attendance Trend | 1.657,98 ms | 0,582 ms |
| Attendance Rate by Department | 2.060,17 ms | 1,159 ms |
| Tabel perbandingan empat KPI | 2.473,71 ms | 1,387 ms |
| Lateness Trend | 2.735,79 ms | 1,301 ms |

Sepuluh query yang memakai view agregasi menghasilkan hasil identik antara view
asli dan mart sementara. Rasio KPI tetap SUM(numerator)/SUM(denominator), bukan
rata-rata persentase. Dua sampel dari view detail—WFO/WFH dan distribusi keterlambatan—
masih sekitar 0,40 dan 1,00 detik; tidak diklaim teratasi oleh mart departemen ini.
Chart komposisi/status/bucket memerlukan grain agregasi tambahan atau query yang
memanfaatkan counter yang tepat, dengan validasi kesetaraan semantik.

Ini membuktikan manfaat pre-agregasi pada query yang sesuai. Tidak dilakukan
penggantian dataset atau benchmark browser setelah mart; belum ada angka initial
load pasca-mart. Perbedaan overhead tabel temporer dan mart permanen, caching,
concurrency, dan rendering tetap harus diverifikasi setelah implementasi nyata.

## Prioritas tindak lanjut

1. Sediakan mart tanggal × departemen yang menyimpan numerator/denominator dan
   counter pendukung. Refresh setelah ETL/reconciliation berhasil, termasuk tanggal
   lama yang dikoreksi; tetapkan indikator kesegaran. Materialized view dapat
   digunakan sebagai tahap awal, kemudian incremental mart bila dibutuhkan.
2. Gunakan dimensi/departemen kecil untuk opsi filter dan tambahkan agregat yang
   sesuai untuk komposisi/status/distribusi. Jangan memaksa distinct headcount atau
   detail pegawai ke grain mart yang kehilangan informasi.
3. Evaluasi indeks `(departemen_id, tanggal)` untuk detail terfilter dan indeks
   tanggal menurut selectivity/execution plan. Manfaat indeks belum diuji dalam
   benchmark ini; filter bulan penuh tetap mungkin memilih sequential scan.
4. Audit cache hasil chart Superset dan invalidasinya setelah ETL (misalnya shared
   Redis). Tidak ada konfigurasi cache chart eksplisit pada file Superset repo;
   cache-hit runtime belum dibuktikan oleh hasil guest API. Production build Next.js
   dapat mengurangi overhead development setelah autentikasi produksi siap, namun
   tidak menghapus scan/agregasi PostgreSQL.

Mart/materialized view menyimpan hasil untuk dibaca kembali, berbeda dari view
biasa: [PostgreSQL materialized views](https://www.postgresql.org/docs/17/rules-materializedviews.html).
Cache hasil query merupakan lapisan berbeda dari mart:
[Superset caching](https://superset.apache.org/docs/configuration/cache/).

## Reproduksi dan bukti

Ringkasan angka, seluruh sampel SQL, dan execution plan pertama per query tersedia
pada `dashboard-performance-results.json`. Script hanya menulis hasil benchmark;
SQL comparison menggunakan temporary table dan rollback.

```bash
PLAYWRIGHT_MODULE=/path/to/playwright CHROMIUM_PATH=/path/to/chromium \
  node scripts/benchmark_dashboard_browser.cjs
PLAYWRIGHT_MODULE=/path/to/playwright CHROMIUM_PATH=/path/to/chromium \
  node scripts/benchmark_dashboard_date.cjs
.venv/bin/python -m scripts.benchmark_dashboard_sql
```

Jalankan secara berurutan agar browser dan EXPLAIN tidak saling berebut resource.
Environment ini memerlukan LD_LIBRARY_PATH untuk library Chromium yang disiapkan
sementara di `/tmp/olap-browser-libs/root/usr/lib/x86_64-linux-gnu`. Browser benchmark
menghasilkan `/tmp/olap-dashboard-benchmark.json`; SQL script menggunakannya untuk
menghasilkan SQL dari chart context. Token, kredensial, header, dan data rows tidak
disimpan dalam file benchmark.
