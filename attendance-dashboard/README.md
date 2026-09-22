# Attendance Dashboard

Kerangka Next.js App Router + React + TypeScript mengikuti `../dashboard.md`.
Saat ini hanya shell tampilan: tidak membaca database atau menampilkan angka dummy.
KPI placeholder bukan angka nol. Target tetap belum ditetapkan.

## Menjalankan lokal

```bash
npm ci
cp .env.example .env.local
npm run dev
```

Buka http://127.0.0.1:3002. Binding lokal menghindari bentrok port layanan existing.
Untuk akses dari komputer lain: `ssh -L 3002:127.0.0.1:3002 piramida@ALAMAT_SERVER`.

```bash
npm run lint
npm run typecheck
npm run build
npm start
```

## Rute

| Halaman | Rute | Superset dashboard | Filter nanti |
|---|---|---|---|
| Overview | / | executive-overview | Tanggal, departemen |
| Attendance | /attendance | attendance-analysis | Tanggal, departemen |
| Department Performance | /departments | department-performance | Tanggal |
| Lateness & Absence | /lateness-absence | lateness-absence | Tanggal, departemen |

`/login` adalah placeholder SSO, bukan login aktif. `/api/health` hanya memeriksa
liveness web app, bukan kesehatan OLAP/Superset. Filter dan visual analitik nantinya
berasal dari Superset; tidak ada filter dekoratif yang berpura-pura bekerja.

## Batas integrasi

- Next.js: shell, navigasi, session SSO dan endpoint guest token.
- Superset: KPI, filter, chart, tabel dan query OLAP.
- Tidak ada koneksi OLTP atau kredensial database pada aplikasi ini.
- Konfigurasi Superset ada di `src/lib/superset/config.ts` dan hanya server-side.
- Belum ada guest-token endpoint atau SDK aktif: tunggu dashboard UUID, SSO,
  service account, allowed domains, dan scope departemen yang tervalidasi.
- Lindungi rute data/embedding dengan session sebelum menampilkan data aktual.
- Jangan memakai kredensial admin dari `.env.dashboard` untuk browser.

Folder infra disiapkan sebagai tempat integrasi nanti. Deployment Superset aktif
masih dikelola di `../docker-compose.dashboard.yml`; lihat
[runbook Superset](../deploy/superset/README.md). Tidak ada deploy web app otomatis.

Referensi scaffold: https://nextjs.org/docs/app/getting-started/installation
