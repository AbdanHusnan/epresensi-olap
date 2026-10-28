# Uji kecil dua shift — pegawai aktual, 28 Oktober 2026

Pelaksanaan atas permintaan pengguna: master diambil dari raw yang telah selesai
backfill; hanya event uji baru yang dibuat di `dbabsen_restore` dan dimuat melalui
Hop. Tidak mengulang backfill dan tidak menjalankan pipeline raw full refresh.

## Cakupan

- Pegawai event: **57342**; pegawai kontrol: **32532**; departemen: **36545**.
- Kedua pegawai aktif pada raw; tidak ada perubahan status/master sumber.
- Bukti historis di raw: empat event pada 2 Agustus 2026, ID 168205076,
  168207135, 168208636, 168212299, menunjukkan dua shift untuk pegawai 57342.
- Shift 22731 (pagi) dan 22732 (siang); jadwal Rabu 125519 dan 125526.
- Target terisolasi: `epresensi-staging-postgres / staging_bkd_e2e_two_shift_20261028`.
  Dua pegawai merupakan keseluruhan populasi **uji**, bukan seluruh organisasi.
- Database sumber tetap `epresensi-olap-postgres / dbabsen_restore`, bukan live.

## Alur yang dijalankan

1. Salin hanya dua master pegawai, satu departemen, dua shift, dan dua jadwal
   dari raw existing ke raw target uji melalui binary COPY. Tidak membaca ulang
   master dari sumber. Tabel raw lain pada target uji kosong.
2. Pasang fungsi ETL yang sama dan salinan pipeline curated yang hanya berbeda
   nama/koneksi target. Jalankan snapshot dua pegawai melalui Hop.
3. Tambahkan satu check-in pukul 07.00 di sumber menggunakan sequence asli.
   Pipeline raw khusus menyalin hanya ID fixture ke `staging_bkd.raw.raw_checkinout`
   dengan `truncate=N`. Verifikasi hash seluruh kolom bisnis terhadap sumber.
4. Salin event tersebut dari raw aktif ke raw uji, daftarkan manifest, kemudian
   jalankan pipeline curated melalui Hop.
5. Ulangi untuk masuk shift siang 14.00, pulang shift pagi 14.05, dan pulang shift
   siang 21.00. Waktu merupakan simulasi, bukan klaim aktivitas nyata pegawai.
6. Kirim ulang empat ID tanpa perubahan untuk membuktikan hasil tidak ditulis
   ulang. Periksa jumlah baris, measure, MIN/MAX, dan versi baris PostgreSQL.

Fixture sumber diberi `is_manual=true` dan keterangan
`E2E_CURATED_TWO_SHIFT_20261028:<label>`. ID serta fase tercatat dalam
`dbabsen_restore.test_curated_v2_20261028.events` pada transaksi yang sama dengan
insert sumber. Tidak mengedit transaksi existing. Empat event uji dipertahankan
di sumber dan raw untuk inspeksi, bukan dihapus otomatis.

## Artefak dan reproduksi

`run.py` menyediakan fase `setup`, `snapshot`, `batch1`, `batch2`, `noop`, `verify`.
**Jangan menjalankan setup ulang:** ia menolak target existing. Fase dapat
dilanjutkan setelah memeriksa manifest dan hasil sebelumnya. Raw loader membaca
hanya ID fixture yang belum ada; semua kolom bisnis kemudian harus cocok dengan
sumber. Tidak memakai watermark atau menyimpulkan batch penuh dari timestamp.

Pipeline `.hpl` pada folder ini tidak memuat kredensial. Metadata koneksi khusus
hanya disimpan di konfigurasi Hop yang sudah ada. Folder runtime pipeline:
`projects/epresensi-staging/pipelines/validation/e2e_two_shift_20261028`.
Nama koneksi: `e2e_restore_20261028`, `e2e_raw_20261028`, `e2e_curated_20261028`.

Log Hop tersedia untuk setiap fase. JSON hasil hanya berisi ID, angka KPI,
timestamp uji dan hash; nama/NIP/kontak pegawai tidak diekspor ke file lokal.

## Batas bukti

Uji membuktikan satu kasus same-day dua shift dengan data kecil dan pipeline
aktual. Ini bukan sertifikasi CDC/producer incremental produksi, performa volume
besar, pairing lintas malam, riwayat populasi, atau finalisasi KPI. Hasil tetap
provisional. Manifest uji dikirim oleh runner setelah raw selesai; producer raw
produksi masih memerlukan integrasi manifest yang durable.

Curated aktif `staging_bkd.curated` tidak diisi oleh pengujian ini. Raw aktif hanya
mendapat empat event fixture baru. Master dan hasil backfill existing dipertahankan.

## Hasil akhir — LULUS

Enam eksekusi Hop selesai tanpa error: snapshot populasi, dua pemuatan raw
append-only, dua batch curated event, dan satu batch curated tanpa perubahan.

| Tahap | Pegawai aktif | Masuk | Tidak masuk | Pulang | Tidak pulang |
|---|---:|---:|---:|---:|---:|
| Snapshot | 2 | 0 | 2 | 0 | 2 |
| Batch pertama | 2 | 1 | 1 | 0 | 2 |
| Batch kedua | 2 | 1 | 1 | 1 | 1 |
| Batch tanpa perubahan | 2 | 1 | 1 | 1 | 1 |

Empat event sumber baru ber-ID **171377675–171377678**. Seluruh kolom bisnis
source/raw cocok berdasarkan hash JSONB; metadata ekstraksi raw tidak ikut hash.
Target uji mempunyai 4 detail event, 1 ringkasan event harian, 2 populasi, dan
2 hasil harian. Tidak ada batch READY tersisa.

Pegawai 57342 mempunyai dua event masuk dan dua event pulang, tetapi measure
masuk/pulang masing-masing **1**. Masuk pertama **07.00**, pulang terakhir
**21.00** pada 28 Oktober 2026. Pegawai 32532 tetap tanpa event.

Batch tanpa perubahan menghasilkan nol perubahan event maupun ringkasan;
versi baris `xmin` hasil harian juga tetap sama. Curated aktif staging_bkd tetap
kosong; empat fixture berada di sumber/raw aktif dan hasilnya di target uji.

Bukti: [hasil akhir](final_result.json), [verifikasi](verification.json),
[batch tanpa perubahan](noop_result.json), [cocok source/raw batch pertama](phase1_raw_verification.json),
dan [cocok source/raw batch kedua](phase2_raw_verification.json).
