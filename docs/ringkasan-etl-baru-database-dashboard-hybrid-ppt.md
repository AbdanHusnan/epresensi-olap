# Ringkasan ETL Baru dan Database Dashboard Hybrid untuk Laporan PPT

Status laporan: **29 Oktober 2026, Asia/Jakarta**. Bahan presentasi ini mencakup ETL baru, struktur database staging dan mart, hasil pengujian terisolasi, serta rencana dashboard hybrid.

**Pesan utama:** kontrak data dan pipeline baru telah diuji sampai serving dengan 2.400 pegawai dan 757 departemen. Infrastruktur hybrid telah tersedia. Pemuatan bisnis pada database aktif, pembuatan dashboard, dan pengujian pengalaman pengguna masih menjadi tahap berikutnya.

# Slide 1 Tujuan dan capaian

- Menyediakan data presensi yang dapat ditelusuri dari transaksi sumber hingga KPI dashboard.
- Menyatukan seluruh shift dalam satu record pegawai per tanggal pelaporan.
- Memisahkan pengolahan aturan bisnis, penyimpanan fakta, agregasi, dan tampilan.
- Menyiapkan dashboard operasional kepala departemen dan dashboard analitis pimpinan instansi.

**Capaian:** schema dan pipeline baru tersedia; pengujian raw ke curated serta curated ke serving lulus dalam database uji; environment Next.js, Metabase, dan Superset telah diverifikasi.

# Slide 2 Kontrak kebutuhan terbaru

| Area | Ketentuan |
|---|---|
| Populasi | Seluruh pegawai aktif pada snapshot tanggal pelaporan, termasuk tanpa event |
| Grain utama | Satu pegawai × satu tanggal pelaporan |
| Banyak shift | Tetap satu hitungan masuk dan satu hitungan pulang per pegawai per hari |
| Waktu aktual | Masuk pertama dari MIN check-in; pulang terakhir dari MAX check-out |
| Izin | Transaksi approved yang valid; tipe 1 bebas kedua sisi, tipe 2 bebas masuk, tipe 3 bebas pulang |
| Histori departemen | Mengikuti snapshot tanggal terkait; mutasi baru tidak otomatis mengubah tanggal sebelumnya |
| Status hasil | Provisional sampai atribusi tanggal dan kelengkapan data tervalidasi |

Jumlah event berbeda dari jumlah pegawai. MIN/MAX tidak digunakan sebagai bukti durasi kerja. Penjumlahan lintas tanggal berunit **pegawai-hari**, bukan pegawai unik.

# Slide 3 Alur ETL baru

```text
Database sumber pengujian: dbabsen_restore
                  ↓ ekstraksi Apache Hop
staging_bkd.raw
Nilai asli sumber dan metadata ekstraksi
                  ↓ manifest perubahan dan transformasi
staging_bkd.curated
Populasi + event + izin → rekap pegawai harian
                  ↓ outbox batch dengan payload immutable
mart_bkd.mart_kehadiran
Dimensi + fact_kehadiran_daily
                  ↓ rebuild partisi tanggal dan departemen
mart_bkd.serving
Agregasi + view KPI + status kelengkapan
                  ↓ koneksi BI read-only
Metabase / Superset → website Next.js
```

Bagian sampai serving telah diuji pada database terisolasi. Integrasi visual BI di website merupakan tahap rencana. Integrasi manifest producer raw untuk operasi rutin masih perlu diselesaikan.

# Slide 4 Susunan database baru

| Database | Schema atau fungsi | Peran |
|---|---|---|
| staging_bkd | raw | Menyimpan salinan data sumber dan metadata ekstraksi |
| staging_bkd | curated | Menetapkan populasi, event harian, izin, dan measure |
| staging_bkd | etl_control | Kontrol pemrosesan dan pengiriman perubahan ke mart |
| mart_bkd | mart_kehadiran | Dimensi dan fakta presensi harian |
| mart_bkd | serving | Agregasi, view dashboard, dan status tanggal |
| mart_bkd | etl_control | Checkpoint batch dan bukti commit penerimaan |
| hybrid_metabase | Metadata aplikasi BI | Konfigurasi dan definisi konten Metabase |
| hybrid_superset | Metadata aplikasi BI | Konfigurasi dan definisi konten Superset |

Database staging berada pada container epresensi-staging-postgres; mart pada epresensi-mart-postgres. Kedua database metadata BI berada di layanan PostgreSQL terpisah dari penyimpanan data presensi.

Database uji dipisahkan dari database aktif. Kelulusan pengujian tidak berarti data bisnis sudah dimuat ke target aktif.

# Slide 5 Bentuk tabel curated

Seluruh tabel berikut berada dalam schema **staging_bkd.curated**.

| Tabel | Satuan satu baris | Isi utama |
|---|---|---|
| cur_employee_population_daily | Pegawai × tanggal | Status aktif, departemen, basis dan waktu snapshot |
| cur_event_attendance | Satu event sumber | ID transaksi, tipe masuk/pulang, waktu, tanggal pelaporan, referensi shift, flag review |
| cur_attendance_event_daily | Pegawai × tanggal | Jumlah event, flag masuk/pulang, masuk pertama, pulang terakhir |
| cur_leave_daily | Pengajuan × pegawai × tanggal izin | Approval, tipe transaksi, validitas, pembebasan masuk/pulang |
| cur_attendance_daily | Pegawai × tanggal | Hasil gabungan populasi, event, izin, measure, dan kualitas data |

**Alur penggabungan:** event diringkas per pegawai-tanggal; izin diekspansi menjadi harian lalu diringkas per pegawai-tanggal; keduanya digabung dengan snapshot populasi. Cara ini mencegah banyak event atau pengajuan izin menggandakan KPI.

Kunci cur_attendance_daily adalah **(pegawai_id, tanggal)**. Detail sumber tetap tersedia untuk audit.

# Slide 6 Bentuk model mart dan serving

| Objek | Kunci atau grain | Fungsi |
|---|---|---|
| mart_kehadiran.dim_calendar | Tanggal, key YYYYMMDD | Referensi waktu pelaporan |
| mart_kehadiran.dim_pegawai | Surrogate key dan interval efektif | Identitas serta versi dimensi pegawai |
| mart_kehadiran.dim_departemen | Surrogate key dan interval efektif | Identitas serta versi dimensi departemen |
| mart_kehadiran.fact_kehadiran_daily | PK pegawai_id_sumber + tanggal | Fakta harian dan 12 measure dari curated |
| serving.agg_kehadiran_departemen_harian | PK tanggal + departemen_key | Penjumlahan measure per departemen-hari |
| serving.attendance_date_state | Per tanggal | Kelengkapan populasi, delivery, dan status penutupan |
| serving.v_kehadiran_departemen_harian | Departemen-hari | Measure, persentase, nama, dan kualitas |
| serving.v_kehadiran_instansi_harian | Instansi-hari | Total seluruh departemen dan persentase instansi |
| serving.v_departemen_filter | ID departemen sumber | Pilihan filter lintas versi dimensi |

Relasi utama: **dim_calendar, dim_pegawai, dan dim_departemen → fact_kehadiran_daily → agregasi departemen-harian → view KPI**.

Fact menyimpan key dimensi, ID sumber, tanggal, status aktif, bukti event, izin, 12 measure, batch, dan flag kualitas. Departemen belum terpetakan memakai **UNKNOWN key 0**. Lookup dimensi harus cocok dengan tanggal efektif.

Agregasi instansi menjumlah seluruh departemen termasuk UNKNOWN. Detail pegawai membaca fact; kartu, tren, dan perbandingan membaca serving.

# Slide 7 KPI dashboard

| KPI utama | Definisi ringkas |
|---|---|
| Pegawai Aktif | Pegawai aktif dalam snapshot harian |
| Absen Masuk | Pegawai aktif dengan minimal satu check-in |
| Absen Pulang | Pegawai aktif dengan minimal satu check-out |
| Tidak Absen Masuk | Pegawai aktif tanpa check-in dan tidak dibebaskan izin masuk |
| Tidak Absen Pulang | Pegawai aktif tanpa check-out dan tidak dibebaskan izin pulang |
| Pegawai Izin | Pegawai aktif dengan minimal satu izin valid |

Enam measure pendukung: wajib masuk, wajib pulang, bebas masuk, bebas pulang, pemenuhan wajib masuk, dan pemenuhan wajib pulang.

- Persentase masuk/pulang = jumlah yang memiliki event ÷ jumlah aktif.
- Persentase pemenuhan = pemenuhan wajib ÷ jumlah wajib setelah pengecualian izin.
- Persentase periode dihitung dari jumlah pembilang dibagi jumlah penyebut.
- Penyebut nol menghasilkan NULL dan ditampilkan sebagai “—”.
- Izin dan event dapat beririsan sehingga tidak boleh dipaksakan menjadi kategori yang saling eksklusif.

# Slide 8 Keandalan pipeline incremental

1. Perubahan curated dicatat bersama payload batch yang tidak berubah setelah commit.
2. Consumer memproses batch secara berurutan dan memvalidasi kontrak.
3. Dimensi, fact, agregasi terdampak, receipt, dan checkpoint disimpan dalam satu transaksi mart.
4. Partisi tanggal-departemen lama dan baru dibangun ulang saat terjadi koreksi.
5. Pipeline acknowledgement memeriksa receipt committed melalui koneksi baru sebelum staging ditandai terkirim.

**Jaminan yang diuji:** replay tidak menggandakan angka; no-op tidak menulis ulang hasil bisnis; kegagalan target melakukan rollback; retry memulihkan proses; penghapusan membersihkan partisi kosong.

Workflow utama: curated_to_serving.hwf. Apply dan acknowledgement berada pada dua child pipeline terpisah. Bootstrap dan capture pada database aktif belum diaktifkan.

# Slide 9 Ringkasan hasil pengujian

| Pengujian | Cakupan | Hasil |
|---|---|---|
| Dua shift source/raw ke curated | Dua pegawai, empat event, enam eksekusi Hop | Lulus; dua shift tetap measure masuk/pulang 1/1 |
| Pengecualian izin | 15 kasus awal, koreksi tipe, approval/revocation, overlap, no-op, rollback/retry | Lulus |
| Bulk raw ke curated | 2.400 pegawai, 757 departemen, 12 skenario, sembilan eksekusi Hop | Lulus; koreksi tepat 400 pegawai-hari, 2.000 baris lainnya tidak ditulis ulang |
| Uji kecil curated ke serving | Incremental, mutasi, event terlambat, replay, immutable payload, UNKNOWN, delete | Lulus; 15 eksekusi Hop sukses dan satu kegagalan sengaja untuk uji rollback |
| Bulk curated ke serving | 2.400 fact dan 757 agregasi departemen-harian | Lulus; nol selisih measure/partisi, nol batch pending |
| Environment hybrid | Build, health, koneksi read-only, login administrator BI | Lulus; lima container sehat dan tiga endpoint HTTP 200 |

Bulk downstream memakai hasil curated bulk yang sudah dikoreksi. Tes tersebut tidak menjalankan ulang raw ke curated. Fixture event dan izin merupakan simulasi dalam lingkungan pengujian.

# Slide 10 Angka hasil bulk dan batas bukti

Hasil satu tanggal pengujian setelah koreksi izin:

| Indikator | Nilai |
|---|---:|
| Pegawai aktif | 2.400 |
| Absen masuk | 1.000 |
| Absen pulang | 1.000 |
| Tidak absen masuk | 1.000 |
| Tidak absen pulang | 600 |
| Pegawai izin | 1.200 |
| Wajib masuk / pulang | 1.800 / 1.400 |
| Bebas masuk / pulang | 600 / 1.000 |
| Pemenuhan wajib masuk / pulang | 800 / 800 |

Pengukuran awal bulk downstream: pemanggilan Hop **11,180 detik** termasuk startup JVM; durasi internal workflow **2,674 detik**. Satu pengukuran query KPI instansi **3,030 ms** dan perbandingan departemen **3,606 ms**.

Angka ini berasal dari satu tanggal dan satu pengukuran lokal. Ini belum membuktikan waktu render dashboard, performa histori besar, atau kapasitas pengguna bersamaan. Hasil data tetap provisional; pairing lintas malam dan finalisasi tanggal belum selesai.

# Slide 11 Rencana dashboard hybrid

Website **Next.js** menjadi antarmuka yang menyematkan dashboard BI. **Metabase OSS** dan **Apache Superset OSS** dibandingkan menggunakan definisi KPI, data, filter, dan skenario yang setara.

| Pengguna | Jenis dashboard | Isi |
|---|---|---|
| Kepala departemen | Operasional | KPI harian, tren, dan daftar pegawai dalam departemennya |
| Pimpinan instansi | Analitis | Ringkasan periode, tren instansi, dan perbandingan departemen |

Periode awal yang diusulkan: hari ini untuk kepala departemen, bulan berjalan untuk pimpinan instansi. Akses pimpinan ke detail pegawai masih perlu keputusan.

Urutan pekerjaan: lengkapi website dan role preview → buat dashboard setara pada kedua BI → integrasikan embedding → uji KPI dan pembatasan departemen → benchmark → pilih engine.

Target performa yang diusulkan: initial completion p95 maksimal 3 detik dan perubahan filter p95 maksimal 1 detik. Target ini belum merupakan hasil pengukuran. Kebenaran data dan isolasi departemen wajib lulus sebelum penilaian performa.

# Slide 12 Rancangan infrastruktur hybrid

| Layanan | Tanggung jawab | Kondisi |
|---|---|---|
| Next.js | Website dan integrasi embedding | Scaffold dan endpoint health tersedia; fitur dashboard belum dibuat |
| Metabase | Kandidat dashboard pertama | Service dan koneksi data tersedia; belum ada dashboard |
| Superset | Kandidat dashboard kedua | Service dan koneksi data tersedia; belum ada chart/dashboard |
| PostgreSQL metadata | Database terpisah untuk kedua BI | Persistent volume, akun terpisah |
| Redis | State filter/form dan infrastruktur cache Superset | Cache hasil query belum diaktifkan |
| PostgreSQL mart | Penyedia fact dan serving | BI memakai akun khusus read-only |

**Jaringan:** web berada di frontend; BI terhubung ke jaringan mart; metadata dan Redis berada pada jaringan internal tanpa port publik. Web tidak mengakses database presensi langsung.

**Batas resource prototype:** web 512 MiB/1 CPU; masing-masing BI 2 GiB/2 CPU; metadata 768 MiB/1 CPU; Redis 256 MiB/0,5 CPU.

Prototype berjalan di server Docker pengujian dengan port host loopback. Produksi direncanakan pada server terpisah setelah pemilihan engine, integrasi identitas, HTTPS, backup, dan persiapan pemulihan.

# Slide 13 Status dan langkah berikutnya

| Status | Komponen |
|---|---|
| Sudah tersedia dan diuji | Schema curated/mart/serving, pipeline baru pada database uji, rekonsiliasi bulk, environment hybrid |
| Belum diaktifkan pada target aktif | Load bisnis curated dan mart, bootstrap/capture downstream |
| Perlu penyelesaian kontrak | Atribusi lintas malam, kelengkapan snapshot, kebijakan penutupan tanggal |
| Perlu implementasi dashboard | KPI/chart, embedding, role preview, pembatasan departemen |
| Perlu evaluasi | Benchmark histori dan concurrency, usability, pemilihan BI |
| Tahap produksi berikutnya | Login/SSO, role terpercaya, deployment server live, backup dan recovery |

**Urutan tindak lanjut:** selesaikan manifest producer dan kesiapan data → validasi kebijakan tanggal → rencanakan aktivasi data → implementasikan dashboard setara → uji kebenaran dan scope → benchmark dan pilih engine → siapkan produksi.

# Referensi teknis

Berkas sumber berada di workspace **/home/piramida/OLAP**. Semua referensi berikut berfokus pada implementasi baru.

- Kontrak KPI: docs/data-lineage-dashboard-kpi.md
- Mapping raw ke curated: docs/sttm-source-to-curated-kehadiran.md
- Mapping curated ke serving: docs/sttm-curated-to-serving-kehadiran.md
- DDL curated: sql/staging/20261028_curated_population_v2.sql, dengan pembaruan kontrak izin mengikuti STTM terbaru
- DDL mart dan serving: sql/mart/20261028_attendance_daily.sql
- Outbox dan consumer: sql/staging/20261028_mart_outbox.sql; sql/mart/20261028_mart_incremental_etl.sql
- Workflow downstream: hop/MART_PIPELINE.md
- Uji dua shift: tests/e2e_two_shift_20261028/README.md
- Uji izin: tests/leave_exemptions_20261028/results.txt
- Bulk curated: tests/bulk_attendance_20261028/README.md
- Uji kecil mart: tests/mart_small_20261029/README.md
- Bulk mart: tests/mart_bulk_20261029/README.md
- Plan hybrid: docs/hybrid-dashboard-prototype-plan.md
- Infrastruktur dan hasil verifikasi: deploy/hybrid/README.md
- Definisi deployment: docker-compose.hybrid.yml

Laporan pengujian 29 Oktober menjadi acuan status eksekusi terbaru. Dokumen kontrak digunakan untuk definisi data dan aturan bisnis.

