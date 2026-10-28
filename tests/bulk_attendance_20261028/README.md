# Bulk test presensi dan izin — 28 Oktober 2026

Target: `epresensi-staging-postgres / staging_bkd_bulk_20261028`.
Master merupakan 2.400 pegawai aktual aktif dari raw yang sudah di-backfill,
dengan akun pengguna dan dua shift aktif berjadwal satu hari yang sama.
Pemilihan disebar antar departemen. Fixture event/izin adalah simulasi,
bukan klaim aktivitas atau pengajuan izin nyata pegawai.

## Skenario

Masing-masing skenario berisi 200 pegawai. Seluruh pegawai termasuk populasi
uji; populasi ini bukan snapshot seluruh organisasi.

| ID | Skenario |
|---:|---|
| 0 | Tanpa event dan tanpa izin |
| 1 | Masuk dan pulang |
| 2 | Hanya masuk |
| 3 | Hanya pulang |
| 4 | Izin lengkap, tanpa event |
| 5 | Izin masuk, memiliki absen pulang |
| 6 | Izin pulang, memiliki absen masuk |
| 7 | Izin masuk, belum absen pulang |
| 8 | Izin pulang, belum absen masuk |
| 9 | Izin lengkap, tetap memiliki kedua event |
| 10 | Dua shift: dua masuk dan dua pulang |
| 11 | Dua izin parsial tumpang tindih, satu untuk masing-masing sisi |

Semua transaksi izin awal disetujui. Kode transaksi `tipe_ijin` menentukan
pengecualian; seluruhnya sengaja memakai master jenis izin yang sama agar
hasil tidak bergantung pada flag setengah hari master.

## Alur

1. Salin master terpilih dari raw aktif menggunakan binary COPY dalam memori.
   Tidak mengulang backfill. Pasang schema serta fungsi ETL yang sama.
2. Jalankan snapshot melalui pipeline curated Hop.
3. Buat 2.400 event dan 1.600 izin bertanda `BULK_CURATED_20261028` pada
   `dbabsen_restore`, menggunakan sequence sumber. Manifest ID disimpan dalam
   schema `test_bulk_curated_20261028` pada transaksi yang sama.
4. Batch pertama: muat 1.000 event masuk dan seluruh izin melalui pipeline raw
   Hop ke raw database uji, cocokkan hash semua kolom bisnis, lalu curated Hop.
5. Batch kedua: muat 1.400 event sisanya melalui Hop, cocokkan hash, lalu
   curated Hop. Skenario dua shift harus menghasilkan 2 masuk/2 pulang,
   measure 1/1, waktu masuk MIN dan pulang MAX kedua jadwal.
6. Kirim ulang seluruh 4.000 ID melalui manifest baru. Seluruh perubahan harus
   nol dan versi baris daily (`xmin`) tidak berubah.
7. Koreksi hanya fixture sumber: cabut persetujuan 200 izin lengkap skenario 4;
   ubah kode 200 izin masuk skenario 7 menjadi izin pulang tanpa mengubah
   timestamp transaksi. Muat ulang 400 ID lewat Hop dan proses curated.
   Hanya 400 pegawai boleh berubah; 2.000 daily lain harus mempertahankan `xmin`.

Untuk koreksi, harness menghapus **hanya 400 baris raw fixture di database uji**
sebelum append ulang melalui Hop. Manifest dibuat sesudah pemuatan berhasil dan
hash cocok. Ini menguji consumer raw→curated, bukan implementasi CDC/upsert
producer produksi. Tidak ada penghapusan event/izin existing di restore.

Setiap tahap memeriksa seluruh 2.400 baris terhadap oracle skenario yang
ditulis terpisah dari fungsi ETL. Bukti berupa JSON/log lokal dan
`test_bulk.results` di database uji. Koneksi Hop mengandung kredensial hanya di
metadata container; artefak lokal tidak mengekspor nama/NIP/kontak pegawai.

## Periksa sendiri

Dari root repository:

```bash
docker exec -i epresensi-staging-postgres \
  psql -X -U admin_staging -d staging_bkd_bulk_20261028 \
  < tests/bulk_attendance_20261028/verify.sql
```

Lihat bukti ID fixture sumber:

```bash
docker exec epresensi-olap-postgres sh -c \
  'psql -X -U "$POSTGRES_USER" -d dbabsen_restore -c "SELECT phase,count(*),min(id),max(id) FROM test_bulk_curated_20261028.events GROUP BY phase ORDER BY phase; SELECT count(*),min(id),max(id) FROM test_bulk_curated_20261028.leaves;"'
```

`run.py` menolak database target yang sudah ada. Jangan menjalankan ulang
seluruh runner setelah selesai; gunakan query inspeksi di atas. Fixture sumber
dan hasil uji dipertahankan untuk audit. Raw dan curated aktif `staging_bkd`
tidak diubah oleh pengujian ini.

## Batas bukti

Uji berfokus pada batch ribuan transaksi satu tanggal, termasuk incremental
dan koreksi izin. Tidak menguji lintas tengah malam, finalisasi tanggal,
konkurensi banyak consumer, seluruh volume historis, atau perubahan status
pegawai pada snapshot. Snapshot memakai status master aktual yang tersedia.
Hasil tetap provisional sesuai kontrak ETL.

## Hasil pelaksanaan — LULUS

2.400 pegawai berasal dari **757 departemen**. Sembilan eksekusi Hop selesai:
lima pipeline curated (snapshot, dua batch event, no-op, koreksi) dan empat
pemuatan raw (dua event, izin awal, koreksi izin). Semua kolom bisnis source/raw
cocok melalui hash pada setiap pemuatan.

| Tahap | Aktif | Masuk | Pulang | Tidak masuk | Tidak pulang | Pegawai berizin valid |
|---|---:|---:|---:|---:|---:|---:|
| Snapshot | 2.400 | 0 | 0 | 2.400 | 2.400 | 0 |
| Batch pertama | 2.400 | 1.000 | 0 | 600 | 1.400 | 1.400 |
| Batch kedua | 2.400 | 1.000 | 1.000 | 600 | 600 | 1.400 |
| Kirim ulang | 2.400 | 1.000 | 1.000 | 600 | 600 | 1.400 |
| Koreksi izin | 2.400 | 1.000 | 1.000 | 1.000 | 600 | 1.200 |

Kirim ulang 4.000 ID menghasilkan nol perubahan. Koreksi mengubah tepat 400
pegawai-tanggal; 2.000 baris lainnya tidak ditulis ulang. Seluruh identitas KPI
lulus, termasuk pembagian populasi menjadi wajib dan dikecualikan per sisi.
Event selama izin lengkap tetap tersimpan dan tidak menjadi numerator
kehadiran yang diwajibkan. Semua 200 kasus dua shift memenuhi MIN/MAX dan
measure harian 1/1.

Isi akhir schema `curated`: 2.400 detail event, 1.400 ringkasan event harian,
1.600 baris izin, 2.400 snapshot populasi, dan 2.400 rekap harian. Nol batch
READY tersisa serta nol event/izin bertanda review.

Bukti: [ringkasan akhir](final.json), [hasil sebelum koreksi](batch2_verification.json),
[hasil koreksi](correction_verification.json), [batch tanpa perubahan](BULK_NOOP.json),
[log runner](run.log), dan [hasil command inspeksi](inspection.txt).
