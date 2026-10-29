# STTM Curated ke Mart dan Serving — Kehadiran

Status: **kontrak dikunci 28 Oktober 2026** berdasarkan keputusan pengguna.
Menggantikan baseline regular/nonregular dan expected-workday. Aturan bisnis
mengikuti [STTM source ke curated](sttm-source-to-curated-kehadiran.md).

## 1. Keputusan dan penerapan

- Satu fact seluruh instansi pada grain pegawai × tanggal pelaporan, seluruh shift.
- Satu agregasi utama pada grain tanggal × departemen.
- KPI seluruh instansi, KPI departemen, tren dan perbandingan departemen membaca
  agregasi. ALL = SUM seluruh departemen termasuk UNKNOWN, bukan row tambahan.
- Fact dipakai untuk daftar/detail pegawai, riwayat, dan analisis pegawai-hari.
- Curated menetapkan populasi, atribusi tanggal dan izin. Mart menyalin measure
  yang sudah tersedia di curated; Hop tidak menghitung ulang aturan tersebut.
- Weekend, libur, nama shift dan jumlah shift tidak menyaring populasi/event.

Target fisik: `epresensi-mart-postgres / mart_bkd`. Inspeksi sebelum migrasi
menemukan database tersebut belum memiliki tabel pengguna. Dashboard lama di
`epresensi_analytics.analytics` terpisah dan tidak diganti oleh migrasi ini.

```text
staging_bkd.curated.cur_attendance_daily
  → mart_bkd.mart_kehadiran.fact_kehadiran_daily
  → mart_bkd.serving.agg_kehadiran_departemen_harian
  → serving.v_kehadiran_departemen_harian / v_kehadiran_instansi_harian
```

[DDL migrasi](../sql/mart/20261028_attendance_daily.sql) membentuk schema dan view,
bukan pipeline pemuatan atau cutover dashboard. Pemasangan satu kali memakai
transaksi; objek existing menyebabkan error, tanpa DROP/CASCADE. Hasil penerapan
dan pengujian dicatat di [laporan schema](penyesuaian-mart-serving-20261028.md).

## 2. Dimensi dan pemetaan fact

Dimensi minimum: `dim_calendar`, `dim_pegawai`, `dim_departemen`.
Calendar memakai key YYYYMMDD. Pegawai/departemen memakai surrogate key dan
interval efektif `[valid_from, valid_to)`; NULL valid_to berarti belum berakhir.
DDL menolak interval overlap per ID sumber. Loader wajib mencari tepat satu
versi efektif dan memvalidasi ID sumber dengan surrogate key sebelum menulis fact.
Versi dimensi tidak membuktikan histori sebelum snapshot tersedia. Jangan mengisi
histori dari master sekarang. Nama dimensi boleh belum diketahui.

Mutasi pegawai mengikuti snapshot pada tanggal terkait: perubahan departemen
pada tanggal baru tidak mengubah fact tanggal sebelumnya. Event terlambat tetap
mengikuti departemen snapshot tanggal pelaporannya. Dimensi departemen tidak
menggantikan riwayat penempatan pegawai. Koreksi snapshot historis hanya melalui
revisi eksplisit dan berjejak, bukan efek otomatis perubahan master terkini.

Departemen NULL/tidak terpetakan memakai key 0 (UNKNOWN); ID sumber tetap disimpan
pada fact untuk audit. Pegawai harus mempunyai anggota dimensi dengan ID sumber
terkait, sekalipun nama belum tersedia. Tidak memaksakan satu shift_key harian.

Target: `mart_kehadiran.fact_kehadiran_daily`.
PK: `(pegawai_id_sumber, tanggal)`. Semua key curated disalin, termasuk audit di
luar populasi aktif. Satu pegawai dengan beberapa shift tetap satu fact harian.

| Kolom target | Sumber / aturan |
|---|---|
| `pegawai_id_sumber`, `tanggal`, `departemen_id_sumber` | `pegawai_id`, `tanggal`, `departemen_id` curated |
| `tanggal_key` | Generated YYYYMMDD; tanggal merujuk dim_calendar |
| `pegawai_key`, `departemen_key` | Lookup dimensi efektif; UNKNOWN untuk departemen belum terpetakan |
| `is_employee_active`, `population_basis` | Salin curated; unknown bukan otomatis nonaktif |
| `has_masuk`, `has_pulang` | Salin flag curated |
| `checkin_event_count`, `checkout_event_count` | Jumlah event asli; berbeda dari jumlah pegawai |
| `first_checkin_at`, `last_checkout_at` | Salin timestamp lokal Asia/Jakarta; bukan durasi kerja |
| `has_manual_event` | Salin curated |
| `has_valid_leave`, `has_full_day_leave`, `has_partial_day_leave` | Salin curated |
| `has_excused_checkin`, `has_excused_checkout` | Salin hasil pengecualian izin curated |
| 12 measure bagian 3 | Salin generated measure curated sebagai nilai; CHECK memeriksa konsistensi |
| `perlu_review`, `alasan_review`, `is_date_final`, `date_assignment_policy` | Salin curated; mart tidak finalisasi sendiri |
| `source_snapshot_at`, `source_batch_id` | Snapshot dan batch downstream yang membawa hasil curated |
| `contract_version`, `mart_loaded_at` | ATTENDANCE_DAILY_V1 dan waktu load |

Pegawai populasi tanpa event tetap mempunyai fact. Nonaktif/unknown memiliki
measure KPI nol. Dua shift dengan 2 masuk/2 pulang tetap measure masuk/pulang 1/1.
Detail event, shift dan pengajuan izin ditelusuri di curated melalui pegawai/tanggal;
event unresolved juga perlu ditelusuri melalui tanggal kalendernya.

## 3. KPI dan measure terbaru

Kondisi berikut berlaku pada satu pegawai-hari. A = aktif, M = ada masuk,
P = ada pulang, I = izin valid, EM/EP = dibebaskan masuk/pulang.

| Measure | Kondisi bernilai 1 | Label / penggunaan |
|---|---|---|
| `active_employee_days` | A | Pegawai Aktif |
| `checkin_days` | A AND M | Absen Masuk |
| `checkout_days` | A AND P | Absen Pulang |
| `no_checkin_days` | A AND NOT EM AND NOT M | Tidak Absen Masuk |
| `no_checkout_days` | A AND NOT EP AND NOT P | Tidak Absen Pulang |
| `leave_days` | A AND I | Pegawai Izin |
| `required_checkin_days` | A AND NOT EM | Wajib Masuk setelah Izin |
| `required_checkout_days` | A AND NOT EP | Wajib Pulang setelah Izin |
| `excused_checkin_days` | A AND EM | Bebas Masuk |
| `excused_checkout_days` | A AND EP | Bebas Pulang |
| `required_checkin_present_days` | A AND NOT EM AND M | Pemenuhan Wajib Masuk |
| `required_checkout_present_days` | A AND NOT EP AND P | Pemenuhan Wajib Pulang |

Enam baris pertama menjadi kartu utama. Tanggal berjalan dapat memakai label
Belum Absen Masuk/Pulang. Kewajiban adalah aturan dashboard setelah izin,
bukan bukti roster atau pelanggaran disiplin. Akhir pekan/libur tidak mengurangi
populasi. Tipe transaksi izin 1 membebaskan kedua sisi, 2 masuk, 3 pulang.
Overlap memakai hasil BOOL_OR curated, bukan penjumlahan pengajuan.

| Kolom persentase view | Rumus dikalikan 100.0 |
|---|---|
| `checkin_rate` | SUM(checkin_days) / SUM(active_employee_days) |
| `checkout_rate` | SUM(checkout_days) / SUM(active_employee_days) |
| `required_checkin_rate` | SUM(required_checkin_present_days) / SUM(required_checkin_days) |
| `required_checkout_rate` | SUM(required_checkout_present_days) / SUM(required_checkout_days) |

Denominator nol menghasilkan NULL (UI: —). Event saat izin penuh tetap masuk
bukti event tetapi tidak pembilang pemenuhan kewajiban. Izin dan event beririsan;
jangan menjadikannya partisi pie yang harus menjumlah ke populasi aktif.
Tidak memakai scheduled_regular_days, absent_days/TANPA_KETERANGAN, atau
attendance_rate berbasis workday. Keterlambatan, durasi kerja, WFO/WFH, komposisi
jenis izin ditunda sampai kontrak tersedia; overlap jenis izin perlu MULTIPLE
atau prioritas eksplisit.

## 4. Agregasi dan akses dashboard

`serving.agg_kehadiran_departemen_harian`: PK `(tanggal, departemen_key)`;
tanggal_key generated, UNIQUE `(tanggal_key, departemen_key)`.
Sumber hanya fact, GROUP BY tanggal dan departemen_key. Seluruh 12 measure
memakai SUM dan tipe bigint. Tidak join detail event/pengajuan izin.

| Kolom tambahan | Aturan |
|---|---|
| `fact_rows` | COUNT semua fact termasuk audit; bukan headcount aktif |
| `review_rows` | COUNT fact perlu_review |
| `nonfinal_rows` | COUNT fact NOT is_date_final |
| `is_provisional` | Generated: ada review/nonfinal; view menambahkan pemeriksaan state tanggal |
| `serving_batch_id`, `refreshed_at` | Batch publikasi dan waktu rebuild partisi |

`v_kehadiran_departemen_harian` menyediakan measure, rate, nama departemen, dan
status kualitas. `v_kehadiran_instansi_harian` menjumlah semua departemen per
tanggal sebelum menghitung rate. View instansi memuat waktu refresh partisi
tertua/terbaru; MAX waktu saja tidak membuktikan seluruh data sudah segar.
`v_departemen_filter` menghasilkan satu pilihan per ID departemen sumber dengan
nama versi terbaru, termasuk UNKNOWN. Filter ID sumber mencakup semua versi
surrogate key yang relevan pada periode.

`serving.attendance_date_state` menyimpan per tanggal: `population_complete`,
`curated_delivery_complete`, `is_closed`, `published_batch_id`, `updated_at`.
Flag default false; hanya orchestrator setelah validasi cakupan yang mengubahnya.
Close memerlukan kedua kelengkapan true. State hilang dianggap tidak lengkap/
provisional. State lengkap tidak meniadakan review/nonfinal pada fact.
Tanggal tanpa row agregasi harus diperiksa melalui calendar/date_state: data
belum tersedia berbeda dari populasi nol. Tidak boleh COALESCE semua kasus ke nol.

Pada satu tanggal, measure adalah jumlah pegawai; SUM lintas tanggal adalah
pegawai-hari. Pegawai unik lintas periode membutuhkan COUNT DISTINCT dari fact.
Rate periode = SUM pembilang / SUM penyebut, bukan AVG rate harian/departemen.
Belum ada agregasi bulanan fisik. Indeks mendukung tanggal/departemen dan detail.
Partisi/cache ditambahkan berdasarkan benchmark, retensi, dan volume aktual.
Agregasi ini tidak mendukung filter atribut lain tanpa grain tambahan.

## 5. Kontrak incremental berikutnya

Schema bukan implementasi pipeline. Raw→curated tetap memakai kontraknya.
`cv2_affected` tetap temporary. Definisi outbox terpisah menangkap perubahan
curated daily pada transaksi yang sama, setelah bootstrap diaktifkan: batch/version, key pegawai-tanggal,
operasi UPSERT/DELETE dan payload konsisten. Payload mewakili versi batch, bukan
row yang mungkin sudah diubah batch berikutnya. Sertakan key lama dan baru.

Consumer memproses versi berurutan dan idempotent. Dalam satu transaksi mart:

1. Periksa batch belum APPLIED, muat dimensi dan payload tervalidasi.
2. Simpan tanggal/departemen lama dari fact sebelum upsert/delete.
3. Sinkronkan fact; row curated yang benar-benar hilang menghasilkan delete.
4. Gabungkan partisi lama/baru; rebuild dari semua fact pada partisi terdampak.
   Hapus agregasi jika partisinya kosong; jangan menambah/mengurangi delta manual.
5. Perbarui date_state jika ada bukti cakupan, checkpoint batch, lalu commit.

Retry tidak menggandakan angka. No-op tidak menulis ulang hasil bisnis.
Staging dan mart berbeda database: gunakan durable delivery/checkpoint per tahap,
bukan satu transaksi raw sampai serving. `etl_control.mart_batch` disiapkan
untuk checkpoint target; APPLIED hanya ditulis bersama commit fact/agregasi.
Definisi outbox, consumer dan refresh agregasi kini tersedia melalui migrasi
ETL terpisah; workflow belum dijalankan dan bootstrap/capture belum diaktifkan.
Lihat [panduan pipeline](../hop/MART_PIPELINE.md).
Initial load memerlukan snapshot konsisten dan batas batch agar perubahan selama
pemuatan tidak hilang. Histori populasi tidak dibuat dari master sekarang.

## 6. Validasi dan finalisasi

```text
aktif = wajib_masuk + bebas_masuk
aktif = wajib_pulang + bebas_pulang
wajib_masuk = pemenuhan_masuk + tidak_masuk
wajib_pulang = pemenuhan_pulang + tidak_pulang
0 <= izin <= aktif
SUM(departemen termasuk UNKNOWN) = ALL
```

Uji schema: grain, FK, interval dimensi, formula measure, denominator nol,
UNKNOWN dan rate instansi. Uji pipeline berikutnya: dua shift, batch terpisah,
overlap/pencabutan izin, koreksi tanggal/pegawai/departemen, delete, no-op,
rollback/retry, perubahan status snapshot, serta rekonsiliasi kecil/bulk ke serving.

Curated saat ini masih is_date_final=false. Tidak menetapkan close 02:00 otomatis.
Atribusi lintas malam, kelengkapan populasi/delivery dan kebijakan close harus
selesai sebelum final. Koreksi tanggal tertutup memerlukan revisi berjejak;
refresh master tidak menimpa histori diam-diam. Cutover dashboard dan benchmark
concurrency adalah tahap lanjutan, bukan bukti yang diberikan oleh uji schema.

## 7. Status pembuatan pipeline

Workflow `curated_to_serving.hwf` dan dua child pipeline telah dipasang pada
proyek Hop epresensi-staging, tanpa menjalankan load. Apply dan ack dipisahkan
oleh batas penyelesaian pipeline; receipt mart diperiksa melalui koneksi baru
sebelum staging ditandai delivered. Ini diperlukan karena TableInput menahan
transaksi query hingga koneksi ditutup.

Bootstrap explicit satu kali mengambil snapshot per tanggal dan memasang capture
atomik. Sebelum aktivasi, tidak ada capture trigger atau batch outbox sehingga
ETL curated existing tidak berubah. Dimensi yang belum tersedia dibuat sebagai
placeholder ID tanpa nama, memakai interval efektif yang tidak overlap; tidak
mengambil master terbaru untuk mengarang histori. Bukti kelengkapan/finalisasi
belum disertakan dalam delivery, maka tanggal terdampak tetap provisional.

Bukti: [validasi tanpa load](../tests/mart_pipeline_20261028/README.md).
Saat pembuatan 28 Oktober, uji integrasi data dan benchmark belum dijalankan.
Pada 29 Oktober, uji kecil terisolasi sudah lulus dengan 12 sampel bulk, termasuk
snapshot mutasi antar-tanggal, event terlambat, incremental, no-op, rollback/retry,
immutable payload, UNKNOWN/nonaktif dan delete. Lihat
[laporan uji kecil](../tests/mart_small_20261029/README.md).
Bulk 2.400 baris curated existing juga telah dijalankan hingga 2.400 fact dan
757 agregasi tanggal-departemen, tanpa skenario baru; seluruhnya cocok. Lihat
[laporan bulk downstream](../tests/mart_bulk_20261029/README.md).
Target aktif tetap belum dimuat; benchmark histori besar/concurrency belum dilakukan.
