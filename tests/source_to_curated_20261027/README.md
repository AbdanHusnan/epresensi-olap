# Pilot source → raw → curated, 27 Oktober 2026

Sumber: `epresensi-olap-postgres / dbabsen_restore`.
Target terisolasi: `epresensi-staging-postgres / staging_bkd_test_20261027`.
Tanggal bisnis/snapshot: **2026-10-27**, Selasa, Asia/Jakarta.
`snapshot_at` dan `extracted_at` mencatat waktu pengambilan sebenarnya; tidak
memalsukan jam server atau menganggap master dump sebagai histori master live.

## Cara menjalankan

Dari root repository, dengan akses Docker:

```bash
python3 tests/source_to_curated_20261027/run.py
python3 tests/source_to_curated_20261027/verify_snapshot.py
python3 tests/source_to_curated_20261027/replay.py
```

`run.py` hanya untuk inisialisasi: berhenti jika database tes sudah ada, agar
snapshot/bukti lama tidak tertimpa. Setelah pilot selesai, gunakan `replay.py`.
Jika inisialisasi gagal, periksa tahap dan data existing sebelum melanjutkan;
runner tidak menghapus database atau mereset fixture secara otomatis.
Tidak memerlukan kredensial di file: psql dijalankan melalui container.

## Cakupan dan alur

1. Salin struktur raw/curated existing ke database tes.
2. Salin master asli tanpa mengubah nilai bisnis. Seluruh pegawai, departemen,
   shift, jadwal, hari libur, kategori pegawai, dan referensi izin disalin;
   izin/libur individual dibatasi yang mencakup tanggal tes. Raw user hanya ID
   dan pegawai_id sesuai kontrak raw existing. Hash binary kolom bisnis merekam
   isi sumber dan diverifikasi ulang terhadap raw. Data pribadi tidak diekspor
   ke file lokal; laporan hanya memuat hitungan, hash, dan ID fixture.
3. Bekukan raw master untuk seluruh siklus. Pengambilan tabel dilakukan berurutan
   pada dump statis, bukan snapshot transaksi global untuk sumber live yang berubah.
4. Bentuk workday seluruh master pegawai, satu pegawai × tanggal. Kategori
   PNS/PTT/PPPK/PPPK Paruh Waktu aktif; Non-Aktif tidak aktif; kode tak dikenal
   tetap NULL. Jadwal Tue dengan shift aktif bernama regular/reguler menentukan
   alternatif; jumlah alternatif tidak menggandakan denominator. Weekend,
   libur global, dan libur individual mengecualikan kewajiban.
5. Pilih dua pegawai wajib kerja tanpa izin hari tes. Jadwal fixture harus
   reguler, tidak fleksibel, dan tidak lintas tengah malam. Satu pegawai mendapat
   masuk/pulang; satu menjadi kontrol tanpa event. Pemilihan jadwal fixture
   adalah pilihan transaksi uji, bukan penghapusan alternatif dari workday.
6. Baseline tanpa event uji → masuk lima menit sebelum jam master → pulang lima
   menit sesudah jam master → rerun → koreksi masuk menjadi terlambat 10 menit
   → kegagalan curated setelah raw commit → retry → penutupan hari simulasi.

Dua transaksi benar-benar dibuat dalam `public.t_checkinout` sumber, memakai
sequence sumber dan ID master asli. Tabel `test_e2e_20261027.events` merekam ID
fixture secara atomik bersama insert; master dan event existing tidak diubah.
Fixture dipertahankan untuk inspeksi. Tidak ada cleanup otomatis.

## Waktu dan incremental

`created_at` adalah waktu event simulasi. `updated_at` fixture diisi waktu nyata
Asia/Jakarta pada insert/koreksi. Batas atas batch adalah waktu ekstraksi sumber;
filter menggunakan updated_at, dengan overlap satu detik dan upsert ID. Event
checkout boleh berada di masa depan relatif terhadap jam proses.

Ekstraksi hanya mencakup ID dalam manifest sumber, bukan seluruh histori.
Ini menguji perubahan, replay, dan koreksi pada dataset terkontrol; **belum
mensertifikasi incremental produksi**. Aplikasi live harus terbukti mengisi
updated_at. Commit terlambat, delete, NULL timestamp, konkurensi, dan kebutuhan
CDC masih perlu desain tersendiri. Checkpoint raw diperbarui bersama commit raw;
curated dibangun ulang dari raw dalam transaksi terpisah. Kegagalan curated tidak
menghapus raw, dan retry tidak membutuhkan pembacaan ulang event dari awal.

`test_control.run.day_closed=false` menjaga baseline tanpa event sebagai status
NULL. Setelah true, pegawai wajib tanpa event/izin menjadi TANPA_KETERANGAN.
Boolean ini adalah simulasi penutupan hari untuk pilot; parameter waktu evaluasi
umum belum diimplementasikan. Snapshot master tidak disegarkan saat replay.

## Artefak dan validasi

- `run.py`: orkestrasi pilot, fixture, ekstraksi, assertions, laporan.
- `workday.sql`: pembentukan workday dari raw master beku.
- `transform.sql`: event, ringkasan reguler/nonreguler, izin, dan hasil harian.
- `schema_reference.sql`: struktur raw/curated dari staging, tanpa data.
- `pipeline_reference/`: salinan pipeline Hop existing sebagai referensi.
- `manifest.json`, `results.json`: cakupan, fixture, hasil tiap tahap.
- `verify_snapshot.py`, `snapshot_validation.json`: kecocokan atribut master.
- `replay.py`, `replay_results.json`: rerun tanpa perubahan nilai bisnis.

Assertion meliputi kesamaan semua atribut source/raw fixture (termasuk NULL),
jumlah event raw/curated, workday sebanyak pegawai, keunikan melalui PK, hasil
status/jumlah event/keterlambatan, fingerprint daily stabil saat rerun, serta
rollback curated pada kegagalan sebelum commit. Timestamp ekstraksi dapat
berubah pada replay; timestamp snapshot dan nilai bisnis tetap.

## Batas implementasi

Pilot SQL berjalan langsung melalui psql. Pipeline curated Hop yang ditemukan
masih scaffold `SELECT 1 ... WHERE FALSE`; salinannya tidak dieksekusi dan tidak
mengubah pipeline aktif. Integrasi transformasi ke Hop adalah pekerjaan lanjutan.

Pilot memuat semua workday tetapi event hanya dua fixture, sehingga status
harian dalam database ini adalah hasil simulasi, bukan laporan presensi nyata.
Kelengkapan kalender libur dari dump tidak disertifikasi sebagai kalender live.

Transformasi terbatas pada tanggal pilot dan kasus reguler sederhana. Pairing
lintas tengah malam, event di luar master, koreksi pindah pegawai/tanggal,
propagasi semua alasan review izin, dan validasi referensi lengkap belum menjadi
cakupan kelulusan. Untuk kasus tersebut jangan gunakan SQL pilot sebagai ETL
produksi. Jam masuk/pulang dibuat dalam menit utuh; aturan pembulatan pecahan
menit masih perlu ditetapkan.

## Open question: backfill

Backfill ditunda sesuai keputusan pengguna. Kelanjutan di server live, cakupan
periode, dan ketersediaan histori master masih terbuka. Master dump hari ini
tidak dipakai untuk menyatakan kewajiban kerja historis.

## Audit denominator workday

Jalankan pemeriksaan read-only:

```bash
docker exec -i epresensi-staging-postgres psql -X -v ON_ERROR_STOP=1 \
  -U admin_staging -d staging_bkd_test_20261027 \
  < tests/source_to_curated_20261027/audit_workday.sql
```

Hasil audit: 125.832 pegawai = 43.713 nonaktif + 82.119 aktif.
Pegawai aktif = 16.692 wajib menurut aturan pilot + 1 libur individual +
65.426 tanpa kandidat reguler. Kelompok terakhir terdiri dari 44.805 pegawai
pada departemen dengan shift regular/reguler hanya nonaktif, 16.837 pada
departemen tanpa nama shift regular/reguler, dan 3.784 pada departemen tanpa shift.

Angka 16.692 membuktikan keluaran aturan teknis pilot, bukan validasi jumlah
kewajiban hadir organisasi. Nama shift non-reguler secara regex belum membuktikan
bahwa shift tersebut bukan jadwal wajib. Relasi jadwal melalui departemen induk
juga belum ditetapkan; pilot menggunakan kecocokan departemen langsung.
Klasifikasi bisnis dan kondisi master dump perlu direview sebelum memakai angka
ini sebagai denominator produksi. Tidak ada perubahan aturan atau data pada audit.

## Revisi 1: aktivasi reguler atas instruksi pengguna

Atas instruksi berikutnya, 4.121 shift bernama regular/reguler yang statusnya
false di `dbabsen_restore.public.m_shift` diaktifkan. Audit sebelum perubahan
tersimpan di `dbabsen_restore.test_e2e_20261027.shift_activation_audit` (ID,
seluruh baris sebelum perubahan, dan waktu). Tidak ada shift bernama lain yang
diaktifkan dan tidak ada jadwal baru yang dibuat.

Baseline target dipertahankan di `test_control.raw_shift_before_activation`,
`workday_before_activation`, `daily_before_activation`, dan `run_before_activation`.
Tanggal bisnis tetap 2026-10-27. Revisi status raw tercatat melalui
`pipeline_run_id=E2E_20261027_REGULAR_V1`; waktu revisi ada pada
`test_control.snapshot_revision`. `source_snapshot_at` tetap menunjuk baseline
master; untuk audit keadaan terkini baca bersama metadata revisi tersebut.
Ini revisi simulasi yang diotorisasi, bukan bukti histori status shift live.

- `activate_regular.py`: skrip aktivasi sekali jalan, pemeriksaan perubahan,
  dan pembentukan ulang workday/curated. Menolak rerun agar audit tetap utuh.
- `results.json`: hasil baseline, tetap dipertahankan.
- `results_revision1.json`: hasil setelah aktivasi dan hash shift baru.
- `verify_snapshot.py`: otomatis memverifikasi revisi terakhir jika tersedia.
- `breakdown_workday.sql` / `.py`: view review dan ekspor rincian per departemen.
- `breakdown_departemen.csv`: semua departemen aktif tanpa kandidat reguler,
  nama shift aktif/nonaktif, parent, dan ancestor terdekat yang memiliki jadwal
  reguler aktif Selasa; tidak berisi nama/NIP individu.
- `breakdown_summary.json`: ringkasan kelompok yang tersisa.

Wajib kerja berubah 16.692 → **61.452**, naik 44.760. Populasi tetap 125.832;
aktif 82.119, nonaktif 43.713, dan satu pegawai reguler libur individual.
Sisa aktif tanpa kandidat = **20.666**, dengan rincian:

| Penyebab | Departemen | Pegawai aktif |
|---|---:|---:|
| Tidak ada shift bernama regular/reguler | 758 | 16.837 |
| Tidak ada shift sama sekali | 200 | 3.784 |
| Reguler aktif tanpa rincian jadwal | 2 | 45 |

Dua departemen terakhir: Terminal Larangan (33059, 23 pegawai, shift 20498)
dan Sub Bagian Umum dan Kepegawaian (33795, 22 pegawai, shift 18795).
Kedua shift tidak mempunyai baris m_jadwal, sehingga aktivasi tidak cukup.

Pada kelompok tanpa nama reguler, 10.854 pegawai berada di departemen dengan
shift aktif bernama lain; 5.983 sisanya hanya mempunyai shift nonaktif.
Contoh terbesar: Bidang Pelayanan Medik dan Keperawatan (36065), 407 pegawai,
dengan berbagai shift rumah sakit. Klasifikasi tidak diubah otomatis.

Kelompok tanpa shift mencakup unit fungsional sekolah, misalnya departemen
32523, 103 pegawai, parent SMKN 1 Lamongan. Nama departemen dapat berulang;
gunakan ID dan parent untuk membedakan unit.

Sebanyak 20.665 dari 20.666 pegawai sisa mempunyai ancestor dengan jadwal
reguler aktif Selasa, tetapi hanya 4.756 yang memilikinya pada parent langsung.
Sisanya ditemukan sampai 2–5 tingkat, termasuk Dinas Pendidikan/Dinas Kesehatan.
Temuan relasi tidak membuktikan pewarisan kewajiban; tidak digunakan otomatis
untuk denominator. Satu pegawai pada departemen Sekretariat Daerah (30115)
tidak memiliki ancestor kandidat; shift yang tersedia bernama GUBERNUR nonaktif.

Query review:

```sql
SELECT * FROM test_control.workday_missing_regular_breakdown
ORDER BY reason, active_employees DESC;
```

Keputusan lanjutan yang diperlukan: apakah dan kapan jadwal induk diwariskan,
klasifikasi jadwal wajib bernama lain (terutama pendidikan/kesehatan), dan
pengisian jadwal untuk dua shift reguler yang belum memiliki rincian hari.
