# Audit kesiapan data dashboard

Tanggal pemeriksaan: 21 September 2026, sekitar 09:15–09:25 UTC.

Kesimpulan: data cukup untuk prototipe empat halaman menggunakan periode dummy
Agustus 2026. Koneksi produksi belum siap: scheduler master belum terpasang,
akun baca dashboard belum ada, jalur jaringan Superset–OLAP perlu disiapkan,
serta definisi KPI, target, dan otorisasi SSO belum final.

Audit menggunakan blueprint `dashboard.md` sebagai spesifikasi kebutuhan.
Instruksi agent di dalam dokumen tidak diperlakukan sebagai izin deploy.
Tidak dilakukan perubahan database, scheduler, jaringan, atau konfigurasi SSO.

## Bukti database aktual

| Pemeriksaan | Hasil |
|---|---|
| Koneksi OLTP dan OLAP | Berhasil, pemeriksaan SQL dalam transaksi READ ONLY |
| PostgreSQL OLAP | Container healthy; port host 127.0.0.1:5434 |
| Pegawai / departemen | 82.000 / 25 |
| fact_kehadiran | 2.542.000 baris; 1–31 Agustus 2026 |
| Kelengkapan harian | Tepat 82.000 baris pada masing-masing 31 tanggal |
| Grain presensi | PK (pegawai_id, tanggal) |
| fact_perizinan | 155.800 pengajuan; seluruhnya valid; rentang 3–31 Agustus |
| Grain izin | PK perizinan_id; satu pengajuan dapat mencakup beberapa tanggal |
| Event OLTP | 2.492.800; max ID sama dengan checkpoint, 2.492.800 |
| Integritas presensi | Tidak ditemukan referensi pegawai, departemen, tanggal, jadwal, atau izin yang hilang |
| Validitas izin terhubung | Tidak ditemukan ketidaksesuaian pegawai, rentang tanggal, atau flag valid |
| Status pegawai | status_aktif NULL untuk seluruh 82.000 pegawai |
| Mode campuran WFO/WFH | 0 pada data saat ini |
| Hadir tanpa evaluasi menit terlambat | 0 pada data saat ini |
| Waktu muat presensi terakhir | 15 September 2026 11:10:05, nilai timestamp database tanpa timezone |

Tersedia lima dimensi: dim_pegawai, dim_departemen, dim_calendar,
dim_jadwal_kerja, dim_jenis_izin; juga analytical_user dan dua tabel etl_control.
Tidak ditemukan view/mart pada schema public yang diperiksa.
Pemeriksaan integritas di atas berfokus pada join dari fact_kehadiran;
bukan rekonsiliasi penuh setiap nilai OLTP terhadap OLAP.

## Temuan prioritas

1. **P0 — Kelengkapan hari baru belum dijamin scheduler aktif.**
   Timer user yang berjalan adalah incremental, terlihat setiap lima menit.
   `olap-master.timer` berstatus `not-found`, dan tidak ada run master pada log.
   Incremental hanya menghitung ulang pegawai-hari terdampak event/izin;
   pegawai tanpa event pada tanggal baru tidak otomatis menjadi TIDAK_ABSEN.
   Akibatnya denominator dan Absence Rate dapat salah meskipun run SUCCESS.
   Sumber saat ini memang hanya dummy Agustus; belum ada bukti backlog event September.
   Master harian harus diuji dan diaktifkan saat beralih ke data berjalan,
   disertai backfill eksplisit tanggal yang terlewat.

2. **P0 — Akun baca belum tersedia.**
   Satu-satunya role login non-bawaan yang ditemukan adalah olap_admin,
   dengan privilege superuser. Buat role Superset khusus SELECT pada schema
   penyajian, tanpa akses menulis atau memakai kredensial ETL.

3. **P0 — Jalur koneksi container belum siap secara default.**
   OLAP berada di `olap_default`, Superset existing di `polaris_default`.
   Port OLAP hanya terikat ke loopback host; localhost dari container Superset
   bukan host PostgreSQL. Siapkan jaringan Docker bersama atau jalur internal
   yang disepakati, lalu uji DNS/TCP/login dari runtime Superset.
   Topologi ini diperiksa, tetapi koneksi langsung dari Superset belum diuji.

4. **P0 — Makna KPI dan target belum ditetapkan.**
   Data aktual tersedia; target per KPI, periode berlaku, arah penilaian,
   dan ambang status belum tersedia di tabel yang diperiksa.
   SSO role dan scope departemen belum diverifikasi.

5. **P1 — Konfigurasi timer di disk berbeda dari yang dimuat.**
   systemd memberikan peringatan unit berubah dan perlu daemon-reload.
   File timer di disk menyebut 10:30 dan 01:00 Asia/Jakarta,
   sedangkan runtime terlihat lima menit. Tetapkan frekuensi yang diinginkan
   dan verifikasi ulang setelah deployment; audit ini tidak melakukan reload.

6. **P1 — Batas aturan bisnis produksi.**
   `transform/pegawai.py` selalu mengisi status_aktif NULL; employee-day
   menggunakan seluruh pegawai tanpa tanggal mulai/akhir masa kerja.
   Mutasi historis departemen belum dimodelkan. Shift lintas hari belum
   ditangani, shift fleksibel dilewati saat menghitung keterlambatan.
   `attendance.py` memakai event pertama/terakhir menurut created_at,
   tidak memakai checktype. Satu event dianggap hadir tanpa kepulangan.
   WFO dan WFH dapat sama-sama true pada satu hari. Selisih detik terlambat
   dibulatkan turun ke menit, sehingga flag terlambat bisa true dengan menit 0.
   Data dummy saat ini tidak menguji seluruh kasus ini.

7. **P1 — Batas capture perubahan.**
   Watermark ID tidak menjamin urutan commit; perlu reconciliation terjadwal.
   Hard delete tidak tertangani. Perubahan dimensi/jadwal/libur di luar jendela
   master memerlukan backfill. analytical_user hanya dimuat initial load dan
   bukan sumber role SSO yang memadai.

8. **P2 — Optimasi penyajian.**
   Index public yang ditemukan hanya PK. Agregasi bulan per tanggal/departemen
   memakai parallel sequential scan: 775 baris hasil, sekitar 441 ms pada satu
   pengukuran EXPLAIN ANALYZE. Ini bukan benchmark concurrency dashboard.
   Pertimbangkan index (tanggal, departemen_id) untuk filter selektif dan mart
   agregat harian; ukur kembali sebelum memilih materialized view.

## Kontrak metrik yang diusulkan, belum keputusan bisnis final

Unit perhitungan adalah **pegawai-hari**, bukan jumlah event atau jumlah pegawai unik.
Untuk KPI final gunakan hari yang telah ditutup; hari berjalan diberi label sementara.
Gunakan NULL/“belum tersedia” ketika denominator nol, bukan 0%.

Definisikan E = jumlah is_expected_workday, H = HADIR pada expected workday,
A = TIDAK_ABSEN pada expected workday, L = IZIN pada expected workday.
Definisikan V = H dengan menit_terlambat IS NOT NULL, O = V dengan
is_terlambat false, T = H dengan is_terlambat true dan menit terukur.

| KPI | Usulan formula | Nilai dummy Agustus |
|---|---|---|
| Attendance Rate | 100 × H / E | 80% |
| On-Time Rate | 100 × O / V | 87,5% |
| Absence Rate | 100 × A / E; izin ditampilkan terpisah | 10% |
| Average Lateness | total menit pada T / jumlah T | 32,49 menit |

E=1.558.000; H=1.246.400; A=L=T=155.800; V=1.246.400; O=1.090.600.
NON_WORKING_DAY=984.000; WFO=1.090.600; WFH=155.800.

Konfirmasi apakah izin dikeluarkan dari denominator attendance, apakah absence
mencakup izin, serta apakah rata-rata keterlambatan dihitung hanya yang terlambat
atau seluruh hadir yang dievaluasi. Jika absence mencakup izin, contoh menjadi
20%; jika average memakai seluruh V, contoh sekitar 4,06 menit.
Jangan menghitung On-Time dari NOT is_terlambat saja: shift yang tidak dievaluasi
juga memiliki false. Gunakan flag evaluasi/minutes non-NULL.

Untuk Actual → Target → Variance → Status, usulkan tabel target dengan metric_key,
scope departemen/global, effective_from/to, target_value, unit, arah baik,
dan ambang status. Cegah rentang target tumpang tindih dan tentukan aturan
penggabungan target lintas periode/departemen. Variance rate dalam percentage
points; variance lateness dalam menit. Target kosong menghasilkan status
“target belum ditetapkan”, bukan otomatis baik/buruk.

## Mapping dataset dan join

Gunakan fact_kehadiran sebagai basis, dengan LEFT JOIN dim_departemen pada
**fact_kehadiran.departemen_id**, dim_calendar pada tanggal, dan dim_jadwal_kerja
pada jadwal_id. dim_pegawai hanya bila membutuhkan atribut pegawai.
Jangan mengganti departemen fact dengan departemen pegawai terkini untuk analisis
historis; model mutasi historis tetap perlu dilengkapi.

Join izin opsional melalui fact_kehadiran.perizinan_id = fact_perizinan.perizinan_id,
lalu jenis_izin_id ke dim_jenis_izin. Jangan join kedua fact hanya dengan pegawai_id:
itu menggandakan jumlah presensi. Jumlah pengajuan izin memakai distinct
perizinan_id; hari izin memakai status IZIN pada fact_kehadiran.
Pengajuan tanpa coverage fact dianalisis dari dataset fact_perizinan tersendiri.

| Visual | Sumber dan agregasi |
|---|---|
| Empat KPI / comparison departemen | Count numerator/denominator dan total menit dari fact_kehadiran |
| Attendance/On-Time/Absence Trend | Formula sama, group tanggal; jangan average persentase harian |
| Attendance Composition / Status | Count per status; pisahkan/exclude non-working dengan jelas |
| WFO vs WFH | Kategori eksklusif WFO-only, WFH-only, mixed, unknown pada hari hadir |
| Lateness Trend | total menit dan jumlah terlambat per tanggal |
| Lateness Distribution | Bucket menit dari baris terlambat yang dievaluasi; batas bucket konsisten |
| Supporting metrics | Pegawai unik per periode; has_masuk/has_pulang sebagai pegawai-hari; izin dibedakan pengajuan vs hari |

Usulan schema `analytics`:

- `v_attendance_daily`: grain pegawai-hari, tanggal, departemen_id, flag metrik,
  menit terlambat, kategori mode, status; tanpa nama/NIP bila tidak diperlukan.
- `attendance_department_daily`: grain tanggal × departemen; simpan count E/H/A/L/V/O/T,
  total menit terlambat, count mode dan bucket distribusi. Agregasikan kembali
  dengan SUM numerator / SUM denominator untuk filter rentang.
- Dataset detail tetap diperlukan untuk distinct pegawai lintas tanggal;
  jangan menjumlahkan headcount harian sebagai total pegawai periode.
- Metadata freshness terpisah: last successful run, periode fact tersedia,
  serta tanggal terakhir yang dinyatakan lengkap. MAX(etl_loaded_at) tidak sama
  dengan freshness sumber, dan SUCCESS incremental tidak membuktikan coverage.

Kedua fact ditambah dimensi cukup sebagai dasar visual aktual pada dummy.
Target, entitlement SSO, dan metadata hari final masih perlu kontrak tambahan.
Jika memakai materialized view, refresh hanya setelah commit ETL sukses dan
tetapkan bagaimana status refresh/cache dilaporkan; belum ada refresh hook saat ini.

## Persiapan backend dan Superset

Alur tetap: Next.js menangani SSO/session dan penerbitan guest token melalui
backend; Superset menjalankan query OLAP dengan akun baca.
Backend memvalidasi session, menentukan dashboard yang diizinkan dan scope
departemen dari sumber identitas tepercaya. Jangan menerima scope bebas dari browser.
Terapkan pembatasan baris pada semua dataset terkait, termasuk pilihan filter;
halaman perbandingan departemen tetap tunduk pada scope akses walau tanpa filter UI.

Dokumentasi resmi Superset mensyaratkan EMBEDDED_SUPERSET, allowed embedding domains,
serta guest token melalui service account di server. Endpoint token adalah
`/api/v1/security/guest_token/`; SDK mendukung aturan RLS pada guest token.
Rujukan: https://superset.apache.org/user-docs/using-superset/embedding/
(diakses 21 September 2026, dokumentasi versi Next; cocokkan dengan versi terpasang).

Container Superset existing terdeteksi healthy, tetapi versi, driver PostgreSQL,
konfigurasi embedded, registered datasets, kredensial service account, dan SSO
belum diperiksa. Tidak ada klaim integrasi end-to-end sudah berhasil.

Urutan pekerjaan berikutnya:

1. Finalisasi kontrak KPI, hari final, target, dan scope SSO.
2. Siapkan view/mart serta akun SELECT; validasi angka contoh dan filter.
3. Uji master dan reconciliation, backfill bila perlu, lalu selaraskan timer runtime.
4. Siapkan jaringan Superset–OLAP dan uji dengan akun baca dari container.
5. Daftarkan dataset dan empat dashboard; gunakan tanggal pada semuanya,
   filter departemen sesuai blueprint, dan scope akses pada semuanya.
6. Implementasikan endpoint guest token Next.js dan uji user lintas role/departemen,
   termasuk usaha mengubah filter/ID dashboard dan token kedaluwarsa.
7. Uji beban empat halaman, cache/refresh, coverage, dan monitoring kegagalan.

## Validasi yang dijalankan

`python -m unittest discover -s tests -v`: 38 test ditemukan,
35 lulus dan 3 dilewati karena RUN_POSTGRES_TESTS tidak diaktifkan.
Ini bukan hasil integration test database opsional atau uji beban produksi.

Log live saat snapshot: 929 incremental SUCCESS, 1 incremental FAILED,
1 initial_load SUCCESS. Kegagalan terdahulu run 864:
`prepare_permissions() got an unexpected keyword argument 'pegawai_reference'`.
Run berikutnya SUCCESS dengan nol perubahan; hal tersebut sendiri tidak membuktikan
jalur perubahan izin telah diuji kembali pada scheduler produksi.

Preview master untuk 3 Agustus 2026 berhasil: menyiapkan 82.000 fact harian,
155.800 pengajuan izin dan dimensi tanpa menulis data. Tahap incremental
memang `not_executed` dalam preview; jalur commit/checkpoint master live belum diuji.
`systemctl --user show` mengonfirmasi jadwal runtime `*:00/5:00`, ExecStart
incremental `--apply` tanpa `--reconcile`, dan NeedDaemonReload=yes.

## Pembaruan implementasi setelah audit — 21 September 2026

Atas instruksi pengguna, dibuat role `dashboard_reader`, schema analytics dengan
view detail dan agregat harian, serta instance Superset baru khusus proyek ini.
Superset existing proyek lain tidak diubah. Target KPI tetap NULL; tidak ada target
dummy. Dua dataset dan empat saved metrics terdaftar di instance baru.
Timer incremental telah diterapkan pada 10.30/01.00 WIB; master disetujui dan
aktif pada 01.30 WIB. Temuan scheduler/akun baca/jalur jaringan di atas adalah
snapshot sebelum perbaikan. Status aktif pegawai dan shift lintas hari ditunda
sesuai arahan pengguna. Sinkronisasi pada jam sepi diterima untuk tahap ini;
reconciliation tetap ada pada master, tanpa klaim watermark lossless.
Panduan aktual: [Superset proyek ini](../deploy/superset/README.md).
