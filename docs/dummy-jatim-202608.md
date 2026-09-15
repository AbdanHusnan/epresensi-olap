# Dummy Jawa Timur — Agustus 2026

Profil `jatim-202608` memenuhi parameter yang disepakati: **82.000 pegawai**, satu
bulan **1–31 Agustus 2026**, **25 departemen**, dan **4 pola shift**. Identitas,
penempatan pegawai, jadwal, serta transaksi bersifat fiktif dan dapat diulang
menggunakan seed 42. Nama organisasi mengambil contoh dari
[SIKIPO Pemprov Jawa Timur](https://api.sikipo.jatimprov.go.id/index.php/dashboard/opd).
Daftar berisi 24 dinas dan Badan Pendapatan Daerah, masing-masing 3.280 pegawai.
Daftar lengkap tersedia di `etl/dummy/jatim.py` dan header file dataset.

## Kalender, shift, dan persentase

Senin–Jumat dijadwalkan bekerja; Sabtu/Minggu libur. Tanggal 17 dan 25 Agustus
mengikuti [daftar libur nasional Kemenko PMK](https://www.kemenkopmk.go.id/node/5862).
Dengan demikian ada 19 hari kerja dan 12 hari nonkerja. Tidak ada libur shift
individual tambahan atau pekerjaan pada hari libur dalam profil ini.

| Pola shift | Masuk | Pulang |
|---|---|---|
| Shift 1 | 07.00 | 15.00 |
| Shift 2 | 08.00 | 16.00 |
| Shift 3 | 09.00 | 17.00 |
| Shift 4 | 12.00 | 20.00 |

Jam mengikuti WIB, disimpan sebagai timestamp lokal tanpa zona waktu. Pola ini
bukan klaim jam kerja resmi dinas. Karena schema mengikat `m_shift` ke departemen,
empat pola didaftarkan pada setiap departemen: **100 baris m_shift**. Setiap
kombinasi departemen/hari memiliki tepat satu jadwal: **125 baris m_jadwal**.
Pola bergantian menurut departemen dan hari, dengan indeks
`(departemen_id - 1 + weekday) % 4`; weekday Senin=0 sampai Jumat=4. Seluruh pegawai
departemen mengikuti jadwal yang sama pada hari itu. Model empat shift bersamaan
untuk kelompok pegawai dalam satu departemen membutuhkan pemetaan jadwal pegawai
baru dan perubahan ETL, yang belum dimodelkan schema saat ini.

| Kategori eksklusif pada hari kerja | Persentase | Pegawai-hari |
|---|---:|---:|
| WFO tepat waktu | 60% | 934.800 |
| WFH tepat waktu | 10% | 155.800 |
| WFO terlambat | 10% | 155.800 |
| Izin disetujui | 10% | 155.800 |
| Tidak absen | 10% | 155.800 |
| Total | 100% | 1.558.000 |

Kuota tepat pada **setiap departemen dan hari kerja**, bukan hanya probabilitas
acak. Pegawai yang mendapat kategori diacak secara deterministik per hari.
Untuk ukuran sampel yang tidak habis dibagi 10, kuota dibulatkan dengan metode
sisa terbesar. Hasil ukuran penuh 82.000 tidak memerlukan pembulatan.

WFH dan terlambat tetap berstatus `HADIR` dalam OLAP; keduanya dibedakan oleh flag.
Karena itu agregat `status_kehadiran = HADIR` adalah **80% hari kerja**, dengan
60% WFO tepat waktu + 10% WFH + 10% WFO terlambat.

Setiap hari hadir memiliki dua event masuk/pulang. Kedatangan tepat waktu antara
25 menit sebelum jadwal sampai tepat jadwal; terlambat 5–60 menit; kepulangan
0–30 menit sesudah jadwal. Izin semuanya approved dan berdurasi satu hari;
jenisnya diacak antara cuti, sakit, dan izin pribadi. Tidak ada izin pending atau
rejected, overlap izin/absensi, pulang awal, maupun event hilang dalam profil
terkontrol ini. Profil `legacy` tetap tersedia untuk skenario variasi tersebut.
Semua akun dummy aktif dan `last_login = NULL`.

## Artifact dan jumlah baris

File: `data/dummy-jatim-82000-202608.jsonl.gz`. Format JSON Lines gzip versi 2,
termasuk metadata profil dan completion trailer; kompatibel dengan seed yang ada.
Seed juga membuat satu baris `m_previleges` (ID 1, `Pegawai Dummy`) sebelum
pegawai dimuat jika tabel tersebut ada di schema OLTP. Ini memenuhi default
`m_pegawai.status = 1`; artifact tidak perlu dibuat ulang. Jumlah di bawah adalah
isi artifact, belum termasuk satu baris referensi tambahan saat seed.

| Sumber | Jumlah |
|---|---:|
| m_departemen | 25 |
| m_pegawai | 82.000 |
| m_user | 82.000 |
| m_shift | 100 |
| m_jadwal | 125 |
| m_tipe_ijin | 1 |
| m_jenis_ijin | 3 |
| m_hari_libur | 2 |
| t_libur_shift | 0 |
| t_perizinan | 155.800 |
| t_checkinout | 2.492.800 |

Target initial load: 25 departemen, 82.000 pegawai, 31 tanggal, 125 jadwal,
3 jenis izin, 82.000 analytical_user, 155.800 fakta izin, dan **2.542.000 fakta
kehadiran**. Dari fakta kehadiran: HADIR 1.246.400; IZIN 155.800;
TIDAK_ABSEN 155.800; NON_WORKING_DAY 984.000.

## Generate, preview, dan load

```bash
# Artifact sudah dihasilkan. Untuk mengulang gunakan path output baru.
.venv/bin/python -m etl.dummy.generate \
  --profile jatim-202608 --employees 82000 \
  --start-date 2026-08-01 --end-date 2026-08-31 --seed 42 \
  --output data/dummy-jatim-82000-202608.jsonl.gz

# Validasi file dan lihat cakupan seed (tanpa perubahan database).
.venv/bin/python -m etl.dummy.seed data/dummy-jatim-82000-202608.jsonl.gz
```

File telah dibuat, tetapi belum diimpor ke tabel utama OLTP/OLAP. Seed yang ada
mereset seluruh tabel public OLTP, termasuk tabel aplikasi di luar fixture.
Prosedur seed dengan backup dan penggantian OLAP tersedia di
[runbook initial load](initial-load.md); gunakan artifact serta periode satu
bulan di halaman ini, bukan contoh enam bulan profil legacy.

Sesudah OLTP diisi:

```bash
.venv/bin/python -m etl.pipeline.initial_load \
  --start-date 2026-08-01 --end-date 2026-08-31 --check-only
.venv/bin/python -m etl.pipeline.initial_load \
  --start-date 2026-08-01 --end-date 2026-08-31
.venv/bin/python -m etl.pipeline.initial_load \
  --start-date 2026-08-01 --end-date 2026-08-31 \
  --apply --confirm-db NAMA_DATABASE_OLAP \
  --backup backups/olap-before-jatim-202608.dump
```

## Verifikasi hasil OLAP

```sql
SELECT count(*) AS total_facts,
       count(*) FILTER (WHERE is_expected_workday) AS workdays,
       count(*) FILTER (WHERE is_expected_workday AND status_kehadiran='HADIR'
                         AND is_wfo AND NOT is_terlambat) AS wfo_tepat_waktu,
       count(*) FILTER (WHERE is_expected_workday AND is_wfh) AS wfh,
       count(*) FILTER (WHERE is_expected_workday AND is_terlambat) AS terlambat,
       count(*) FILTER (WHERE is_expected_workday AND status_kehadiran='IZIN') AS izin,
       count(*) FILTER (WHERE is_expected_workday AND status_kehadiran='TIDAK_ABSEN') AS tidak_absen
FROM fact_kehadiran
WHERE tanggal BETWEEN '2026-08-01' AND '2026-08-31';
```

Tes otomatis memeriksa kategori setelah transformasi ETL, kuota per
pegawai-hari/departemen, hari libur, pola shift, konsistensi ID lintas batch,
reproduksibilitas, serta COPY/constraint/rollback pada schema PostgreSQL sementara.

## Jika pg_dump lokal versi 16 tetapi server OLTP versi 18

Helper `scripts/pg_dump18` menggunakan image lokal `postgres:18.4` melalui Docker.
Helper membutuhkan akses Docker, meneruskan password melalui environment, dan
menulis arsip ke stdout untuk ditangani mekanisme backup seed. Helper tidak
memulai server PostgreSQL atau menarik image baru.

Dari root repository, periksa versi lalu ulangi seed dengan nama backup baru:

```bash
./scripts/pg_dump18 --version
DUMMY_PG_DUMP=./scripts/pg_dump18 .venv/bin/python -m etl.dummy.seed \
  data/dummy-jatim-82000-202608.jsonl.gz \
  --apply --all-public-records --confirm-db epresensi_clean \
  --backup backups/oltp-before-jatim-202608-pg18.dump
```

Backup gagal versi dapat meninggalkan file 0 byte; file tersebut bukan backup
pemulihan. Jangan gunakan kembali path itu. Prefix environment di atas berlaku
hanya untuk command seed OLTP; initial load OLAP tetap memakai client default.
Perbedaan versi ini sesuai batasan [pg_dump PostgreSQL](https://www.postgresql.org/docs/18/app-pgdump.html):
client tidak dapat membackup server dengan major version lebih baru darinya.


## Jika seed sebelumnya gagal pada m_pegawai_status_fkey

Seed telah diperbaiki agar referensi `m_previleges` ID 1 ikut dimuat dan sequence
serta jumlah barisnya direkonsiliasi. Tidak ada foreign key yang dinonaktifkan.
Tes menggunakan salinan schema OLTP asli dengan default/constraint dipertahankan,
sequence terisolasi, dan seluruh perubahan di-rollback. File dummy lama tetap valid.
Ulangi dengan backup baru (backup percobaan sebelumnya tetap disimpan):

```bash
DUMMY_PG_DUMP=./scripts/pg_dump18 .venv/bin/python -m etl.dummy.seed \
  data/dummy-jatim-82000-202608.jsonl.gz \
  --apply --all-public-records --confirm-db epresensi_clean \
  --backup backups/oltp-before-jatim-202608-refs.dump
```
