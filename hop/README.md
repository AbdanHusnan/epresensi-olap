# Pipeline dimensi presensi

Project `presensi`, environment `presensi-local`, run configuration `local`.
Target aktif **epresensi_analytics_hop_dev.public**. Sumber **dbabsen_restore.public**.
Koneksi `presensi_target` memakai `${HOP_TARGET_DB}`. Database analytics lama dan
`epresensi_analytics.hop.dim_departemen` bukan target aktif pipeline ini.

## Mapping dan urutan

1. `pipelines/dim_departemen.hpl`: Table Input → Insert / Update, kunci
   `departemen_id_sumber`. Tujuh atribut sumber; `departemen_id` juga diisi ID sumber
   untuk kompatibilitas dengan view/FK pada database dev.
2. `pipelines/dim_pegawai.hpl`: Table Input (LEFT JOIN m_previleges) → Database Lookup
   public.dim_departemen → Insert / Update, kunci `pegawai_id_sumber`.
3. `pipelines/dim_shift.hpl`: gabung m_jadwal + m_shift → lookup departemen →
   Insert / Update, kunci `jadwal_id_sumber`. Setup/run ada pada bagian shift di bawah.

Pegawai menyimpan identitas, departemen mentah dan key lookup, kategori pegawai,
kode jenis kelamin, jabatan/pangkat/jenis jabatan/eselon/kelas jabatan, unit induk,
dan timestamp sumber. Semua kategori termasuk Non-Aktif dimuat. `status_aktif`
tetap NULL; status sumber adalah kategori, bukan bukti masa aktif historis.
`status_shift` tidak dipakai sebagai ID shift. NIP tetap teks.
Mapping: [lembar review](../docs/oltp-mapping-review.csv).

Grain satu baris per ID sumber, kondisi terbaru, tanpa SCD2. ID baru mendapat
surrogate key database; perubahan atribut mempertahankan key. Timestamp proses
hanya berubah pada insert/update; rerun identik dilewati. Tidak ada delete otomatis.
Tidak memfilter kode HAPUS/nama NULL pada departemen. Lookup gagal mempertahankan
pegawai dengan key NULL; validator menandainya. Selesaikan pipeline departemen
sebelum pegawai dan jangan jalankan dua instance bersamaan. Commit per 1000 baris;
rerun setelah memperbaiki penyebab kegagalan untuk memulihkan batch parsial.

## Setup dan deploy

`setup_hop_departemen.py` kini menyiapkan **kedua** dimensi pada database dev yang
sudah tersedia. Migrasi aditif `sql/hop/dev_dimensions.sql` mempertahankan tabel,
FK, view, dan kolom kompatibilitas. Skrip ini bukan bootstrap database kosong.
`sql/hop/dim_departemen.sql` adalah DDL target lama, tidak lagi dipakai setup.

```bash
.venv/bin/python scripts/setup_hop_departemen.py
docker cp .env.hop.json epresensi-hop-web:/usr/local/tomcat/webapps/ROOT/config/environments/presensi-local.json
docker cp hop/presensi/. epresensi-hop-web:/usr/local/tomcat/webapps/ROOT/config/projects/presensi/
docker exec -u root epresensi-hop-web chown -R hop:hop /usr/local/tomcat/webapps/ROOT/config/projects/presensi /usr/local/tomcat/webapps/ROOT/config/environments/presensi-local.json
```

Backup/export perubahan GUI sebelum deploy: volume GUI tidak otomatis sinkron
ke repository. Metadata menyimpan referensi variabel, bukan password. `.env.hop`
dan `.env.hop.json` diabaikan Git, mode 0600. Reader hanya membaca tiga tabel master.
Writer mempunyai SELECT/INSERT/UPDATE pada dua dimensi dan akses sequence terkait.
Trigger mart departemen yang sudah ada memerlukan SELECT mart ringkasan dan
SELECT/INSERT mart_dirty_dates; tidak diberi DELETE/TRUNCATE atau hak admin.

Setelah perubahan koneksi, buka ulang proyek/environment di GUI. Jika environment
lama masih tersimpan dalam sesi, restart Hop Web lalu sambungkan ulang browser.

## Run dan validasi

```bash
docker exec epresensi-hop-web bash -c 'cd /usr/local/tomcat/webapps/ROOT && ./hop-run.sh --project=presensi --environment=presensi-local --runconfig=local --file=/usr/local/tomcat/webapps/ROOT/config/projects/presensi/pipelines/dim_departemen.hpl --level=Minimal'
docker exec epresensi-hop-web bash -c 'cd /usr/local/tomcat/webapps/ROOT && ./hop-run.sh --project=presensi --environment=presensi-local --runconfig=local --file=/usr/local/tomcat/webapps/ROOT/config/projects/presensi/pipelines/dim_pegawai.hpl --level=Minimal'
.venv/bin/python scripts/validate_hop_dimensions.py
```

Jalankan kedua pipeline sekali lagi tanpa perubahan sumber, kemudian:

```bash
.venv/bin/python scripts/validate_hop_dimensions.py --unchanged
```

Validasi seluruh nilai, ID, key lookup, dan hash key/timestamp pada rerun disimpan
ke `logs/reports/validation-hop-dimensions.json`. Sumber/target dibaca dalam snapshot
terpisah; lakukan pada sumber yang stabil. Skrip `validate_hop_departemen.py`
sekarang mengarahkan ke validator kedua dimensi agar tidak memeriksa target lama.

Di laptop gunakan port tunnel yang sudah berhasil, misalnya:
`ssh -N -L 28080:127.0.0.1:8080 pti`, lalu `http://127.0.0.1:28080/ui`.
Refresh file explorer proyek untuk melihat kedua pipeline.

## String kosong dan NULL

Runtime memakai `HOP_EMPTY_STRING_DIFFERS_FROM_NULL=Y` pada variabel global
Hop (`config/hop-config.json`) dan `JAVA_TOOL_OPTIONS` pada Compose. Ini wajib
agar string kosong tidak berubah menjadi NULL. Sumber memiliki tujuh nama kosong
dan satu NIP kosong; nilai tersebut dipertahankan, tanpa label/nilai pengganti.
Jalankan `docker compose -p epresensi-hop -f docker-compose.hop.yml up -d` setelah
perubahan opsi JVM. Referensi: https://hop.apache.org/manual/latest/variables.html



## Dimensi shift gabungan

Pipeline `pipelines/dim_shift.hpl` menulis ke
`epresensi_analytics_hop_dev.public.dim_shift`. Satu baris per `m_jadwal.id`;
`shift_id_sumber` induk dapat berulang pada hari berbeda. Upsert berdasarkan
`jadwal_id_sumber`, surrogate `shift_key` stabil.

Alur: gabung m_jadwal LEFT JOIN m_shift → lookup dim_departemen → Insert / Update.
Jalankan setelah departemen. Status nonaktif dan jadwal akhir pekan tetap dimuat.
Jam sama/lintas malam hanya indikator, bukan keputusan libur atau tanggal fakta.
Shift tanpa jadwal dicatat terpisah dalam laporan, tidak diberi jadwal buatan.
Snapshot tidak merekonstruksi histori. Tidak dibuat dimensi jadwal terpisah.

```bash
.venv/bin/python scripts/setup_hop_shift.py
docker cp hop/presensi/pipelines/dim_shift.hpl epresensi-hop-web:/usr/local/tomcat/webapps/ROOT/config/projects/presensi/pipelines/dim_shift.hpl
docker exec -u root epresensi-hop-web chown hop:hop /usr/local/tomcat/webapps/ROOT/config/projects/presensi/pipelines/dim_shift.hpl
docker exec epresensi-hop-web bash -c 'cd /usr/local/tomcat/webapps/ROOT && ./hop-run.sh --project=presensi --environment=presensi-local --runconfig=local --file=/usr/local/tomcat/webapps/ROOT/config/projects/presensi/pipelines/dim_shift.hpl --level=Minimal'
.venv/bin/python scripts/validate_hop_shift.py
```

Setelah rerun pipeline tanpa perubahan sumber:
`.venv/bin/python scripts/validate_hop_shift.py --unchanged`.
Laporan `logs/reports/validation-hop-dim-shift.json` memuat rekonsiliasi penuh, key,
timestamp, jumlah dan ID shift tanpa jadwal. Setup menggunakan akun terbatas
Hop yang sudah ada dan tidak mengubah password atau koneksi pipeline lainnya.
SQL Table Input ada juga di `sql/hop/extract_dim_shift.sql`; jaga kesamaan SQL
tersebut dengan pipeline jika mapping diedit.


## Dimensi tanggal / dim_calendar

Pipeline `pipelines/dim_calendar.hpl` →
`epresensi_analytics_hop_dev.public.dim_calendar`. Satu baris per tanggal.
Parameter **START_DATE** dan **END_DATE** pada Run Options memakai format
YYYY-MM-DD, inklusif; default 2021-01-01 sampai 2026-12-31. Rentang terbalik ditolak.
Tanggal adalah key; tidak ada surrogate baru atau penghapusan tanggal di luar
periode. Pipeline dapat dijalankan mandiri karena tidak membutuhkan dimensi lain.

Alur: generator tanggal + agregasi libur per tanggal (Table Input) → Insert / Update.
Penanda libur berdasarkan keberadaan record, termasuk bila keterangan NULL.
Nama hari/bulan Indonesia, hari dan tahun ISO, akhir pekan, serta Senin–Jumat
normal dihitung deterministik. Libur pegawai dan kewajiban hadir harian bukan
atribut kalender. ID libur sumber disimpan sebagai daftar angka terurut dalam
teks, dipisah koma. Data libur terakhir 2026-08-25; kelengkapannya belum disertifikasi.

```bash
.venv/bin/python scripts/setup_hop_calendar.py
docker cp hop/presensi/pipelines/dim_calendar.hpl epresensi-hop-web:/usr/local/tomcat/webapps/ROOT/config/projects/presensi/pipelines/dim_calendar.hpl
docker exec -u root epresensi-hop-web chown hop:hop /usr/local/tomcat/webapps/ROOT/config/projects/presensi/pipelines/dim_calendar.hpl
docker exec epresensi-hop-web bash -c 'cd /usr/local/tomcat/webapps/ROOT && ./hop-run.sh --project=presensi --environment=presensi-local --runconfig=local --file=/usr/local/tomcat/webapps/ROOT/config/projects/presensi/pipelines/dim_calendar.hpl --level=Minimal'
.venv/bin/python scripts/validate_hop_calendar.py
```

Setelah rerun tanpa perubahan sumber:
`.venv/bin/python scripts/validate_hop_calendar.py --unchanged`.
Untuk periode lain, validator menerima `--start-date YYYY-MM-DD --end-date YYYY-MM-DD`
sesuai parameter pipeline. Rekonsiliasi dan pengujian kasus batas disimpan pada
`logs/reports/validation-hop-dim-calendar.json`. Validasi rerun harus memakai periode yang
sama dengan laporan pembanding. SQL mandiri dan SQL di dalam pipeline harus tetap
sama bila mapping diedit.

## Status pipeline fakta — 9 Oktober 2026

Pipeline `fact_kehadiran.hpl` dan `fact_ingest_events.hpl`, kedua workflow
pendukungnya, serta `scripts/run_hop_fact.py` telah dihapus atas permintaan
pengguna. Pengguna akan membuat pipeline fakta sendiri melalui Apache Hop.
Pipeline dimensi tetap tersedia. Data database, fungsi SQL, checkpoint, serta
laporan validasi lama dipertahankan; penghapusan ini bukan reset database.

Bagian berikut merupakan **catatan historis implementasi yang sudah dihentikan**.
Perintah runner dan referensi pipeline/workflow fakta di bawah tidak lagi berlaku.

## Riwayat fact kehadiran: seluruh histori restore

Workflow `workflows/fact_kehadiran_all.hwf` menjalankan
`pipelines/fact_kehadiran.hpl` berulang sampai checkpoint selesai. Target tetap
`epresensi_analytics_hop_dev`; sumber khusus `dbabsen_restore`. Transformasi SQL
dieksekusi oleh Hop melalui koneksi `presensi_target`, dengan foreign tables
target `hop_source` yang membaca sumber memakai akun terbatas. Aturan berada di
`sql/hop/fact_kehadiran_rules.sql`; pipeline memanggil `hop_etl.fact_step()`.

Tahapan: agregasi event per rentang ID → snapshot izin/libur/dimensi → fakta per
tanggal → rekonsiliasi. Satu batch event mencakup paling banyak 1.000.000 ID,
bukan batas jumlah data keseluruhan. Setiap batch dan checkpoint commit atomik.
Rerun melanjutkan posisi terakhir; workflow selesai menjadi no-op. Jangan
menjalankan dua loader bersamaan atau mengosongkan checkpoint untuk mengulang.
Ini backfill sumber restore yang tetap, belum merupakan sinkronisasi perubahan
sumber. Pembaruan histori membutuhkan rancangan run/reprocessing tersendiri.

```bash
# Provisioning awal; jangan jalankan bersamaan dengan loader aktif.
.venv/bin/python scripts/setup_hop_fact.py
# Setelah pipeline/workflow disalin ke project Hop: jalankan atau lanjutkan.
.venv/bin/python scripts/run_hop_fact.py --detach
# Audit progres; --complete hanya berhasil setelah seluruh rentang selesai.
.venv/bin/python scripts/validate_hop_fact.py
```

Runner memanggil Hop, menyimpan log dan status di `logs/hop-fact/latest.json`,
lalu otomatis menjalankan `validate_hop_fact.py --complete` setelah Hop sukses.
Status `running` pada berkas adalah catatan terakhir, bukan heartbeat; cocokkan
dengan proses dan `hop_etl.fact_checkpoint.changed_at` bila mesin terputus.
Kegagalan tersimpan sebagai `failed`/`validation_failed`. Jalankan ulang runner
setelah penyebabnya diperbaiki. Runner tahan putusnya sesi chat, tetapi tidak
otomatis hidup kembali setelah restart host/container.

```sql
SELECT * FROM hop_etl.fact_checkpoint;
SELECT * FROM hop_etl.fact_days ORDER BY tanggal DESC LIMIT 10;
SELECT * FROM analytics.hop_fact_kehadiran_review WHERE tanggal = DATE '2024-01-02';
SELECT * FROM analytics.hop_event_rejects;
```

Grain fisik tetap pegawai × tanggal. Baris dibentuk bila ada bukti event, izin,
atau libur individual; kandidat tanpa bukti tersedia lewat
`analytics.hop_missing_employee_days_review` setelah run selesai. Selalu filter
tanggal/pegawai saat membaca view kandidat tersebut karena cakupannya besar.
Snapshot seluruh master bukan bukti bahwa seluruh pegawai wajib hadir sepanjang
histori. Tidak dibentuk TANPA_KETERANGAN atau penyebut tingkat kehadiran tanpa
bukti populasi historis.

Konsumsi KPI melalui `analytics.hop_fact_kehadiran_final`: hanya baris tanpa
review setelah checkpoint selesai. View dashboard target juga menyaring review
dan run yang belum selesai. `durasi_terlambat` adalah menit desimal tanpa
pembulatan; kolom legacy `menit_terlambat` belum diisi, sehingga dashboard legacy
belum menyajikan durasi ini. Data eligible tidak mewakili seluruh populasi.
Prioritas IZIN atas HADIR dipertahankan. Jadwal ambigu, pasangan event belum
valid, histori tidak terbukti, hari nonwajib, manual/fleksibel, konflik izin,
dan cakupan hari belum terverifikasi disimpan sebagai review.

Validasi mencakup 14 skenario aturan, uji tanggal dalam transaksi rollback,
kontinuitas batch ID, jumlah event/reject, serta rekonsiliasi fakta saat selesai.
Laporan progres adalah `logs/reports/validation-hop-fact-progress.json`; laporan lengkap
baru dibuat sebagai `logs/reports/validation-hop-fact-complete.json` bila run selesai
dan seluruh pemeriksaan lolos. Uji rollback saat ekstraksi masih berjalan bukan
rekonsiliasi final tanggal itu: ID batch berikutnya bisa membawa event lama.

Laporan yang dihasilkan skrip disimpan di `logs/reports/` (diabaikan Git), terpisah
dari dokumentasi yang dipelihara. Baseline validasi dimensi tetap disimpan di sana
untuk opsi `--unchanged`. Laporan audit/benchmark lama telah dibersihkan; jalankan
skrip terkait bila memerlukan hasil baru. Skrip validasi tetap dipertahankan karena
runner backfill fakta memakainya untuk pemeriksaan akhir.

### Penyesuaian load histori 8 Oktober 2026

Pembacaan seluruh event menemukan rentang tanggal **2020-06-01 sampai
2026-09-01**. Kalender target diperluas melalui pipeline dengan parameter
`START_DATE=2020-06-01,END_DATE=2026-12-31` menjadi 2.405 tanggal. Tanggal tambahan
masuk snapshot sebelum pembentukan fakta; parameter default kalender tetap sama.
Untuk validasi kalender aktual, gunakan `--start-date 2020-06-01 --end-date 2026-12-31`.

Rentang tersebut bukan histori event yang kontinu sejak 2020. Ada **976 tanggal
unik berisi event**: satu event bertanggal 2020-06-01, lalu 366 tanggal tahun 2024,
365 tanggal tahun 2025, dan 244 tanggal tahun 2026 sampai 1 September. Tidak ada
event presensi pada 2021–2023; fakta review yang muncul di periode tersebut
berasal dari bukti izin/libur individual sesuai aturan kandidat. Tanggal 2020
tetap dipertahankan untuk review, bukan dianggap bukti histori harian lengkap.

Trigger legacy `analytics.mart_dirty_dates.flush_attendance_marts` dinonaktifkan
khusus pada target Hop dev. Pencatatan dirty dates tetap aktif. Mart/dashboard
legacy belum diperbarui oleh load ini dan memerlukan refresh eksplisit serta
validasi terpisah saat integrasi dashboard; keberhasilan load bukan bukti mart
sudah siap. Pengaturan ini dipertahankan oleh setup SQL fakta.

Kompilasi JIT dinonaktifkan khusus fungsi pembentukan fakta untuk mengurangi
biaya kompilasi per tanggal. Perbandingan proyeksi sebelum/sesudah pada 58.928
baris menghasilkan nilai identik. Run ini menggunakan tujuh tanggal per batch
commit; checkpoint tetap atomik dan dapat dilanjutkan tanpa menggandakan fakta.

### Status terakhir: load dijeda atas permintaan pengguna

Pada 2026-10-08T15:07:20.567523+07:00, runner dihentikan dengan membatalkan batch aktif.
Commit terakhir mencakup tanggal sampai **2025-10-30**, sebanyak
**29,825,212 baris fakta**. Checkpoint berikutnya adalah
**2025-10-31**; batas akhir sumber tetap 2026-09-01.
Seluruh event sudah di-staging, tetapi pembentukan fakta masih parsial. View KPI
final tetap tertahan; jangan menyatakan full backfill selesai.

Status runner dicatat `paused` di `logs/hop-fact/latest.json`. Pesan pembatalan
pada log Hop adalah penghentian yang diminta pengguna. Tidak ada resume otomatis.
Jika pengguna meminta melanjutkan, jalankan runner yang sama; checkpoint akan
melanjutkan tanggal berikutnya tanpa membaca ulang seluruh sumber.
