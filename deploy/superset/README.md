# Superset dashboard ePresensi

Instance khusus proyek ini: Superset 6.1.0, image dasar dipin ke digest dan driver
psycopg2-binary 2.9.10. Tidak memakai container atau metadata Superset proyek lain.

## Akses

- Dari server: http://127.0.0.1:8090
- Username: `dashboard_admin`.
- Password ada di `.env.dashboard`, key `SUPERSET_ADMIN_PASSWORD`; file mode 600,
  diabaikan Git. Jangan menyalin kredensial ke dokumentasi atau frontend.
- Dari komputer lain, gunakan SSH tunnel:
  `ssh -L 8090:127.0.0.1:8090 piramida@ALAMAT_SERVER`, lalu buka localhost:8090.
- Data tersedia melalui menu **Datasets**: `analytics.attendance_daily` dan
  `analytics.attendance_department_daily`, database **ePresensi OLAP**.
- Empat saved metrics: attendance_rate, ontime_rate, absence_rate, average_lateness.
  Pilih periode **2026-08-01 sampai sebelum 2026-09-01** untuk baseline dummy.

Ini menyiapkan koneksi dan dataset, bukan empat dashboard visual/Next.js/SSO.
Guest role masih tanpa permission; pembatasan departemen dan embedding publik
menunggu mapping role SSO serta domain aplikasi. Local admin memiliki akses seluruh
departemen untuk setup, bukan akun untuk dibagikan ke pengguna manajemen.

## Menjalankan ulang / instalasi pada lingkungan ini

Jalankan dari root repo; `.env` harus menunjuk OLAP yang tepat dan network
`olap_default` harus sudah ada dari docker-compose.yml utama.

```bash
.venv/bin/python -m scripts.provision_dashboard --apply
docker compose --env-file .env.dashboard -f docker-compose.dashboard.yml build
docker compose --env-file .env.dashboard -f docker-compose.dashboard.yml up -d
docker compose --env-file .env.dashboard -f docker-compose.dashboard.yml ps -a
```

Provisioner tidak merotasi password existing. Jika `.env.dashboard` hilang setelah
instalasi, pulihkan dari penyimpanan secret/backup; jangan membuat ulang sembarang
password karena metadata PostgreSQL, akun admin, serta secret enkripsi Superset
harus tetap cocok. Backup file secret secara terpisah dan aman.

Init menjalankan migrasi metadata, role init, membuat admin jika belum ada,
serta mendaftarkan koneksi dan dataset secara idempotent. Untuk memperbarui
registrasi dataset setelah mengedit bootstrap:

```bash
docker compose --env-file .env.dashboard -f docker-compose.dashboard.yml run --rm --no-deps superset-init python /app/dashboard/bootstrap.py
```

Metadata tersimpan pada named volume `epresensi-dashboard_superset_metadata`.
Jangan gunakan `down -v` kecuali memang ingin menghapus seluruh metadata dashboard.
Database metadata tidak dipublikasikan ke port host. Superset bergabung dengan
network OLAP dan memakai `postgres-olap:5432`; aplikasi tidak memakai localhost
container untuk mengakses PostgreSQL OLAP.

## Kontrak dataset

`dashboard_reader` mendapat SELECT pada dua view saja, tanpa akses langsung
ke fact/dimensi. Default transaksi read-only dan timeout query 30 detik.
View detail tidak mengekspos nama, NIP, alasan izin, atau raw timestamp presensi.
`pegawai_id` tetap disertakan untuk distinct headcount, sehingga akses dataset
detail masih harus diberi scope sesuai SSO sebelum dibuka ke user manajemen.

Agregat menyimpan numerator/denominator; metrik menghitung SUM/SUM agar persentase
lintas tanggal/departemen tetap tertimbang. View biasa mengikuti data committed
ETL tanpa refresh materialized view. Belum ada index tambahan (optimasi P2).

Target attendance/ontime/absence/lateness NULL dan status TARGET_NOT_SET.
Variance/status pencapaian belum dihitung. Formula masih baseline:
- attendance: hadir / expected workday;
- ontime: tepat waktu / hadir dengan evaluasi waktu;
- absence: tidak absen tanpa izin / expected workday;
- average lateness: menit terlambat / jumlah hari terlambat.

Tidak ada target dummy. Hari berjalan harus diberi label provisional di dashboard;
view tidak mengklaim hari sudah final hanya berdasarkan tanggal atau ETL SUCCESS.
Status aktif pegawai, shift lintas hari dan histori mutasi belum ditambahkan.

## Scheduler dan verifikasi 21 September 2026

- Incremental: 10.30 dan 01.00 WIB, konfigurasi runtime sudah dimuat.
- Master: 01.30 WIB, `--recent-days 2 --reconcile --apply`, sudah enabled/active.
- Master melengkapi pegawai tanpa event dan merekonsiliasi sumber. Monitor durasi:
  offset 30 menit bukan dependency; jika incremental masih aktif, shared lock
  membuat master gagal cepat dan retry terbatas. Jadwal dapat perlu digeser sesuai
  pengukuran beban aktual. Eksekusi master produksi pertama belum diverifikasi.
- Pada sumber dummy statis, master hari berjalan dapat menghasilkan TIDAK_ABSEN
  untuk pegawai dummy: jangan menafsirkannya sebagai operasional nyata.

Validasi: kedua container healthy, init exit 0; KPI Agustus melalui role baca
80%, 87,5%, 10%, 32,49 menit; seluruh target NULL; SELECT fact mentah,
UPDATE fact dan CREATE TABLE ditolak meskipun transaksi read-write dicoba.

## Tahap integrasi aplikasi

SSO/session → backend Next.js → guest token Superset → Embedded SDK → OLAP.
Gunakan scope departemen dari server, bukan parameter browser. Konfigurasikan
allowed embedding domains, permission guest, RLS, HTTPS/reverse proxy dan secret
service account saat domain/SSO tersedia. Rate limiting instance lokal ini masih
memakai memory per worker; siapkan shared storage sebelum exposure produksi.

Referensi resmi:
- https://superset.apache.org/docs/configuration/configuring-superset/
- https://superset.apache.org/admin-docs/installation/docker-builds/
- https://superset.apache.org/user-docs/using-superset/embedding/

Verifikasi API Superset juga berhasil untuk kedua dataset: empat KPI Agustus
sama dengan hasil SQL OLAP. Filter departemen diuji, dan rentang kosong
menghasilkan KPI NULL, bukan nol. Provisioner berhasil dijalankan ulang tanpa
mengganti password atau mengubah data fact.
