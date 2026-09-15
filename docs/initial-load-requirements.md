# Initial load OLAP: requirement dan cara menjalankan

Profil dummy yang disepakati tersedia di [Dummy Jawa Timur — Agustus 2026](dummy-jatim-202608.md).

## Kondisi OLTP sudah dibersihkan

Initial load membaca OLTP yang sudah terisi; proses ini tidak membuat dummy.
Isi master terlebih dahulu, lalu transaksi. OLTP tanpa pegawai ditolak agar data
OLAP lama tidak terganti dengan hasil kosong. Struktur database harus sudah ada;
perintah ini tidak membuat database atau migrasi schema.

## Cakupan dan urutan

| Target OLAP | Sumber OLTP | Requirement |
|---|---|---|
| dim_departemen | m_departemen | Master departemen terisi, ID unik |
| dim_pegawai | m_pegawai | Master pegawai terisi, departemen valid, NIP/nama |
| dim_calendar | Rentang tanggal + m_hari_libur | Tanggal awal/akhir eksplisit; hari libur boleh kosong |
| dim_jadwal_kerja | m_shift + m_jadwal | Master terisi; shift dan departemen valid; satu jadwal per departemen/hari |
| dim_jenis_izin | m_tipe_ijin + m_jenis_ijin | Master terisi; jenis merujuk tipe yang tersedia |
| fact_perizinan | t_perizinan | Pegawai/jenis valid, tanggal izin valid; transaksi boleh kosong |
| analytical_user | m_user | ID unik; pegawai non-NULL harus tersedia; boleh kosong |
| fact_kehadiran | Pegawai × tanggal, t_checkinout, t_libur_shift, izin | Event `work_code = 1` dalam periode; referensi pegawai valid |

Dimensi dimuat sebelum fakta. Izin dimuat sebelum kehadiran agar referensi izin
tersedia. Satu baris fact_perizinan adalah satu pengajuan; satu baris
fact_kehadiran adalah satu pegawai per tanggal, termasuk hari tanpa absensi.
Semua pengajuan izin sumber dimuat, termasuk di luar periode absensi.

## Requirement teknis

- Python dengan `psycopg` dan `python-dotenv` (tersedia di `.venv` proyek).
- `.env`: `OLTP_HOST`, `OLTP_PORT`, `OLTP_DB`, `OLTP_USER`, `OLTP_PASSWORD`,
  serta lima variabel yang sama dengan awalan `OLAP_`.
- Koneksi PostgreSQL dapat diakses. User OLTP memiliki SELECT pada sumber;
  user OLAP memiliki SELECT, INSERT, TRUNCATE pada target, DELETE pada
  `etl_control.pipeline_state`, INSERT/UPDATE pada `etl_control.pipeline_runs`,
  serta akses schema dan sequence run log yang diperlukan.
- Delapan tabel target di atas, `etl_control.pipeline_runs`, dan
  `etl_control.pipeline_state` sudah tersedia. Kontrak kolom diperiksa preflight.
- Tipe kolom, constraint, default ID/run log dan `etl_loaded_at` kompatibel dengan
  data transformasi; preflight kolom tidak membuktikan seluruh constraint atau hak tulis.
- Rentang tanggal dan zona waktu data disepakati. Samakan zona waktu koneksi/data
  absensi agar batas hari konsisten; initial load tidak mengonversi zona waktu.
- `pg_dump` kompatibel dan path backup baru untuk `--apply`.
- Ruang disk untuk backup, tabel, indeks, WAL; waktu maintenance tanpa ETL lain
  atau penulis sumber. Load memakai snapshot sumber dan satu transaksi OLAP;
  kegagalan membatalkan seluruh perubahan OLAP. Lock bertahan sampai commit.

Ukuran fakta kehadiran = jumlah pegawai × jumlah hari inklusif. Contoh 82.000 ×
184 hari = 15.088.000 baris. Pemrosesan absensi per hari; master dan seluruh izin
masih ditampung di memori. Batas saat ini 500.000 pegawai per batch harian.
Ukur kebutuhan RAM/disk/waktu dengan sampel sebelum menaikkan volume.

## Menjalankan

Contoh periode berikut bisa diganti; jalankan dari root repository.

```bash
# 1. Periksa tabel, kolom, master kosong dan estimasi jumlah fakta (read-only).
.venv/bin/python -m etl.pipeline.initial_load \
  --start-date 2026-03-01 --end-date 2026-08-31 --check-only

# 2. Setelah sumber terisi: validasi transformasi lengkap tanpa menulis.
.venv/bin/python -m etl.pipeline.initial_load \
  --start-date 2026-03-01 --end-date 2026-08-31

# 3. Jalankan penggantian seluruh data target OLAP, dengan backup otomatis.
# Ganti nama database dan gunakan path backup baru setiap eksekusi.
.venv/bin/python -m etl.pipeline.initial_load \
  --start-date 2026-03-01 --end-date 2026-08-31 \
  --apply --confirm-db NAMA_DATABASE_OLAP \
  --backup backups/olap-before-initial-load.dump
```

`--check-only` mengembalikan exit code 1 jika requirement belum lengkap. Mode ini
memeriksa nama kolom dan jumlah sumber, bukan seluruh aturan bisnis. Preview
selanjutnya memvalidasi referensi, jadwal, izin, grain fakta, dan rekonsiliasi event.
Transaksi kosong memberi peringatan, bukan kegagalan: tanpa event, hari kerja
pegawai tanpa izin dihitung TIDAK_ABSEN. Initial load adalah full replacement;
periode yang sebelumnya ada di OLAP tetapi di luar rentang baru akan hilang.
Checkpoint terkait dihapus, history run dipertahankan. Jalankan ANALYZE setelah
load sebagaimana runbook, lalu refresh cache/dataset dashboard.

## Agar dummy mendekati production

Siapkan ringkasan agregat berikut untuk mengkalibrasi generator:

1. Jumlah pegawai per departemen dan periode historis.
2. Kalender kerja/libur, jam shift, toleransi terlambat, pola Sabtu/Minggu.
3. Persentase hadir, tidak absen, WFH/WFO, terlambat dan pulang awal per departemen.
4. Frekuensi event hilang/duplikat dan distribusi jam masuk/pulang.
5. Komposisi jenis izin, durasi, approved/rejected/pending, serta overlap izin/absensi.
6. Proporsi akun aktif/pernah login jika analytical_user dipakai dashboard.

Generator yang tersedia menggunakan distribusi ilustratif, belum dikalibrasi
terhadap angka production. Gunakan identitas fiktif dan seed tetap agar hasil
bisa diulang. Model saat ini belum mendukung shift lintas tengah malam, mutasi
historis departemen, atau pembatasan tanggal masuk/keluar pegawai; jangan masukkan
skenario tersebut sebelum aturan ETL diperluas.

Prosedur generator/seed, backup, validasi SQL dan recovery ada di
[runbook lengkap](initial-load.md). Seed yang tersedia mereset seluruh tabel
public OLTP dan mengisi sebelas tabel fixture ETL serta referensi `m_previleges`
ID 1 jika tabel tersebut tersedia. Referensi dimuat sebelum pegawai untuk default
`m_pegawai.status = 1`. Bila dummy dibuat lewat
aplikasi atau mekanisme lain, lewati langkah seed tersebut.
