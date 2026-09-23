# Attendance Dashboard

Next.js shell untuk empat dashboard Superset. KPI, chart, tabel, dan filter native
Superset ditampilkan melalui Embedded SDK; tidak ada query database di Next.js.

| Rute | Dashboard | Environment UUID |
|---|---|---|
| `/` | executive-overview | SUPERSET_OVERVIEW_ID |
| `/attendance` | attendance-analysis | SUPERSET_ATTENDANCE_ID |
| `/departments` | department-performance | SUPERSET_DEPARTMENTS_ID |
| `/lateness-absence` | lateness-absence | SUPERSET_LATENESS_ID |

## Pratinjau lokal tanpa SSO

SSO ditunda sesuai instruksi. Pratinjau memberikan akses seluruh departemen dan
hanya bekerja jika NODE_ENV=development, DASHBOARD_LOCAL_PREVIEW=true, serta
Origin dan Host cocok dengan APP_ORIGIN localhost. Jangan mempublikasikan dev
server melalui reverse proxy; pembatasan ini bukan pengganti autentikasi.
Build produksi menolak penerbitan guest token sampai integrasi session tersedia.

1. Jalankan `npm ci` dan salin `.env.example` ke `.env.local`.
2. Pada setiap dashboard Superset, aktifkan **Embed** dan isi allowed domains
   dengan `http://127.0.0.1:3002`. Masukkan embedded UUID ke env sesuai tabel.
3. Siapkan service account khusus dengan permission `can_grant_guest_token`
   dan `can_read` (CSRF) pada `SecurityRestApi`; masukkan username/password hanya di `.env.local`.
4. Konfigurasikan role `DashboardGuest` pada Superset untuk membaca chart/dashboard
   yang diperlukan. Pastikan akses embedded dan query kedua dataset analytics
   berhasil; jangan berikan Admin, SQL Lab, atau permission tulis.
5. Periksa konfigurasi CSP/frame-ancestors Superset mengizinkan origin Next.js.
   Gunakan secret guest JWT tersendiri yang kuat di Superset.
6. Set `DASHBOARD_LOCAL_PREVIEW=true`, lalu `npm run dev`.

Buka http://127.0.0.1:3002. Untuk akses dari komputer lain:

```bash
ssh -L 3002:127.0.0.1:3002 -L 8090:127.0.0.1:8090 piramida@ALAMAT_SERVER
```

Kedua tunnel diperlukan karena iframe dimuat langsung oleh browser.
SUPERSET_URL harus dapat diakses browser; SUPERSET_INTERNAL_URL dipakai backend.

## Alur dan validasi

`POST /api/dashboards/[key]/guest-token` menerima hanya key yang terdaftar.
Backend login ke Superset dengan service account dan meminta token untuk satu
embedded dashboard. Token tidak di-cache; SDK memperbaruinya otomatis. Kredensial
service account tetap di server. UI menyediakan status loading, error, dan retry.
Halaman shell dapat dibuka tanpa session; akses data dikendalikan endpoint token.

```bash
npm run lint
npm run typecheck
node --test tests/*.test.mjs
npm run build
```

Pengujian policy mencakup development eksplisit, penolakan produksi, origin/host
asing, dan konfigurasi invalid. Verifikasi integrasi setelah konfigurasi instance:
buka keempat halaman, ubah filter tanggal/departemen, pastikan Department
Performance hanya memiliki filter tanggal, lalu biarkan terbuka lebih dari lima
menit untuk memeriksa refresh token. Periksa juga respons 403 untuk origin asing.

## SSO berikutnya

Ganti gerbang preview dengan session server terverifikasi dan derive scope dari
role SSO. Tambahkan RLS `departemen_id` untuk middle management ke permintaan token;
jangan menerima scope dari browser. `/login` masih placeholder. `/api/health`
hanya liveness aplikasi, bukan kesehatan Superset/OLAP.

Konfigurasi lokal instance sudah diterapkan melalui `../scripts/configure_next_embedding.py`:
empat embedded UUID, allowed domain localhost, service account khusus, dan guest
role baca minimum. `.env.local` disimpan mode 600 dan diabaikan Git. Ulangi dari
root repo dengan `.venv/bin/python scripts/configure_next_embedding.py --apply`.
Script khusus instance ini menggunakan ID dashboard 1–4 dan tidak merotasi password
akun existing. Konfigurasi frame dan guest signing key berada di
`../deploy/superset/superset_config.py`; perubahan file itu memerlukan restart Superset. Referensi SDK: https://superset.apache.org/user-docs/using-superset/embedding/

## Hasil verifikasi lokal

Lint, TypeScript, build produksi dan lima pengujian policy lulus. Browser headless
berhasil menampilkan data di seluruh halaman: Attendance 80,00% / 87,50%, tabel
25 departemen, Lateness 32,49 menit / Absence 10,00% pada Agustus 2026.
Overview mengikuti konfigurasi existing tanpa default filter periode; hasilnya
tidak selalu sama dengan halaman yang dibatasi Agustus. Native filter tetap
berasal dari masing-masing dashboard Superset.

Token Overview berhasil membaca dashboard 1 dan ditolak saat membaca dashboard 2;
origin asing atau hilang ditolak 403. Ada pesan console nonblocking dari instance
Superset: service-worker.js 404 dan penyimpanan warna Department Performance 403.
Data/chart tetap tampil; guest tidak diberi permission tulis hanya untuk menyimpan
warna. Ini dapat ditinjau terpisah pada konfigurasi dashboard Superset.

Refresh token terverifikasi dengan memajukan clock browser lebih dari lima menit
(request token sukses bertambah dari satu menjadi dua). Pemilihan Badan Pendapatan
Daerah Provinsi Jawa Timur dan Apply filters juga berhasil menampilkan ulang chart
Attendance dengan scope departemen yang dipilih.

## Mart agregasi aktif

Keempat halaman sudah memakai dataset Superset berbasis mart fisik. Median initial
load lokal turun menjadi sekitar 3,6–4,1 detik; filter departemen sekitar 1,5–1,9
detik, filter tanggal Department Performance sekitar 0,94 detik. Refresh mart
berjalan atomik bersama commit ETL. Lihat [alur, validasi, dan recovery](../docs/attendance-marts.md).
