# Data Lineage Dashboard KPI E-Presensi

> **Pembaruan ETL 28 Oktober 2026:** pipeline Hop dan fungsi incremental raw ke
> curated sudah dipasang dan diuji. Data bisnis belum dimuat; producer raw masih
> perlu mengirim manifest ID berubah. Lintas malam tetap provisional/unresolved.
> Petunjuk dan batas implementasi ada di [panduan ETL](../hop/README.md).

> **Status fisik 28 Oktober 2026:** schema curated baru sudah dibuat di
> `staging_bkd` dan masih kosong; data lama berada di `curated_legacy_20261028`.
> ETL sudah dipasang; pengisian ulang data bisnis belum dijalankan. Lihat
> [hasil pemeriksaan dan migrasi](penyesuaian-curated-staging-20261028.md).

Status: **revisi rancangan 28 Oktober 2026**, berdasarkan konfirmasi pengguna
mengenai penggunaan database aplikasi sebelumnya. Menggantikan rancangan berbasis
keyword regular/reguler. Kontrak, schema dan pipeline curated telah diperbarui; data bisnis belum dimuat.
Aturan atribusi tanggal lintas malam belum final.

## 1. Keputusan rancangan

1. Database aplikasi diterima apa adanya. Tidak mengubah nama/status shift,
   master, relasi, atau transaksi agar cocok dengan kebutuhan analitik. Raw
   menyimpan nilai asli beserta metadata ekstraksi.
2. Keyword regular/reguler tidak membuktikan kewajiban hadir. Banyak departemen
   memiliki shift tanpa keyword tersebut. Tidak ada pencarian shift reguler,
   aktivasi shift, atau fallback ke departemen induk untuk membentuk populasi.
3. Workday pegawai tidak dapat ditentukan dari bukti yang tersedia. Populasi
   dashboard adalah **seluruh pegawai aktif**, termasuk yang tidak memiliki
   jadwal atau event. Kalender, libur, dan izin tidak mengurangi denominator.
4. Grain utama adalah **pegawai × tanggal pelaporan**. Beberapa shift pada
   tanggal sama tetap satu pegawai. Jam masuk aktual adalah check-in paling
   awal; jam pulang aktual adalah check-out paling akhir dari seluruh shift.
5. Pisahkan **Tidak Absen Masuk** dan **Tidak Absen Pulang**. Izin adalah metrik
   tersendiri yang dapat beririsan dengan metrik event maupun ketiadaan event.
6. Satu logical `mart_kehadiran` berisi dimensi/fakta. Dashboard hanya membaca
   agregasi schema `serving`.

## 2. Filter, populasi, dan waktu

| Kontrak | Aturan |
|---|---|
| Tanggal | `tanggal = :tanggal`; tanggal pelaporan mengikuti aturan atribusi di bawah. |
| Departemen | Filter ID, bukan nama; ALL mencakup seluruh populasi. |
| Departemen KPI | Usulan: departemen snapshot pegawai yang digunakan untuk populasi. Departemen transaksi dipertahankan untuk audit. Satu pegawai-hari mendapat satu departemen KPI. |
| Aktif | Mapping kode `m_pegawai.status` harus diverifikasi terhadap aplikasi; tidak menebak kode aktif. |
| Histori | Snapshot status/departemen sekarang tidak membuktikan status historis. Backfill tanpa snapshot tanggal terkait harus diberi label basis populasi saat ekstraksi. |
| Finalisasi | Tanggal berjalan berlabel provisional; belum pulang bukan kesimpulan tidak hadir sepanjang hari. |

Simpan tanggal kalender event dalam konteks Asia/Jakarta terpisah dari tanggal
pelaporan. Untuk event same-day, keduanya sama.

**Arah lintas malam dari pengguna:** check-out terkait hari check-in. Namun ini
masih arah logis, belum konfirmasi perilaku aplikasi lama. Algoritme pasangan,
batas durasi, checkout tanpa pasangan, dan waktu penutupan hari perlu ditetapkan
sebelum implementasi final. Jangan menggeser semua checkout ke D-1. Jangan
mensyaratkan ID jadwal masuk/pulang sama; audit menemukan jadwal harian berbeda.
Event ambigu tetap tersimpan dengan status atribusi belum terselesaikan, tidak
hilang atau dihitung pada dua tanggal. Tanggal terdampak belum boleh disebut final.

## 3. Sumber dan lineage

| Sumber | Peran |
|---|---|
| `m_pegawai`, `m_departemen` | Populasi pegawai aktif dan organisasi pelaporan. |
| `t_checkinout` | Bukti event: `checktype=1` masuk, `checktype=2` pulang; timestamp aktual `created_at`. |
| `m_jadwal`, `m_shift` | Lookup konteks melalui `jadwal_id → m_jadwal.id → m_jadwal.jenis → m_shift.id`; bandingkan `work_code` untuk audit. Bukan filter populasi/event. |
| `t_perizinan`, `m_user`, `m_jenis_ijin`, `m_tipe_ijin` | Identitas, approval, rentang dan jenis izin. |
| `m_hari_libur`, `t_libur_shift` | Konteks kalender, bukan pengurang populasi aktif. |

Alur: **sumber → raw → curated → mart_kehadiran → serving → dashboard**.

| Objek target | Grain | Fungsi |
|---|---|---|
| `raw_*` | 1:1 sumber | Nilai asli, PK, timestamp sumber dan ekstraksi. |
| `cur_employee_population_daily` | pegawai × tanggal | Status aktif, departemen, basis snapshot. |
| `cur_event_attendance` | satu event | Semua event dan lookup konteks, termasuk referensi kosong/tidak cocok. |
| `cur_attendance_event_daily` | pegawai × tanggal | Semua shift, flag masuk/pulang, jumlah event, masuk pertama/pulang terakhir. |
| `cur_leave_daily` | pegawai × tanggal izin × pengajuan | Ekspansi rentang izin dan validasi. |
| `cur_attendance_daily` | pegawai × tanggal | Join populasi dengan event dan izin yang telah diringkas per pegawai-hari. |
| `mart_kehadiran.fact_kehadiran_daily` | pegawai × tanggal | Salin kontrak curated dan bentuk measure 0/1. |
| `serving.agg_kehadiran_departemen_harian` | tanggal × departemen | Agregasi metrik populasi, event dan izin. |
| `serving.v_departemen_filter` | satu ID departemen | Opsi filter. |

Dimensi pegawai, departemen, kalender dan jenis izin tetap relevan. Referensi
shift disimpan pada detail event; jangan memaksakan satu shift untuk satu fakta
harian yang memuat beberapa shift. Pemisahan regular/non-regular tidak diperlukan
untuk KPI utama.

## 4. Definisi KPI

Misalkan `A` adalah pegawai aktif pada basis snapshot, `M` memiliki check-in,
`P` memiliki check-out, dan `I` memiliki setidaknya satu izin approved valid.
Semua flag dievaluasi pada pegawai-hari yang sama dan dikonversi menjadi 0/1.

| KPI | Measure per pegawai-hari | Agregasi |
|---|---|---|
| Pegawai Aktif | `active_employee_days = A` | SUM |
| Absen Masuk | `checkin_days = A AND M` | SUM |
| Tidak Absen Masuk | `no_checkin_days = A AND NOT M` | SUM |
| Absen Pulang | `checkout_days = A AND P` | SUM |
| Tidak Absen Pulang | `no_checkout_days = A AND NOT P` | SUM |
| Pegawai Izin | `leave_days = A AND I` | SUM; banyak pengajuan tetap satu orang. |
| Persentase Absen Masuk | — | `100.0 * SUM(checkin_days) / NULLIF(SUM(active_employee_days),0)` |
| Persentase Absen Pulang | — | `100.0 * SUM(checkout_days) / NULLIF(SUM(active_employee_days),0)` |

Persentase adalah proporsi populasi aktif dengan event, bukan kepatuhan jadwal.
Pegawai izin tanpa event tetap tercatat pada Tidak Absen Masuk dan Tidak Absen
Pulang serta Pegawai Izin. Izin penuh/parsial dapat dirinci tanpa menggandakan
total pegawai izin. Kategori izin dan event tidak saling eksklusif.

Event pegawai nonaktif/tidak ditemukan tetap disimpan untuk audit, tetapi tidak
masuk pembilang KPI populasi aktif. Kelengkapan presensi, keyword shift, atau
review referensi jadwal tidak menjadi syarat check-in/out jika identitas dan
tanggal pelaporannya jelas. Event manual tetap menjadi bukti event.

KPI Wajib Hadir, Tanpa Keterangan, dan kepatuhan jadwal ditarik dari kontrak utama
karena kewajiban individual tidak dapat dibuktikan. Tidak Absen Masuk/Pulang
bukan status pelanggaran disiplin. Keterlambatan dan WFO/WFH memerlukan kontrak
lanjutan mengenai pemilihan konteks event sebelum digunakan.

## 5. Contoh dan pemeriksaan

Seluruh contoh memakai pegawai aktif dan tanggal pelaporan yang telah ditentukan.

| Kondisi | Masuk | Tidak masuk | Pulang | Tidak pulang | Izin |
|---|---:|---:|---:|---:|---:|
| Tanpa event/izin | 0 | 1 | 0 | 1 | 0 |
| Check-in saja | 1 | 0 | 0 | 1 | 0 |
| Check-out saja | 0 | 1 | 1 | 0 | 0 |
| Dua shift, keduanya masuk/pulang | 1 | 0 | 1 | 0 | 0 |
| Izin tanpa event | 0 | 1 | 0 | 1 | 1 |
| Izin dengan masuk/pulang | 1 | 0 | 1 | 0 | 1 |

Masuk 07.00 dan 14.00, pulang 14.05 dan 21.00 menghasilkan masuk harian 07.00
dan pulang harian 21.00. Tetap satu pegawai; rentang ini bukan otomatis durasi
kerja sah atau bukti satu sesi.

Untuk setiap tanggal-departemen:

```text
active_employee_days = checkin_days + no_checkin_days
active_employee_days = checkout_days + no_checkout_days
0 <= leave_days <= active_employee_days
```

Total departemen harus cocok dengan ALL. Departemen kosong/tidak cocok harus
tertampung sebagai belum terpetakan, bukan hilang melalui join. Jangan memakai
rumus lama `expected = present + leave + absent` pada model yang beririsan ini.

## 6. Penerapan dan keputusan tersisa

1. Gunakan revisi ini dan [STTM source ke curated](sttm-source-to-curated-kehadiran.md)
   sebagai kontrak baru; pipeline lama menjadi baseline pembanding.
2. Verifikasi kode status aktif, basis populasi historis, serta departemen filter.
3. Konfirmasikan lintas malam, pasangan ambigu, dan penutupan tanggal.
4. Revisi STTM curated ke mart/serving dan transformasi Hop agar tidak memakai
   keyword shift, workday, atau pemisahan regular/non-regular untuk KPI utama.
5. Bangun target analitik terpisah tanpa mengubah database aplikasi. Jangan
   rename/drop objek lama sebelum memeriksa dependensi.
6. Uji departemen tanpa shift reguler, dua shift, event berulang, masuk/pulang
   saja, izin, nonaktif, lookup gagal, dan lintas malam. Rekonsiliasi per tanggal
   serta departemen terhadap aplikasi lama, dengan penjelasan setiap selisih.
7. Cutover dashboard setelah kontrak tanggal dan validasi selesai.

Bukti sebelumnya: [review shift](review-penentuan-shift-20261027.md) dan
[audit dua shift/lintas malam](audit-dua-shift-dan-lintas-malam-20261027.md).
Usulan sesi pada audit tidak mengganti grain KPI pegawai-hari yang dikonfirmasi.
