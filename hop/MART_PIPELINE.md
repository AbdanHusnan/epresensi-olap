# Hop curated → fact → serving

Status 28 Oktober 2026: workflow, dua pipeline, koneksi mart, definisi outbox dan
consumer terpasang. **Belum dijalankan. Tidak ada load curated→fact→serving,
bootstrap, aktivasi capture, atau scheduler.** Validasi hanya metadata, definisi
SQL, EXPLAIN tanpa ANALYZE dan pemeriksaan read-only.

Pembaruan 29 Oktober 2026: [uji kecil terisolasi](../tests/mart_small_20261029/README.md)
sudah lulus melalui workflow Hop. Database aktif tetap belum dimuat dan
bootstrap/capture produksi belum aktif. Hasil ini tidak menggantikan benchmark.

Kontrak: [STTM terbaru](../docs/sttm-curated-to-serving-kehadiran.md).

## Entry point

Buka [curated_to_serving.hwf](workflows/mart/curated_to_serving.hwf) di proyek Hop
`epresensi-staging`. Lokasi runtime: `workflows/mart/curated_to_serving.hwf` relatif
ke project. Satu eksekusi workflow nantinya memproses satu batch committed.

```text
Start
  → curated_to_fact_serving_batch.hpl
      baca outbox → apply mart atomik → receipt ke workflow
  → ack_committed_mart_batch.hpl
      receipt → verifikasi commit pada koneksi mart baru → ack staging
```

Tahap acknowledgement hanya diteruskan setelah pipeline pertama selesai sukses.
Hop TableInput lokal memakai transaksi query; pemisahan pipeline memastikan
koneksi pertama sudah ditutup sebelum tahap berikutnya. Verifikasi receipt pada
koneksi mart baru menjadi bukti bahwa hasil target benar-benar committed, bahkan
jika driver gagal melaporkan commit saat disconnect. Jangan menggabungkan apply
serta ack dalam satu pipeline atau memakai shared transaction lintas database.

Koneksi `presensi_staging` dipertahankan. `presensi_mart` ditambahkan memakai
variabel environment Hop; password tidak ada pada HPL/HWF atau repositori.
Jaringan `epresensi_mart` ditambahkan ke runtime Hop dan compose untuk persistensi
saat container dibuat ulang. Tidak ada restart container atau perubahan scheduler.
Reload environment di Hop Web bila variabel baru belum terlihat.

## Definisi dan alur data

[SQL staging](../sql/staging/20261028_mart_outbox.sql):

- `mart_outbox_stream`: identitas stream dan urutan batch transaksional.
- `mart_outbox_batch/item`: payload JSONB immutable setelah commit, bukan sekadar
  ID yang akan dibaca ulang dari curated versi terbaru.
- `prepare_mart_bootstrap()`: fungsi eksplisit yang mengambil snapshot existing
  per tanggal dan memasang capture INSERT/UPDATE/DELETE dalam transaksi dan lock
  yang sama. Tidak dipanggil oleh installer atau workflow.
- Capture memakai transition tables; mencatat key lama/baru, tombstone DELETE,
  serta hasil akhir tiap pegawai-tanggal dalam satu transaksi curated.
- Update source_snapshot_at saja tidak menghasilkan batch. TRUNCATE daily
  ditolak setelah capture aktif agar penghapusan tidak kehilangan tombstone.
- `next_mart_delivery()`: membaca satu batch pending tanpa mengubah sumber.
- `ack_mart_delivery()`: menandai terkirim secara berurutan setelah verifikasi mart.

[SQL mart](../sql/mart/20261028_mart_incremental_etl.sql):

- `apply_mart_delivery()` memvalidasi kontrak, stream dan sequence. Sequence 1
  wajib BOOTSTRAP dan target fact/agregasi/checkpoint harus kosong.
- Satu transaksi menyimpan dimensi, upsert/delete fact, rebuild partisi
  tanggal-departemen lama DAN baru, date_state, receipt, dan checkpoint APPLIED.
- Seluruh 12 measure disalin dari payload curated; constraint schema menolak
  nilai yang tidak konsisten. Tidak menghitung ulang izin atau atribusi tanggal.
- Kalender diisi dari tanggal payload. Dimensi pegawai/departemen menggunakan
  versi efektif existing. Interval yang belum tercakup dibuat sebagai placeholder
  identitas tanpa nama dari ID curated, sampai batas versi berikutnya bila ada;
  tidak mengambil master terbaru untuk mengarang nama/status historis.
  Departemen NULL memakai UNKNOWN key 0. Nama dapat dilengkapi melalui proses
  dimensi dengan bukti snapshot/versi yang sesuai.
- Lookup key harus tepat satu baris. PK/FK/constraint measure menjaga kontrak.
- Agregasi rebuilt hanya untuk partisi terdampak; partisi kosong dihapus.
- Payload replay harus identik dengan receipt tersimpan. Replay mengembalikan
  receipt tanpa menulis ulang fact. No-op bisnis mempertahankan fact/agregasi;
  delivery baru tetap mempunyai receipt/checkpoint untuk audit.
- Koreksi mengembalikan date_state tanggal terdampak ke incomplete/open.
  Tidak ada klaim complete/closed otomatis: payload belum membawa bukti cakupan.
  is_date_final curated tetap disalin, tetapi view menjaga status provisional.
- `confirm_mart_delivery()` read-only memeriksa receipt/APPLIED pada koneksi baru.

Receipt menyimpan payload untuk retry dan audit. Kebijakan retensi/arsip belum
ada; jangan menghapus receipt/outbox tanpa merancang ulang jaminan replay.
Payload bootstrap dibatasi satu tanggal, bukan seluruh histori dalam satu JSON.
Ukuran maksimum harian dan concurrency tetap perlu diuji sebelum aktivasi rutin.

## Instalasi, tanpa load

Schema dasar [attendance_daily.sql](../sql/mart/20261028_attendance_daily.sql)
harus sudah terpasang. Installer definisi adalah migrasi **satu kali**; jika objek
sudah ada ia gagal, bukan menimpa/drop. Staging dan mart dipasang dalam transaksi
masing-masing karena berbeda database. Bila tahap kedua gagal, inspeksi tahap
pertama sebelum melanjutkan; jangan menganggap instalasi lintas DB atomik.

```bash
python3 hop/scripts/install_mart_etl.py                      # tampilkan rencana
python3 hop/scripts/install_mart_etl.py --apply-definitions  # definisi saja
python3 hop/scripts/deploy_mart_pipeline.py                 # tampilkan rencana
python3 hop/scripts/deploy_mart_pipeline.py --apply-metadata # file/koneksi saja
```

Perintah apply di atas sudah dilakukan pada tahap pembuatan ini. Jangan mengulang
installer satu kali pada target yang sama. Deployment file/metadata dapat diulang.
Installer tidak memanggil fungsi bootstrap/apply/ack dan tidak menjalankan Hop.

## Aktivasi berikutnya — belum dilakukan

Setelah ada instruksi untuk aktivasi/pemuatan dan pengujian integrasi:

1. Uji pada database terisolasi: bootstrap, dua shift, izin/overlap, no-op,
   koreksi/delete/perpindahan key/departemen, urutan salah, replay payload berubah,
   rollback dan kegagalan antara commit target dengan ack sumber.
2. Pastikan target awal kosong dan sumber curated memiliki basis snapshot yang
   benar. Bootstrap tidak mengisi populasi historis dari master sekarang.
3. Panggil `etl_control.prepare_mart_bootstrap()` secara eksplisit di staging.
   Ini mempersiapkan delivery snapshot dan mengaktifkan capture atomik, belum
   memuat fact. Fungsi menolak bootstrap ulang; retry dilakukan pada delivery.
4. Jalankan entry point workflow per batch. Jangan menjalankan child ack secara
   manual atau menandai outbox delivered tanpa receipt committed.
5. Rekonsiliasi curated/fact/agregasi sebelum scheduler atau cutover dashboard.

Sebelum langkah 3, curated existing tetap dapat berjalan seperti sebelumnya;
perubahannya akan tercakup dalam snapshot bootstrap saat aktivasi. Capture sengaja
belum aktif agar tahap pembuatan pipeline ini tidak mengubah perilaku ETL existing.

## Bukti tanpa load

Folder [tests/mart_pipeline_20261028](../tests/mart_pipeline_20261028/README.md)
memuat validasi parser Hop asli untuk dua pipeline dan workflow, EXPLAIN 16
statement inti tanpa eksekusi, dan hasil verifikasi fact/agregasi/batch/receipt
nol. Outbox kosong, last_sequence=0, bootstrap_prepared=false, capture trigger
pada curated belum ada. Ini belum merupakan uji integrasi atau performa load.
