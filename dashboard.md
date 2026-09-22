# Blueprint Web App Dashboard Presensi

## 1. Tujuan
Membangun web app dashboard presensi yang terpisah dari web app admin/operasional dan digunakan oleh top/middle management.

## 2. Boundary Arsitektur — LOCKED

```text
OLTP
  │
  │ ETL / Pipeline
  ▼
PostgreSQL OLAP
  │
  ▼
Dashboard Web App Baru
  │
  └── Login via SSO
```

Keputusan:
- Dashboard web app terpisah dari aplikasi admin.
- Dashboard hanya membaca PostgreSQL OLAP.
- Dashboard tidak mengakses OLTP secara langsung.
- Data masuk ke OLAP melalui pipeline OLTP → OLAP.
- SSO digunakan untuk akses ke aplikasi dashboard.

## 3. Technology Stack — LOCKED

- Next.js
- React
- TypeScript
- SSO existing
- Apache Superset Embedded
- PostgreSQL OLAP
- Docker
- Nginx

Pembagian tanggung jawab:
- Next.js/React: application shell, SSO/session, routing, sidebar, layout.
- Superset: KPI, filter, chart, tabel, visual analytics, dan query ke OLAP.

## 4. Navigasi — LOCKED

Sidebar memiliki 4 halaman:

1. Overview
2. Attendance
3. Department Performance
4. Lateness & Absence

## 5. KPI Utama — LOCKED

1. Attendance Rate
2. On-Time Rate
3. Absence Rate
4. Average Lateness

Konsep KPI menggunakan pola:

```text
Actual → Target → Variance → Status
```

Metric lama seperti Total Pegawai, Total Masuk, Total Pulang, Total Izin, WFO, dan WFH tetap digunakan sebagai supporting/context metrics.

## 6. Filter — LOCKED

| Halaman | Filter Tanggal | Filter Departemen |
|---|---|---|
| Overview | Ya | Ya |
| Attendance | Ya | Ya |
| Department Performance | Ya | Tidak |
| Lateness & Absence | Ya | Ya |

Catatan:
- Filter tanggal wajib tersedia pada semua halaman.
- Department Performance tidak memakai filter departemen karena halaman tersebut digunakan untuk membandingkan antar departemen.

## 7. Wireframe Konten — LOCKED

### 7.1 Overview

Konten:
- Filter tanggal/periode
- Filter departemen
- Attendance Rate
- On-Time Rate
- Absence Rate
- Average Lateness
- Attendance Trend
- Attendance Composition
- WFO vs WFH
- Supporting metrics

### 7.2 Attendance

Konten:
- Filter tanggal/periode
- Filter departemen
- Attendance Rate
- On-Time Rate
- Attendance Rate Trend
- On-Time Rate Trend
- Status Kehadiran
- WFO vs WFH

### 7.3 Department Performance

Konten:
- Filter tanggal/periode
- Attendance Rate by Department
- Tabel perbandingan departemen berisi minimal:
  - Attendance Rate
  - On-Time Rate
  - Absence Rate
  - Average Lateness

Tidak ada filter departemen pada halaman ini.

### 7.4 Lateness & Absence

Konten:
- Filter tanggal/periode
- Filter departemen
- Average Lateness
- Absence Rate
- Lateness Trend
- Lateness Distribution
- Absence Trend

## 8. Struktur Superset — LOCKED

Empat dashboard Superset:

```text
superset/
├── executive-overview
├── attendance-analysis
├── department-performance
└── lateness-absence
```

Mapping ke Next.js:

```text
/                  → executive-overview
/attendance        → attendance-analysis
/departments       → department-performance
/lateness-absence  → lateness-absence
```

## 9. Struktur Folder Next.js — BASELINE LOCKED

```text
attendance-dashboard/
├── src/
│   ├── app/
│   │   ├── (auth)/
│   │   ├── (dashboard)/
│   │   ├── api/
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── components/
│   │   ├── ui/
│   │   ├── layout/
│   │   └── dashboard/
│   ├── features/
│   │   ├── overview/
│   │   ├── attendance/
│   │   ├── departments/
│   │   └── lateness/
│   ├── lib/
│   │   ├── auth/
│   │   └── superset/
│   ├── hooks/
│   ├── types/
│   └── config/
├── public/
├── infra/
│   ├── superset/
│   ├── nginx/
│   └── docker/
├── .env.example
├── package.json
├── tsconfig.json
└── README.md
```

## 10. Data Source — BELUM DI-LOCK

Baseline awal yang sudah diketahui:
- `fact_kehadiran`
- `fact_perizinan`

Namun mapping sumber data detail **sengaja belum di-lock**.

Agent diminta melakukan brainstorming dan validasi berdasarkan keseluruhan project untuk menentukan:
- tabel/dimensi tambahan yang diperlukan;
- join yang tepat;
- field mapping untuk setiap KPI dan visual;
- apakah perlu view/materialized view/mart tambahan;
- apakah `fact_kehadiran` dan `fact_perizinan` sudah cukup untuk seluruh kebutuhan dashboard.

Agent tidak perlu mengubah blueprint UI/arsitektur yang sudah locked hanya karena melakukan data-source mapping.

## 11. SSO Role Mapping — PENDING

SSO sudah menjadi mekanisme authentication yang dipilih.

Yang belum ditentukan:
- nama role actual pada instansi;
- mapping role untuk top management;
- mapping role untuk middle management;
- scope akses departemen berdasarkan role/user.

Hal ini akan divalidasi lebih lanjut dari konfigurasi SSO existing.

## 12. Scope untuk Agent

Agent dapat melanjutkan pada area berikut:

1. Validasi data source untuk setiap KPI dan visual.
2. Validasi relasi tabel dan dimensi yang diperlukan.
3. Menentukan query/view/mart yang dibutuhkan Superset.
4. Menentukan implementasi koneksi Superset ke OLAP.
5. Menentukan implementasi embedding Superset ke Next.js.
6. Menentukan detail implementasi setelah role SSO tersedia.

Agent **tidak perlu mengubah** keputusan berikut kecuali ditemukan blocker teknis nyata:
- aplikasi dashboard terpisah dari admin app;
- dashboard hanya membaca OLAP;
- Next.js/React/TypeScript sebagai web app;
- Superset Embedded sebagai dashboard engine;
- 4 halaman utama;
- KPI utama;
- aturan filter per halaman;
- sidebar sebagai navigasi utama.

## 13. Status Blueprint

**LOCKED:**
- boundary arsitektur;
- technology stack;
- struktur aplikasi;
- 4 halaman;
- KPI;
- filter;
- wireframe konten;
- pembagian Next.js vs Superset.

**PENDING:**
- SSO role mapping;
- detail data-source mapping.
