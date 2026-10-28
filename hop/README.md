# Apache Hop — raw ke curated v2

Pipeline aktif: [curated_incremental_batch.hpl](pipelines/curated/curated_incremental_batch.hpl).
Implementasi SQL: [20261028_curated_incremental_etl.sql](../sql/staging/20261028_curated_incremental_etl.sql).

Satu eksekusi Hop mengambil satu manifest READY tertua dan menjalankan lima
proses dalam satu transaksi PostgreSQL: snapshot populasi jika diminta, lookup
/upsert event, ekspansi izin, ringkasan event, dan hasil harian pegawai. Memecahnya
menjadi lima koneksi TableOutput terpisah akan kehilangan jaminan transaksi ini.
Jika tidak ada batch READY, pipeline berhasil tanpa mengubah data.

## Status penerapan

Fungsi SQL terpasang di `epresensi-staging-postgres / staging_bkd` dan pipeline
terpasang pada proyek Hop `epresensi-staging`. Enam scaffold curated sebelumnya
berada di folder runtime `archive/curated_before_v2_20261028`.

Uji integrasi memakai database sintetis terisolasi. Smoke test Hop aktif hanya
memproses batch kosong; lima tabel curated tetap kosong. Belum ada backfill,
scheduler baru, atau pemuatan populasi/data bisnis pada penerapan ini.

**Producer raw belum otomatis mengirim manifest.** Pipeline raw yang ditemukan
masih full refresh dengan TRUNCATE, bukan incremental. Jangan menjalankannya
untuk mencoba pipeline curated ini. Kontrak integrasi berikut harus dipanggil
oleh loader raw setelah mengetahui ID yang benar-benar berubah. Tidak memakai
watermark ID/timestamp sebagai tebakan, tidak memindai 89 juta event setiap batch,
dan tidak menganggap satu batch sebagai seluruh event pegawai pada suatu hari.

## Kontrak producer raw

Simpan daftar ID event dan izin yang di-insert/update serta ID yang dihapus.
Daftarkan manifest dalam transaksi yang sama dengan upsert raw bila memungkinkan;
consumer baru melihat manifest setelah commit. Jika pendaftaran dilakukan setelah
commit raw, producer harus menyimpan manifest secara durable dan dapat mengirimnya
ulang agar kegagalan di antara kedua langkah tidak kehilangan perubahan.

```sql
-- Di akhir transaksi pemuatan raw, sebelum COMMIT:
SELECT etl_control.enqueue_curated_batch(
  p_batch_id => 'RAW_BATCH_0001',
  p_event_ids => ARRAY[101,102],
  p_leave_ids => ARRAY[201],
  p_deleted_event_ids => ARRAY[]::integer[],
  p_deleted_leave_ids => ARRAY[]::integer[]
);
```

ID di atas hanya contoh, bukan ID yang perlu dijalankan pada database aktual.
Manifest UPSERT harus memiliki baris raw; DELETE memerlukan baris raw sudah tidak
ada. Batch yang bertentangan dengan keadaan raw gagal, bukan diam-diam dianggap
berhasil. Semua ID memakai PK raw sehingga tidak memerlukan full scan histori.

Manifest harus lengkap ketika transaksi enqueue committed; gunakan fungsi
enqueue, bukan menambahkan item satu per satu dengan commit terpisah. ID batch
unik. Jangan enqueue ulang ID batch yang sudah ada: retry cukup menjalankan batch
tersebut. Batch APPLIED dan itemnya tidak dapat diubah. Perubahan baru menggunakan
ID batch baru. Perubahan referensi yang memang dimaksudkan sebagai koreksi lookup
memerlukan enqueue ulang ID event/izin terdampak; ETL tidak otomatis menafsirkan
perubahan master sekarang sebagai perubahan konteks historis.

## Menjalankan dan memeriksa batch

CLI tidak membutuhkan file kredensial; menggunakan psql di container staging.

```bash
python3 hop/scripts/curated_batch.py enqueue --batch-id RAW_BATCH_0001 --events 101,102 --leaves 201
python3 hop/scripts/curated_batch.py run --batch-id RAW_BATCH_0001
python3 hop/scripts/curated_batch.py status --batch-id RAW_BATCH_0001
```

Gunakan enqueue CLI hanya untuk raw yang sudah committed dan ID yang sudah
terverifikasi. Enqueue sendiri tidak memindahkan atau mengubah data raw.

Untuk mengambil satu batch READY tertua lewat Hop:

```bash
docker exec epresensi-hop-web sh -c 'cd /usr/local/tomcat/webapps/ROOT && ./hop-run.sh -j epresensi-staging -e presensi-staging-local -r local -f /usr/local/tomcat/webapps/ROOT/config/projects/epresensi-staging/pipelines/curated/curated_incremental_batch.hpl -l BASIC'
```

Alternatif CLI: `python3 hop/scripts/curated_batch.py next`.
Hasil dan jumlah perubahan tersimpan di `etl_control.curated_batch.result`.
Kesalahan membatalkan seluruh perubahan curated dan menyisakan batch READY untuk
retry. Batch gagal tertua menahan consumer `next` sampai penyebabnya ditangani;
batch lain tetap dapat dijalankan secara eksplisit jika memang independen.
Tidak ada checkpoint yang maju sebelum transaksi curated berhasil.

## Snapshot populasi

Setelah raw pegawai merupakan snapshot lengkap yang berhasil dimuat, enqueue
batch populasi untuk tanggal hari ini menurut Asia/Jakarta:

```bash
python3 hop/scripts/curated_batch.py enqueue --batch-id POPULATION_20261028_01 --snapshot-today --confirm-complete-employee-snapshot
python3 hop/scripts/curated_batch.py run --batch-id POPULATION_20261028_01
```

Ganti ID batch dengan ID unik sesuai eksekusi. Flag complete merupakan pernyataan
producer bahwa snapshot raw lengkap, bukan pemeriksaan kelengkapan otomatis.
Gunakan ID baru jika snapshot berubah lagi pada hari yang sama. Snapshot sama
tidak menulis ulang hasil harian. Snapshot historis dan tanggal yang telah final
ditolak; histori membutuhkan kebijakan tersendiri. `population_basis` tetap
EXTRACTION_SNAPSHOT karena master raw saat ekstraksi tidak membuktikan histori.

Mapping status 1–4 aktif dan 5 nonaktif diverifikasi dari `raw_previleges` pada
pilot. Konfigurasi tersimpan di `etl_control.curated_active_status`; kode lain
menghasilkan unknown/review, bukan dianggap aktif/nonaktif secara diam-diam.

## Tanggal, izin dan ringkasan

- Semua shift masuk, tanpa filter keyword atau status shift saat ini. Event
  manual tetap dihitung. Join referensi memakai LEFT JOIN.
- Setiap ID event di-upsert; kunci pegawai-tanggal lama **dan** baru masuk daftar
  terdampak. Agregasi membaca seluruh event curated pada kunci tersebut.
- Ringkasan seluruh shift memakai MIN check-in dan MAX check-out; bukan durasi
  kerja. ID event tetap dapat ditelusuri melalui pegawai/tanggal pada tabel event.
- Izin diproses independen dari event; koreksi rentang/identitas, pencabutan
  approval, dan penghapusan memperbarui kunci lama dan baru. Izin overlap tidak
  menggandakan pegawai. Izin invalid tanpa rentang/identitas yang dapat diekspansi
  tercatat pada `etl_control.curated_leave_state`.
- Kolom generated tidak diisi loader. Snapshot atau izin dapat mengubah KPI
  meskipun tidak ada presensi baru. Batch tanpa perubahan relevan tidak menulis
  ulang fakta/ringkasan (diverifikasi dengan xmin pada pengujian).
- Kebijakan sementara SAME_DAY_PROVISIONAL_V1 memakai tanggal kalender untuk
  check-in dan checkout dengan jadwal jelas tidak lintas malam. Checkout dengan
  jam keluar <= jam masuk, atau jam rencana tidak diketahui, tetap UNRESOLVED
  dengan tanggal pelaporan NULL. Tidak ada pergeseran D-1/pairing otomatis.
- Event unresolved tetap disimpan; tanggal kalender terkait diberi alasan review.
  Semua hasil masih `is_date_final=false`. Angka tidak masuk/pulang belum boleh
  dianggap kesimpulan resmi untuk tanggal yang atribusinya belum selesai.
- Belum ada kebijakan finalisasi hari, pairing lintas malam, maupun backfill
  populasi historis. Tidak otomatis mengisi histori menggunakan master saat ini.

## Pengujian

```bash
python3 tests/curated_etl_v2/run.py --reset-synthetic
```

Perintah ini hanya membuat ulang `staging_bkd_etl_v2_test_20261028`, menyalin DDL
raw/curated tanpa data, lalu memasukkan fixture sintetis. Hasil berada di
[hasil integrasi](../tests/curated_etl_v2/integration_results.txt).
Database staging aktif dan sumber tidak dipakai sebagai fixture.
