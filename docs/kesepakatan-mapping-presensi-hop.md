# Kesepakatan mapping presensi untuk Apache Hop

Acuan diskusi sampai 7 Oktober 2026, waktu Asia/Jakarta. Tujuannya adalah melanjutkan mapping kolom OLTP ke dimensi dan fakta tanpa kehilangan keputusan bisnis, bukti sumber, dan pertanyaan terbuka. Mapping dim_departemen, dim_pegawai, dim_shift gabungan, dan dimensi tanggal (fisik dim_calendar) telah dilanjutkan ke implementasi Hop atas permintaan pengguna. Keputusan final dim_shift pada akhir dokumen menggantikan rancangan pemisahan shift/jadwal; grain aktifnya satu m_jadwal.id. Target terkini adalah epresensi_analytics_hop_dev.public; bagian implementasi lama di bawah disimpan sebagai riwayat dan digantikan oleh pembaruan target pada akhir dokumen.

## Dasar desain dan prioritas keputusan

Baseline: [Business Process and Grain Design](../BKD_Presensi_Business_Process_and_Grain_Design.docx). Keputusan pengguna yang lebih baru dalam dokumen ini memperjelas atau menggantikan asumsi sebelumnya. Bedakan keputusan bisnis dari usulan teknis yang belum disepakati.

Database sumber inspeksi adalah **dbabsen_restore**, menggunakan koneksi OLAP proyek dengan nama database diubah secara eksplisit. Jangan menganggap OLTP default dalam `.env` sebagai database backup ini. Jangan menyimpan kredensial dalam dokumentasi.

Tujuan migrasi: memindahkan proses Python ke Apache Hop setelah mapping dan transformasinya disepakati. Tidak sekadar menyalin asumsi pipeline Python lama.

## Aturan bisnis yang disepakati

| Topik | Keputusan pengguna |
|---|---|
| Grain fakta | Satu pegawai × satu tanggal kerja |
| Penentu shift | Departemen/dinas mengatur shift pegawai |
| Shift mandatory | Menurut informasi pengguna dari owner aplikasi, shift berkeyword regular adalah shift wajib dinas. Pencarian data mencakup ejaan REGULAR dan REGULER tanpa membedakan kapital |
| Status aktif | Shift aktif ditampilkan pada aplikasi presensi; admin menonaktifkan shift ketika tidak digunakan lagi |
| Histori | Shift yang nonaktif sekarang tetap diperhitungkan untuk masa ketika shift tersebut aktif. Tidak boleh memfilter histori hanya dengan status aktif saat ini |
| Hari kerja normal | Senin–Jumat |
| Sabtu dan Minggu | Bukan kewajiban hadir normal. Event presensi tetap bisa terjadi untuk keperluan di kantor; ketiadaan event tidak dianggap absen |
| Libur | Hari libur/off yang diketahui tidak dianggap absen |
| Satu reguler berlaku | Pegawai → departemen → shift reguler yang berlaku → jadwal harinya |
| Beberapa reguler berlaku | Seluruhnya menjadi alternatif. Presensi pada salah satu alternatif memenuhi kewajiban; alternatif yang tidak dipilih tidak menambah ketidakhadiran |
| Izin | Izin approved yang relevan tetap menghasilkan IZIN meskipun ada presensi |
| Kehadiran | Tanpa izin approved, presensi yang memenuhi aturan kehadiran menghasilkan HADIR |
| Tanpa keterangan | Pada kandidat tanggal wajib kerja: tidak ada presensi pada alternatif yang relevan dan tidak ada izin approved menghasilkan TANPA_KETERANGAN |
| Waktu | Ambil masuk dan pulang aktual; keterlambatan dihitung dengan membandingkan masuk aktual dengan jam masuk jadwal yang digunakan |

Pengguna menyebut alternatif shift sebagai XOR. Makna yang dijelaskan adalah cukup hadir pada salah satu pilihan. Ini tidak menetapkan bahwa hadir pada beberapa pilihan harus dianggap tidak hadir. Penanganan beberapa shift/event pada tanggal kerja yang sama masih perlu aturan teknis.

Filter aktif berlaku sesuai tanggal evaluasi. Status aktif saat ini bisa digunakan untuk snapshot saat ini; periode historis memerlukan bukti masa berlaku. Pemilihan satu shift secara arbitrer tidak dibenarkan.

## Hubungan sumber OLTP

| Sumber | Referensi | Bukti dan batas |
|---|---|---|
| m_pegawai.departemen | m_departemen.id | Foreign key; organisasi pegawai pada master |
| m_shift.departemen_id | m_departemen.id | Foreign key nullable; pemilik shift, bukan otomatis organisasi pegawai pada transaksi |
| m_jadwal.jenis | m_shift.id | Foreign key; rincian jadwal per shift dan hari |
| t_checkinout.pegawai_id | m_pegawai.id | Foreign key |
| t_checkinout.jadwal_id | m_jadwal.id | Relasi logis tanpa foreign key; cocok pada seluruh 10.000 event sampel terakhir, bukan validasi seluruh tabel |
| t_checkinout.work_code | m_shift.id | Pada 10.000 event sampel terakhir cocok dengan ID shift dan m_jadwal.jenis; tanpa foreign key |
| t_perizinan.pegawai_id | m_pegawai.id | Relasi logis; perlu validasi identitas terhadap user_id → m_user.pegawai_id |
| t_libur_shift.pegawai_id | m_pegawai.id | Foreign key; pengecualian libur per tanggal |
| m_shift.event_id | t_pegawai_lokasi.id | Kandidat relasi logis: 437 kecocokan ke record is_event=1; semua record yang cocok memiliki pegawai NULL, sehingga bukan roster individual |

Departemen dibedakan berdasarkan **ID**, bukan nama. Nama unit dapat sama. Kode departemen juga tersedia untuk penelusuran. Pewarisan shift dari parent atau OPD induk belum ditetapkan.

Satu shift bisa mempunyai jadwal Senin sampai Minggu. Pada pemeriksaan sebelumnya tidak ditemukan duplikasi kombinasi m_jadwal.jenis + hari. Adanya jadwal Sabtu/Minggu tidak mengubah keputusan hari kerja normal Senin–Jumat.

## Pembentukan fakta yang direncanakan

1. Tentukan periode analisis dan populasi pegawai. Batas masa aktif pegawai secara historis masih perlu sumber yang memadai.
2. Bentuk kandidat pegawai–tanggal, kemudian evaluasi Senin–Jumat dan pengecualian libur.
3. Hubungkan organisasi pegawai ke alternatif shift REGULAR/REGULER yang berlaku pada tanggal tersebut.
4. Hubungkan shift ke jadwal harinya. Beberapa alternatif hanya memperbanyak baris kerja sementara, bukan baris fakta final.
5. Ambil event masuk/pulang. Gunakan jadwal transaksi dan periksa silang identitas shift; jangan menganggap dua event selalu berarti satu masuk dan satu pulang.
6. Pasangkan event ke tanggal kerja. Usulan untuk shift lintas tengah malam: gunakan tanggal mulai shift. Contoh Jumat malam sampai Sabtu pagi tetap tanggal kerja Jumat; aturan pemasangan detail belum final.
7. Jabarkan rentang izin ke tanggal cakupan dan validasi approval, jenis izin, serta tumpang tindih. Ringkas sebelum join agar fakta tidak berganda.
8. Pada hari wajib kerja, utamakan IZIN jika ada izin approved; lalu HADIR jika ada presensi yang memenuhi aturan; sisanya TANPA_KETERANGAN setelah jendela evaluasi selesai.
9. Hitung keterlambatan terhadap jadwal yang digunakan pada presensi. Waktu yang tidak tersedia tidak diganti dengan nilai buatan.
10. Ringkas menjadi satu pegawai–tanggal kerja, lookup dimensi, dan simpan referensi sumber untuk audit.

Hari libur/off dan Sabtu–Minggu tidak menghasilkan TANPA_KETERANGAN. Pilihan menyimpan hari tersebut dalam fakta yang sama dengan is_wajib_kerja=false, atau dalam keluaran terpisah, **belum disepakati**. Nama status NON_WORKING_DAY juga belum menjadi keputusan final.

Departemen tanpa kandidat reguler yang teridentifikasi tidak otomatis menghasilkan tanpa keterangan. Penugasan dinas induk, shift bersama, dan periode historis yang tidak lengkap perlu ditangani secara eksplisit.

## Rancangan mapping awal untuk dilanjutkan

Nama kolom berikut merupakan rancangan, bukan skema fisik yang sudah disetujui.

| Target | Sumber | Transformasi dan batas |
|---|---|---|
| dim_pegawai | m_pegawai + m_previleges | Identitas, NIP sebagai teks, kategori pegawai; masa aktif dan perubahan historis belum lengkap |
| dim_departemen | m_departemen | Nama target disepakati menggantikan dim_dinas; ID, kode, nama unit, hierarki parent/OPD; jangan menggabungkan unit hanya karena nama sama |
| dim_tanggal | Kalender lengkap + m_hari_libur | Hari, bulan, tahun, penanda Senin–Jumat, libur kalender; deduplikasi tanggal libur |
| dim_shift | m_shift | ID, nama, departemen pemilik, reguler/fleksibel, status dan versi historis jika tersedia |
| fact_kehadiran.pegawai_key | Identitas pegawai | Lookup dimensi; tipe key belum final |
| fact_kehadiran.tanggal_key | Tanggal kerja | Normalisasi lintas hari masih perlu keputusan detail |
| fact_kehadiran.departemen_key | Organisasi pada tanggal kejadian | Nama diselaraskan dengan dim_departemen; prioritas departemen transaksi vs master dan histori mutasi belum final |
| fact_kehadiran.shift_key | Jadwal/shift pada event presensi | Hari tanpa event dengan beberapa alternatif tidak boleh diberi shift sembarang |
| fact_kehadiran.waktu_masuk dan waktu_pulang | t_checkinout | Checktype 1/2 dipetakan Masuk/Keluar pada view v_absen_lengkap; kode lainnya perlu ditangani |
| fact_kehadiran.jadwal_mulai dan jadwal_selesai | Jam transaksi, m_jadwal, histori master | Prioritas sumber acuan historis masih perlu validasi |
| fact_kehadiran.status_kehadiran | Izin, event, kandidat hari wajib | IZIN lebih dahulu dari HADIR; TANPA_KETERANGAN sebagai sisa hari wajib |
| fact_kehadiran.is_terlambat dan durasi_terlambat | Masuk aktual vs jadwal | Selisih positif dalam menit; pembulatan, toleransi, shift fleksibel, dan perlakuan pada status IZIN belum final |
| fact_kehadiran.mode_kerja | t_checkinout.is_wfh | Kandidat 0=WFO, 1=WFH; sesuai baseline NULL pada hari izin; konflik nilai per hari perlu aturan |
| Kolom audit dan kualitas | ID sumber, jumlah event, waktu proses | Untuk menelusuri jadwal hilang, event tidak lengkap, konflik, dan pemrosesan ulang |

Surrogate key dan waktu proses untuk dim_departemen telah diterima dalam kelanjutan pembahasan di bawah. SCD, key dimensi lain, tabel pendukung alternatif shift, serta penyimpanan snapshot jam jadwal belum menjadi keputusan final. Fakta perizinan terpisah belum diputuskan; izin dapat lebih dahulu menjadi masukan klasifikasi fakta kehadiran.

## Mapping dim_departemen: kelanjutan 6 Oktober 2026

Pengguna menyetujui kelanjutan mapping dan usulan sebelumnya, serta memilih nama **dim_departemen**, menggantikan dim_dinas. Tahap awal ini menyelesaikan mapping dan validasi sumber; kemudian pengguna meminta implementasi pipeline dim_departemen sampai selesai sebelum membahas tabel lain. Nama kolom diselaraskan memakai departemen.

Grain snapshot: satu unit organisasi per m_departemen.id. Untuk versi historis, strategi SCD dan sumber masa berlaku masih terbuka; snapshot sekarang tidak boleh dianggap sebagai keadaan seluruh periode lampau.

| Sumber | Target | Tipe rancangan | Aturan |
|---|---|---|---|
| Dibentuk warehouse | departemen_key | bigint | Surrogate key stabil; tidak dibentuk ulang setiap load |
| m_departemen.id | departemen_id_sumber | integer | NOT NULL, unik untuk rancangan snapshot; identitas sumber |
| m_departemen.kode | kode_departemen | varchar(40) | Salin teks, pertahankan NULL dan nol di depan |
| m_departemen.nama_departemen | nama_departemen | varchar(200) | Nullable; jangan menggabungkan nama yang sama |
| m_departemen.kode_lengkap | kode_lengkap | text | Salin; sampel berisi jalur nama organisasi, bukan semata kode |
| m_departemen.parent | parent_id_sumber | integer | Salin mentah, termasuk 0/NULL; validasi referensi terpisah |
| m_departemen.opd_parent | opd_induk_id_sumber | integer | Salin mentah; nilai orphan tetap dapat diaudit |
| m_departemen.unit_kerja_induk | unit_kerja_induk_id_sumber | integer | Salin nullable; tidak diisi otomatis dari kolom hierarki lainnya |
| Timestamp proses ETL | waktu_proses | timestamptz | Audit waktu pemrosesan; bukan awal masa berlaku organisasi |

Tipe data, aturan kualitas, dan bentuk load di atas merupakan rancangan teknis berdasarkan persetujuan melanjutkan; semantik hierarki yang belum terbukti tidak dianggap sudah dikonfirmasi owner. Loader lama menggunakan departemen_id, sehingga implementasi nanti memerlukan penyelarasan eksplisit; jangan langsung menjalankan DDL pengganti pada tabel lama.

### Bukti audit sumber

Audit SELECT read-only atas seluruh **6.892** baris dbabsen_restore.public.m_departemen, dalam snapshot transaksi repeatable-read. Laporan dapat dibuat ulang di `logs/reports/audit-mapping-departemen.json`. Skrip ulang: `.venv/bin/python scripts/audit_departemen_mapping.py`.

| Kolom | Hasil |
|---|---|
| parent | 4.958 referensi ke unit lain cocok, 1.932 NULL, 2 bernilai 0; tidak ada orphan atau siklus |
| opd_parent | 5.885 referensi ke unit lain cocok, 48 menunjuk dirinya sendiri, 958 NULL, 1 orphan |
| unit_kerja_induk | 6.890 NULL; hanya unit 36078 dan 36523 menunjuk 30160 (Dinas Kesehatan) |
| nama_departemen | 553 NULL; 183 kelompok nama yang berulang |
| kode | Tidak NULL/kosong dan unik pada snapshot; 1.957 kode mengandung HAPUS |
| kode_lengkap | 3 NULL; 88 kelompok nilai berulang |

Orphan OPD: departemen **31964 → 1407**, sedangkan ID 1407 tidak ditemukan pada master. Jangan menghapus departemen 31964 atau mengganti referensinya secara tebakan. LEFT JOIN lookup mempertahankan baris utama; reference raw tetap disimpan, hasil lookup yang tidak ditemukan tetap NULL dan dicatat sebagai masalah kualitas.

Dari 5.934 nilai opd_parent yang terisi, 4.200 berada pada rantai parent termasuk unit itu sendiri; **1.734 berada di luar rantai tersebut**. Hanya 6 sama dengan titik terminal parent ketika penelusuran berhenti pada 0/NULL. Perhitungan ini tidak membuktikan bahwa terminal tersebut adalah OPD bisnis. Dengan demikian, parent, opd_parent, dan unit_kerja_induk dipertahankan terpisah. Self-reference OPD tidak otomatis dianggap korup; dapat menandai unit pengelompokan, tetapi maknanya belum dikonfirmasi. Tidak ada siklus OPD multiunit dalam audit.

### Aturan mapping dan penerimaan

- Ekstrak semua departemen tanpa filter nama, HAPUS, atau kewajiban shift.
- Simpan NULL nama apa adanya; label tampilan seperti “Nama belum tersedia” bukan nilai pengganti pada dimensi.
- Pertahankan parent=0 sebagai nilai sumber; jangan menyatakan 0/NULL pasti akar bisnis tanpa bukti tambahan.
- Lookup validasi hierarki memakai LEFT JOIN ke m_departemen.id; setiap lookup tidak boleh menambah atau mengurangi baris utama.
- Target snapshot harus merepresentasikan seluruh 6.892 ID pada snapshot audit ini, di luar baris teknis unknown jika kelak ditambahkan. Jumlah aktual divalidasi ulang ketika load dilakukan.
- Duplikasi ID sumber atau penggandaan akibat join adalah kegagalan validasi. Nama/kode_lengkap berulang bukan alasan deduplikasi.
- Jangan membentuk foreign key fisik langsung dari referensi mentah sebelum orphan dan sentinel ditangani; key lookup dimensi bisa dirancang terpisah.
- m_departemen.created_at tidak dipakai sebagai valid_from. Dua belas kolom sumber lainnya ditandai di luar mapping inti pada lembar review, bukan dihapus dari sumber.
- Kebijakan is_allow_wfh bukan mode kerja aktual harian. Pewarisan shift berdasarkan hierarki belum ditetapkan.

Mapping tujuh kolom sumber telah diisi pada [lembar review](oltp-mapping-review.csv); dua kolom teknis hasil pembentukan dicatat pada tabel di atas. Mapping dimensi lain dan fakta belum dianggap final oleh audit ini.

### Implementasi pipeline dim_departemen

Atas instruksi pengguna, pipeline tersedia dalam proyek Hop `presensi`:
`pipelines/dim_departemen.hpl`, environment `presensi-local`, run configuration `local`.
Sumber: `dbabsen_restore.public.m_departemen`. Target:
`epresensi_analytics.hop.dim_departemen`.

Schema `hop` memisahkan model baru dari `public.dim_departemen` lama yang memiliki
25 baris, nama NOT NULL, dan referensi dari dim_pegawai, dim_jadwal_kerja,
fact_perizinan, serta fact_kehadiran. Tidak dilakukan migrasi fact/dashboard lama.

Pipeline Table Input → Insert / Update membaca tujuh kolom mapping tanpa filter.
Lookup memakai departemen_id_sumber. Database membentuk departemen_key pada insert;
key dipertahankan pada update. waktu_proses diisi default database pada insert dan
trigger pada update; baris identik dilewati. Ini pemuatan keadaan terkini dengan
update atribut, bukan rekonstruksi histori/SCD2. Tidak ada penghapusan otomatis.
Commit per 1.000 baris; kegagalan bisa menyisakan batch yang sudah selesai dan dapat
dipulihkan dengan rerun setelah penyebab diperbaiki. Hindari run bersamaan.

Artefak, langkah deploy, dan validasi tersedia di [panduan pipeline](../hop/README.md).
Hasil pemeriksaan seluruh kolom dan rerun dicatat di
`logs/reports/validation-hop-dimensions.json`.
Kredensial berada di file lokal yang diabaikan Git dan environment volume Hop,
bukan pada metadata koneksi di repository. Akun sumber hanya membaca m_departemen;
akun target dibatasi pada tabel dim_departemen dan sequence terkait.

## Bukti data dan batas historis

m_pegawai.status merujuk m_previleges, dengan kategori PNS, PTT, PPPK, PPPK Paruh Waktu, dan Non-Aktif. Status sekarang tidak menentukan seluruh masa aktif historis. m_pegawai.status_shift berisi 1, 2, 5, 6 atau NULL, bukan ID m_shift yang sudah terbukti. JSON attrs yang diperiksa tidak memuat field roster atau penugasan shift.

Audit perubahan m_shift dan m_jadwal yang ditemukan mencakup Januari–Agustus 2026. Ada bukti jam jadwal berubah, misalnya 14.00 menjadi 09.00. Kelengkapan audit dan keadaan awal sebelum perubahan perlu diverifikasi untuk merekonstruksi interval berlaku. created_at bukan otomatis awal kewajiban kerja atau awal masa berlaku jadwal.

Pada sampel terakhir 10.000 event, 9.975 pasangan jam masuk/pulang cocok dengan master saat diperiksa; 25 tidak memenuhi kecocokan itu. Gunakan temuan ini untuk memvalidasi prioritas snapshot transaksi, bukan menganggap master selalu benar untuk histori.

## Hasil pemeriksaan shift reguler

Snapshot 6 Oktober 2026, berdasarkan hubungan langsung m_shift.departemen_id ke m_departemen.id; mencakup unit berkode HAPUS dan semua status organisasi yang ada. Pencarian nama: regular|reguler, case-insensitive.

| Kondisi | Jumlah |
|---|---:|
| Departemen/unit diperiksa | 6.892 |
| Tepat satu reguler aktif | 1.316 |
| Beberapa reguler aktif | 75 |
| Memiliki reguler tetapi tidak ada yang aktif | 3.468 |
| Tidak ada keyword reguler secara langsung | 2.033 |
| Shift matching seluruh status | 5.607 |
| Shift matching aktif | 1.486 |
| Shift matching nonaktif | 4.121 |
| Shift matching tanpa departemen | 10, seluruhnya nonaktif |

Sebanyak 72 dari 75 departemen dengan beberapa reguler aktif memiliki beberapa jadwal pada hari yang sama. Ini menjadi alternatif sesuai keputusan pengguna, bukan alasan menggandakan fakta. Seluruh 1.316 kandidat tunggal memiliki record jadwal, tetapi jam dan pengecualian liburnya tetap perlu validasi.

Contoh ID departemen 30364 memiliki reguler pagi/siang juru masak serta pagi/siang/malam pelayanan. Jangan menganggap label kelompok dalam nama sebagai penugasan pegawai tanpa aturan tambahan.

## Posisi rekap aplikasi

t_posting adalah rekap aplikasi per departemen dan rentang tanggal, berisi JSON pegawai serta rincian harian dan total periode. Rentangnya dapat satu hari, beberapa hari, atau sebulan. Format JSON bervariasi menurut periode.

Pada contoh yang diperiksa, field shift di tingkat pegawai bernilai seperti 5, sementara jadwal_masuk berada di detail Datang. Contoh hari alpha tidak memuat jadwal wajib. Karena itu t_posting menjadi **bahan rekonsiliasi hasil**, bukan bukti expected shift. Cakupan periode, posting tumpang tindih, versi/finalitas, dan pemaknaan field masih perlu pemeriksaan.

## Pemulihan sumber dan kualitas data

Database restore awal tidak lengkap. Pada 5 Oktober 2026 dipulihkan tujuh tabel yang sebelumnya kosong dari dump asli, tanpa menimpa data yang sudah ada: t_libur_shift 440.437; t_log_lokasipegawai 360.318; t_log_pegawai 6.088.501; t_pegawai_lokasi 8.512; t_posting 12.840; t_sales 149.835; titik_lokasi3 2.273 record. Empat trigger audit asli pada m_shift dan m_jadwal juga dipulihkan; trigger tersebut mencatat perubahan, bukan memilih shift pegawai.

Verifikasi jumlah, constraint, sequence, dan trigger tersedia dalam [hasil verifikasi restore](../backups/restore-missing-20261005/verification.json). Kesimpulan lama bahwa tabel-tabel tersebut kosong tidak lagi menggambarkan sumber saat ini.

t_libur_shift mencakup 4.630 pegawai; ditemukan 1.433 kelompok duplikat pegawai–tanggal, 5 tanggal NULL, dan 421 tanggal sebelum 2000 atau mulai 2100. Data sumber dipertahankan; deduplikasi dan penanganan anomali harus ditentukan pada transformasi. t_pegawai_lokasi mempunyai 3 rentang tanggal terbalik.

## Keputusan teknis yang masih terbuka

- Check-in tanpa check-out tetap pending menurut dokumen awal; kriteria event cukup untuk HADIR belum final.
- Check-out tanpa check-in, presensi berulang, beberapa shift per tanggal, serta pemilihan pasangan event.
- Masa aktif historis pegawai, mutasi departemen, dan penanganan kode departemen HAPUS.
- Kelengkapan histori shift/jadwal, interval berlaku, dan perlakuan sebelum audit tersedia.
- Shift bersama tanpa departemen, pewarisan jadwal induk, serta presensi di luar pilihan reguler.
- Arti jadwal jam masuk sama dengan pulang atau 00.00; tidak otomatis dianggap libur.
- Prioritas izin terhadap libur pada tanggal yang sama, izin sebagian hari, dinas luar, koreksi lupa absen, dan pengajuan bertumpuk.
- Makna approval=false bersama status/approval_at. Pipeline lama menganggap false=ditolak, tetapi default false belum membuktikan penolakan.
- Aturan pembulatan keterlambatan, fleksibilitas/toleransi, timezone, presensi manual, dan batas penutupan evaluasi harian.
- Bentuk penyimpanan Sabtu/Minggu/libur dan penyebut KPI; kuota izin 10 hari dalam dokumen masih dummy.

## Hal yang tidak boleh diwarisi langsung dari ETL lama

Pipeline Python memfilter work_code=1, sedangkan sampel aktual menunjukkan work_code sebagai ID shift. Event pertama/terakhir tanpa checktype tidak cukup untuk memastikan pasangan masuk/pulang. Prioritas lama presensi mengalahkan izin telah diganti: izin approved tetap IZIN. Filter aktif saat ini untuk seluruh histori serta asumsi seluruh hari terjadwal wajib kerja juga bertentangan dengan keputusan terbaru.

## Berkas acuan dan langkah berikutnya

- [Rekap seluruh departemen shift dan jadwal](../exports/rekap-departemen-shift-jadwal-20261005.xlsx).
- [Rekap kandidat mandatory reguler](../exports/rekap-shift-mandatory-regular-reguler-20261006.xlsx).
- [Inventaris kolom sumber](oltp-columns-hop.md).
- [Lembar review mapping kolom](oltp-mapping-review.csv), dengan mapping inti m_departemen terisi; sumber lainnya masih menunggu pembahasan.
- [ERD sumber sebelumnya](oltp-erd-hop.md), snapshot 29 September 2026; baca bersama keputusan terbaru di sini.

Tahap berikutnya adalah mengisi mapping per kolom dengan: target tabel/kolom, grain, sumber tabel/kolom, jalur join, filter, transformasi, prioritas histori, penanganan NULL/duplikasi, validasi, dan status keputusan. Setelah mapping disetujui, barulah susun transform/workflow Apache Hop, strategi incremental, serta rekonsiliasi. Tidak ada izin tersirat untuk menerapkan perubahan ETL hanya karena catatan diskusi ini tersimpan.


## Pembaruan target dan implementasi dim_pegawai — 6 Oktober 2026

Keputusan terbaru pengguna: tetap PostgreSQL; belum memerlukan ClickHouse. Dimensi
pegawai menyimpan snapshot terkini tanpa SCD2. Satu baris per m_pegawai.id, ID baru
insert dengan surrogate baru, ID sama update atribut dengan key tetap. Perpindahan
departemen belum diasumsikan pasti membuat ID sumber baru. NIP bukan kunci upsert.
Pengguna meminta mapping, konfigurasi pipeline Hop, perbaikan target, dan perpindahan
ke **epresensi_analytics_hop_dev**. Instruksi ini menggantikan target lama.

Target aktif: **public.dim_departemen** dan **public.dim_pegawai** di database dev.
Database epresensi_analytics dan tabel hop.dim_departemen lama tidak dipindah/dihapus.
Koneksi presensi_target menggunakan HOP_TARGET_DB dari environment presensi-local.
Mapping lengkap sumber per kolom ada di oltp-mapping-review.csv; nama kategori
berasal dari m_previleges.previleges. Nilai kategori: PNS, PTT, PPPK, PPPK Paruh
Waktu, Non-Aktif. Tidak ada filter kategori atau departemen.

Pipeline pegawai: Table Input (LEFT JOIN kategori) → Database Lookup departemen
pada target → Insert / Update berdasarkan pegawai_id_sumber. Kolom inti: ID sumber,
NIP, nama, departemen sumber dan key, kategori sumber dan label, kode jenis kelamin,
jabatan, pangkat, jenis_jabatan, eselon, kelas_jabatan, unit_kerja_induk_id_sumber,
source_created_at, source_updated_at. Timestamp sumber dipertahankan nullable.
pegawai_key dibentuk identity database; waktu_proses dan etl_loaded_at diperbarui
oleh trigger hanya pada perubahan. status_aktif tetap NULL; status_shift tidak
menjadi relasi shift. Tidak ada penghapusan otomatis.

Perbaikan target memakai migrasi aditif sql/hop/dev_dimensions.sql. Kolom lama
pegawai_id/departemen_id tetap diisi ID sumber untuk menjaga dependensi view/FK.
Kolom ID sumber yang tadinya generated diubah menjadi kolom biasa agar dapat
diisi Hop; uniqueness tetap dipertahankan. NULL nama departemen diizinkan sesuai
sumber. Surrogate key tidak disamakan dengan ID sumber dan tidak dibentuk ulang.
Kolom source_hash lama tidak dipakai pipeline ini. Histori mutasi belum dibentuk.

Urutan run: departemen dahulu, lalu pegawai. Hindari dua pemuatan bersamaan.
Commit per 1000; kegagalan dapat menyisakan batch selesai, pulihkan dengan rerun.
Referensi tidak cocok tidak membuang baris pegawai; lookup NULL dicatat validator.
Skrip validasi membandingkan semua kolom mapping dengan sumber, lookup key,
keunikan key, dan kestabilan key/timestamp pada rerun tanpa perubahan. Laporan:
validation-hop-dimensions.json. Panduan operasional terbaru: ../hop/README.md.

Runtime Hop diatur HOP_EMPTY_STRING_DIFFERS_FROM_NULL=Y agar tujuh nama kosong dan satu NIP kosong tetap string kosong; tidak diganti NULL atau label buatan.

Validasi implementasi selesai: public.dim_departemen 6.892 baris dan public.dim_pegawai 125.832 baris. Seluruh nilai mapping cocok dengan sumber, key unik, lookup departemen hilang 0. Rerun kedua pipeline tanpa perubahan sumber mempertahankan seluruh nilai, surrogate key, waktu_proses, dan etl_loaded_at. Bukti lengkap: `logs/reports/validation-hop-dimensions.json`.

## Mapping dimensi lanjutan — 7 Oktober 2026

Status: **rancangan mapping berbasis audit**, belum deployment pipeline/DDL dimensi
lanjutan. Acuan: BKD_Presensi_Business_Process_and_Grain_Design.docx (khususnya
BR-01–14, grain dan model konseptual) serta keputusan terbaru dalam dokumen ini.
Instruksi pengguna untuk menunda histori pegawai tidak menghapus kebutuhan bukti
historis shift/jadwal. Aturan pending tetap pending.

Database tujuan tetap epresensi_analytics_hop_dev, schema public. Audit read-only
dapat dibuat ulang ke `logs/reports/audit-remaining-dimensions.json`;
ulangi melalui `.venv/bin/python scripts/audit_remaining_dimensions.py`.

### Cakupan dan kondisi target (rancangan awal, dikoreksi di bawah)

| Peran | Rancangan target | Grain | Kondisi target audit |
|---|---|---|---|
| Dimensi inti baseline | dim_tanggal secara konseptual; usulan fisik memakai dim_calendar yang ada | Satu tanggal kalender | dim_calendar kosong; tidak rename/drop pada tahap mapping |
| Dimensi inti baseline | dim_shift | Satu m_shift.id untuk snapshot referensi terkini | Belum ada |
| Detail jadwal pendukung shift | dim_jadwal_kerja | Satu m_jadwal.id, terkait satu shift dan hari | Tabel tersedia, kosong |
| Referensi pendukung evaluasi izin | dim_jenis_izin | Satu m_jenis_ijin.id | Tabel tersedia, kosong; bukan penambahan fakta izin |

Dim_jadwal_kerja menyediakan rincian hari karena satu shift memiliki beberapa
jadwal. Menggabungkan seluruh jadwal ke satu baris dim_shift akan kehilangan grain,
sedangkan satu baris shift per hari akan menggandakan identitas shift. Hubungan
shift → jadwal adalah satu-ke-banyak; fakta tetap satu pegawai × tanggal kerja.
Dim_jenis_izin dipetakan sebagai referensi pendukung; keputusan fact_perizinan
terpisah tetap terbuka dan tidak dibuat hanya karena tabel lama tersedia.

### Dimensi tanggal: mapping konseptual dim_tanggal ke usulan fisik dim_calendar

Sumber utama adalah generator tanggal lengkap START_DATE..END_DATE inklusif,
bukan hanya tanggal yang mempunyai transaksi atau record libur. Periode load
harus menjadi parameter eksplisit; belum dipilih pada tahap ini. Tanggal awal
harus <= tanggal akhir. Gunakan date, bukan timestamp, untuk kunci kalender.

| Sumber/perhitungan | Target usulan | Tipe | Transformasi |
|---|---|---|---|
| Generator tanggal | tanggal | date, unik/PK | Satu baris setiap tanggal, termasuk Sabtu/Minggu dan libur |
| Tanggal | tahun, bulan, hari | smallint | Tahun kalender, nomor bulan 1–12, tanggal dalam bulan 1–31; hari bukan nomor hari pekan |
| Tanggal | nama_bulan, nama_hari | text | Label bahasa Indonesia yang deterministik, tidak tergantung locale server |
| Tanggal | hari_iso | smallint | Senin=1 sampai Minggu=7 |
| Tanggal | minggu_ke, tahun_iso | smallint | Minggu ISO dipasangkan dengan tahun ISO, termasuk pergantian tahun |
| Tanggal | kuartal | smallint | 1–4 |
| hari_iso | is_weekend | boolean | TRUE untuk 6/7 |
| hari_iso | is_hari_kerja_normal | boolean | TRUE untuk 1–5; belum menyatakan kewajiban individual |
| EXISTS m_hari_libur tanggal sama | is_hari_libur | boolean | Berdasarkan keberadaan tanggal, tidak berdasarkan keterangan NOT NULL |
| m_hari_libur.keterangan | keterangan_libur | text nullable | STRING_AGG DISTINCT terurut per tanggal; NULL tetap boleh jika tidak ada label |
| m_hari_libur.id | libur_id_sumber | integer[] nullable | ARRAY_AGG DISTINCT terurut per tanggal untuk audit |
| m_hari_libur.created_at | libur_source_created_at_terakhir | timestamp nullable | MAX per tanggal untuk audit record; bukan source_updated_at atau awal berlakunya libur |
| Proses ETL | waktu_proses | timestamptz | Isi insert/perubahan; rerun identik tidak mengubah timestamp |

Usulan mempertahankan tanggal sebagai key sesuai PK/FK existing; penambahan
surrogate tanggal_key tidak diperlukan untuk mapping ini. Jika model fakta baru
kelak memakai tanggal_key, konvensinya diputuskan eksplisit, bukan diisi ID acak.

Transformasi: deduplikasi libur per tanggal dahulu, lalu LEFT JOIN ke generator.
Jumlah output harus tepat END_DATE - START_DATE + 1; join tidak menambah baris.
Libur individual t_libur_shift bukan atribut kalender global: evaluasi terpisah
pada pegawai–tanggal. Tidak membentuk is_wajib_kerja final di kalender.

Audit: 131 record libur, 126 tanggal unik, lima tanggal memiliki dua record.
Cakupan tanggal sumber 2021-08-11..2026-08-25, tanpa keterangan NULL/kosong pada
snapshot ini. Tidak adanya record setelah batas tersebut **tidak membuktikan**
kalender libur periode berikutnya lengkap. is_hari_libur=false berarti tidak
terdaftar dalam sumber, bukan verifikasi kalender nasional. Kelengkapan sumber
per periode perlu ditetapkan sebelum klasifikasi TANPA_KETERANGAN.

Perubahan penting dari ETL lama: keberadaan libur tidak ditentukan oleh label.
Saat record libur dihapus/dikoreksi, hitung ulang flag untuk seluruh periode load;
jangan hanya upsert tanggal yang masih muncul pada tabel libur.

### Dimensi shift (rancangan awal pemisahan, digantikan keputusan gabungan di bawah)

| Sumber | Target usulan | Tipe | Transformasi |
|---|---|---|---|
| Database | shift_key | bigint identity | Surrogate stabil pada insert, tidak diubah saat update |
| m_shift.id | shift_id_sumber | integer unik NOT NULL | Kunci pencocokan snapshot |
| m_shift.nama | nama_shift | text | Salin mentah, tidak deduplikasi nama |
| m_shift.departemen_id | departemen_id_sumber | integer nullable | Pemilik shift; bukan otomatis organisasi pegawai pada tanggal transaksi |
| Lookup public.dim_departemen | departemen_key | bigint nullable | LEFT lookup departemen_id_sumber; simpan baris jika sumber NULL/tidak cocok |
| m_shift.status | is_aktif_saat_ini | boolean nullable | Salin; tanpa filter aktif saat ekstraksi |
| m_shift.nama | is_reguler | boolean | Pencarian case-insensitive regular atau reguler sesuai keputusan pengguna |
| m_shift.is_flexible | is_flexible_kode_sumber | integer nullable | Pertahankan kode mentah |
| m_shift.is_flexible | is_flexible | boolean nullable | 0→FALSE, 1→TRUE, NULL→NULL; nilai lain ditandai invalid, bukan bool(nonzero) |
| m_shift.event_id | event_id_sumber | integer nullable | Salin; bukan bukti penugasan pegawai/roster |
| m_shift.created_at | source_created_at | timestamp nullable | Salin; tidak dipakai sebagai valid_from/source_updated_at |
| Proses ETL | waktu_proses | timestamptz | Insert/perubahan saja |

m_shift.created_by tidak masuk mapping inti; tidak diperlukan untuk klasifikasi
kehadiran. Semua shift dipertahankan, termasuk nonreguler, nonaktif, tanpa
pemilik departemen dan tanpa jadwal. Filter kandidat reguler dilakukan ketika
menilai kewajiban, bukan dengan membuang master dimensi.

Audit: 15.624 shift; 6.886 aktif dan 8.738 nonaktif; 5.607 matching reguler;
312 tanpa departemen, tanpa orphan untuk ID departemen yang terisi; 113 fleksibel
(kode 1), lainnya kode 0. Sebanyak 393 shift tidak mempunyai jadwal.

Snapshot ini hanya menggambarkan master saat ini. Ia tidak cukup untuk menentukan
shift yang berlaku di masa lampau. Untuk evaluasi historis gunakan bukti transaksi
atau interval audit yang tervalidasi; jangan memperlakukan status sekarang maupun
waktu_proses sebagai masa berlaku historis. Beberapa reguler pada departemen yang
sama tetap alternatif; tidak dipilih dengan MIN(id), MAX(id), atau nama pertama.

### Detail jadwal: dim_jadwal_kerja (rancangan awal yang dibatalkan)

| Sumber | Target usulan | Tipe | Transformasi |
|---|---|---|---|
| Database | jadwal_key | bigint identity | Surrogate stabil |
| m_jadwal.id | jadwal_id_sumber | integer unik NOT NULL | Grain satu record sumber |
| m_jadwal.id | jadwal_id | bigint | Kolom kompatibilitas existing; diisi ID sumber |
| m_jadwal.jenis | shift_id_sumber | integer | Referensi m_shift.id; bukan kategori shift |
| Lookup dim_shift | shift_key | bigint nullable | LEFT lookup tanpa menggandakan/membuang jadwal |
| m_jadwal.hari | hari_sumber | text | Pertahankan nilai asli |
| Normalisasi hari | hari, hari_iso | text, smallint | Trim/lower untuk lookup Mon..Sun → Senin..Minggu / 1..7; alias Indonesia lengkap diterima; nilai tak dikenal dicatat dan hentikan publish hasil terkait |
| m_jadwal.jam_masuk | jam_masuk | time | Salin tanpa pembulatan/penambahan toleransi |
| m_jadwal.jam_keluar | jam_keluar | time | Salin; tanggal pulang belum dibentuk pada dimensi |
| m_jadwal.jam_masuk_awal | jam_masuk_awal | time | Salin batas sumber; tidak otomatis menjadi toleransi terlambat |
| m_jadwal.jam_keluar_akhir | jam_keluar_akhir | time | Salin |
| m_jadwal.flexible_time | flexible_time_sumber | time nullable | Salin mentah; tidak otomatis dianggap durasi menit |
| m_jadwal.created_at | source_created_at | timestamp nullable | Salin; bukan awal masa berlaku |
| Perbandingan jam | indikasi_lintas_tengah_malam | boolean | jam_keluar < jam_masuk; indikator pemeriksaan, bukan keputusan tanggal kerja |
| Perbandingan jam | is_jam_sama | boolean | jam_keluar = jam_masuk; tidak otomatis libur atau 24 jam |
| Proses ETL | waktu_proses | timestamptz | Insert/perubahan saja |

Kolom existing shift_id/departemen_id/nama_shift/is_flexible dapat diisi dari
lookup shift sebagai kompatibilitas; sumber otoritatif atribut tersebut tetap
dim_shift. Kolom source_updated_at lama jangan diisi MAX(created_at) seolah-olah
itu waktu pembaruan. DDL implementasi perlu mempertahankan FK/view existing.

Audit: 106.616 jadwal; hanya Mon/Tue/Wed/Thu/Fri/Sat/Sun; tidak ada orphan shift
atau duplikasi shift–hari ternormalisasi. Ada 9.909 jam pulang < jam masuk,
7.250 jam sama (termasuk 4.211 keduanya 00:00), dan flexible_time seluruhnya NULL.
Semua jadwal tetap dipetakan, termasuk akhir pekan. Keberadaan jadwal Sabtu/Minggu
tidak membatalkan keputusan hari kerja normal Senin–Jumat. Jam ambigu ditandai;
perhitungan durasi/keterlambatan terkait menunggu aturan, bukan diberi nol buatan.

### Referensi jenis izin (pendukung, bukan penetapan fakta baru)

| Sumber | Target usulan dim_jenis_izin | Tipe | Transformasi |
|---|---|---|---|
| Database | jenis_izin_key | bigint identity | Surrogate stabil |
| m_jenis_ijin.id | jenis_izin_id_sumber | integer unik NOT NULL | Kunci upsert; jenis_izin_id existing tetap ID sumber |
| m_jenis_ijin.nama | nama_jenis_izin | text | Salin |
| m_jenis_ijin.kode | kode_jenis_izin | text nullable | Salin; tidak dipakai sebagai key |
| m_jenis_ijin.label_kode | label_kode | text nullable | Salin terpisah dari kode |
| m_jenis_ijin.tipe_id | tipe_izin_id_sumber | integer nullable | Simpan referensi; tipe_izin_id existing tetap nilai yang sama |
| LEFT JOIN m_tipe_ijin.id | nama_tipe_izin | text nullable | Label dari m_tipe_ijin.nama |
| m_tipe_ijin.tipe | tipe_izin_raw | text nullable | Simpan teks seperti [1, 2, 3]; semantik belum disimpulkan |
| m_jenis_ijin.setengah_hari | is_setengah_hari_sumber | boolean nullable | Atribut sumber, bukan otomatis bobot 0,5 hari pada fakta |
| m_jenis_ijin.is_aktif | status_aktif_kode_sumber | integer nullable | Salin tanpa filter aktif; NULL bukan otomatis FALSE |
| m_jenis_ijin.potongan | potongan_sumber | text nullable | Pertahankan teks; tidak ditafsirkan persen/nilai uang |
| m_jenis_ijin.created_at | source_created_at | timestamp nullable | Salin; tidak dinamai source_updated_at |
| Proses ETL | waktu_proses | timestamptz | Insert/perubahan saja |

Audit: 29 jenis izin dan empat tipe, tanpa orphan tipe. Kode LA dipakai dua ID
berbeda; nama Tugas Lapangan/Tugas Belajar juga berulang, sehingga tidak boleh
dideduplikasi dengan kode/nama. LEFT JOIN tipe tidak menambah/mengurangi 29 baris.

Dimensi ini tidak menentukan approval. Approved, ditolak, dan pending adalah
kondisi transaksi. approval=false sendiri belum membuktikan penolakan. Izin
approved yang relevan tetap lebih tinggi daripada HADIR sesuai kesepakatan.
Aturan setengah hari, koreksi lupa absen, dinas luar, overlap, dan prioritas
terhadap libur tetap belum final. Jatah 10 hari pada baseline adalah dummy;
tidak dijadikan atribut permanen atau pengurang saldo izin produksi.

### Rancangan alur Hop dan penerimaan (rancangan awal; shift/jadwal dikoreksi di bawah)

- Kalender: generator tanggal → agregasi libur per tanggal → LEFT lookup →
  hitung atribut kalender → upsert berdasarkan tanggal.
- Shift: Table Input seluruh m_shift → mapping/validasi kode fleksibel →
  LEFT lookup departemen → upsert berdasarkan shift_id_sumber.
- Jadwal: Table Input seluruh m_jadwal → normalisasi hari/penanda kualitas →
  LEFT lookup shift → upsert berdasarkan jadwal_id_sumber.
- Referensi izin: Table Input m_jenis_ijin LEFT JOIN m_tipe_ijin → mapping →
  upsert berdasarkan jenis_izin_id_sumber.

Pola snapshot terbaru yang diusulkan: insert ID baru, update atribut berubah,
lewati baris identik, tidak delete otomatis. Gunakan key database stabil dan
waktu_proses yang hanya berubah bila data berubah. Kunci/strategi baru ini adalah
rancangan teknis, bukan klaim bahwa histori shift telah tersedia. Full source
comparison dipilih karena master terkait tidak memiliki updated_at yang memadai;
created_at tidak dipakai sebagai watermark perubahan.

Validasi implementasi nanti: jumlah dan himpunan ID cocok dengan sumber, join
tidak menggandakan baris, seluruh nilai mentah termasuk NULL/string kosong cocok,
key stabil dan rerun identik tidak mengubah timestamp. Hari tak dikenal, referensi
hilang, kode fleksibel di luar 0/1, serta jadwal ambigu harus dilaporkan. Pipeline
memakai pengaturan string kosong yang sudah diterapkan pada dimensi sebelumnya.

Urutan dependensi: dim_departemen → dim_shift → dim_jadwal_kerja; kalender dan
referensi izin dapat disiapkan terpisah. Nama fisik kalender, periode load, serta
aturan bisnis yang pending tetap dicatat sebelum implementasi/fakta terkait.
Tahap ini hanya memutakhirkan mapping dan bukti audit; tabel/pipeline aktif belum
berubah.


## Keputusan final gabungan dim_shift dan implementasi Hop — 7 Oktober 2026

Pengguna mengoreksi rancangan pemisahan shift/jadwal dan menyetujui penggabungan
m_shift + m_jadwal pada dim_shift, lalu meminta transformasi Hop dijalankan.
Bagian ini **menggantikan** rancangan pemisahan dim_shift/dim_jadwal_kerja di atas.
Dimensi inti tetap pegawai, departemen, tanggal, dan shift. Dimensi jenis izin
belum diperlukan; tidak dibuat pipeline dim_jadwal_kerja/dim_jenis_izin baru.
Tabel lama yang sudah ada tetap tersedia untuk kompatibilitas, tidak menjadi
target pipeline gabungan.

Target: **epresensi_analytics_hop_dev.public.dim_shift**.
Grain: **satu baris per m_jadwal.id**. Kunci upsert jadwal_id_sumber (unik),
shift_key surrogate stabil; shift_id_sumber adalah identitas induk yang berulang
pada beberapa hari. Nama/hari bukan kunci upsert. Fakta tetap pegawai × tanggal.

| Sumber | Kolom target aktif |
|---|---|
| Database identity | shift_key |
| m_jadwal.id | jadwal_id_sumber |
| m_jadwal.jenis = m_shift.id | shift_id_sumber |
| m_shift.nama | nama_shift; is_reguler diturunkan dengan regular/reguler case-insensitive |
| m_shift.departemen_id | departemen_id_sumber; LEFT lookup public.dim_departemen → departemen_key |
| m_shift.status | is_aktif_saat_ini, tanpa filter status |
| m_shift.is_flexible | is_flexible_kode_sumber; 0→false, 1→true, NULL→NULL pada is_flexible |
| m_shift.event_id | event_id_sumber |
| m_shift.created_at | shift_source_created_at |
| m_jadwal.created_at | jadwal_source_created_at |
| m_jadwal.hari | hari_sumber; normalisasi hari dan hari_iso Senin=1..Minggu=7 |
| m_jadwal.jam_masuk/jam_keluar/jam_masuk_awal/jam_keluar_akhir | Empat kolom time dengan nama sama |
| m_jadwal.flexible_time | flexible_time_sumber, nullable tanpa mengarang durasi |
| jam_keluar < jam_masuk | indikasi_lintas_tengah_malam, hanya indikator |
| jam_keluar = jam_masuk | is_jam_sama, tidak otomatis libur/24 jam |
| Database default/trigger | waktu_proses dan etl_loaded_at pada insert/perubahan |

Pipeline `pipelines/dim_shift.hpl`: Table Input gabungan (m_jadwal LEFT JOIN
m_shift) → Database Lookup departemen target → Insert / Update. LEFT JOIN menjaga
semua ID jadwal; parent yang hilang atau hari tidak dikenal menyebabkan validasi
constraint gagal, bukan dibuang diam-diam. Metadata sumber saat ini menunjukkan
referensi parent lengkap. Referensi departemen NULL tetap NULL; referensi terisi
yang gagal lookup dilaporkan validator. Kolom fleksibel di luar 0/1 ditolak.

Shift tanpa record m_jadwal tidak mempunyai baris pada grain ini; tidak dibuatkan
jadwal/hari buatan. Validator menyimpan jumlah dan daftar ID-nya terpisah.
Semua jadwal sumber dipertahankan tanpa filter akhir pekan, reguler, atau status
aktif. Beberapa shift reguler tetap alternatif. Snapshot ini tidak merekonstruksi
histori status/jam; source_created_at dan waktu_proses bukan valid_from.

Loader mengubah atribut dengan ID jadwal yang sama sambil mempertahankan shift_key,
melewati baris identik, dan tidak menghapus baris otomatis. Commit per 1000;
hindari run bersamaan dan rerun setelah memperbaiki kegagalan batch parsial.
Jalankan dim_departemen sebelum dim_shift. Tidak perlu menjalankan dim_pegawai
untuk lookup shift.

Artefak: sql/hop/dim_shift.sql, sql/hop/extract_dim_shift.sql,
scripts/setup_hop_shift.py, scripts/validate_hop_shift.py. Validator membandingkan
seluruh atribut dengan transformasi Python dari record mentah sumber, memeriksa
lookup/key dan fingerprint rerun. Hasil: validation-hop-dim-shift.json.


## Implementasi dimensi tanggal — 7 Oktober 2026

Atas permintaan pengguna melanjutkan pipeline dimensi yang tersisa, dimensi tanggal
konseptual diimplementasikan pada tabel existing
**epresensi_analytics_hop_dev.public.dim_calendar** dengan pipeline
`pipelines/dim_calendar.hpl`. Tidak dibuat duplikat tabel dim_tanggal atau dimensi
jadwal/jenis izin tambahan. Ini menetapkan pilihan fisik kalender pada rancangan
sebelumnya dan mempertahankan PK/FK existing berbasis tanggal.

Parameter START_DATE dan END_DATE berupa tanggal inklusif. Default operasional
awal 2021-01-01..2026-12-31 dipilih untuk mencakup tahun awal libur sumber sampai
tahun kerja saat ini; bukan pembatas periode bisnis permanen. Ubah parameter
pada Run Options di Hop jika cakupan analisis berubah. Tanggal akhir sebelum
awal ditolak. Tanggal di luar periode run tidak dihapus.

Table Input pada sumber membentuk kalender lengkap melalui generate_series,
mengagregasi m_hari_libur per tanggal, lalu LEFT JOIN dan menghitung atribut
kalender. Insert / Update target memakai tanggal sebagai key. Seluruh tanggal,
termasuk akhir pekan dan tanggal tanpa transaksi, tetap ada. is_hari_libur
berdasar keberadaan tanggal libur, tidak bergantung pada isi keterangan.
is_hari_kerja_normal hanya Senin–Jumat, bukan is_wajib_kerja final pegawai.
Libur individual t_libur_shift tetap dievaluasi pada fakta, bukan kalender global.

Kolom baru: hari_iso, tahun_iso, is_hari_kerja_normal, libur_id_sumber,
libur_source_created_at_terakhir, waktu_proses. Keterangan libur diperluas menjadi
text agar gabungan label tidak terpotong. Penyesuaian fisik dari rancangan awal:
libur_id_sumber disimpan sebagai **teks daftar ID terurut numerik dipisah koma**
(bukan integer[]) agar Table Input/Insert Update JDBC Hop dapat mempertahankan
nilai audit secara langsung. Nilai NULL tetap NULL jika tidak ada record libur.

Setiap run menghitung ulang seluruh tanggal dalam periode, sehingga koreksi atau
penghapusan record libur sumber mengubah flag/label pada rerun, tanpa menghapus
baris kalender. Trigger waktu_proses/etl_loaded_at hanya berjalan pada perubahan.
Commit per 1000, hindari run bersamaan, rerun bila ada kegagalan batch parsial.

Validasi membandingkan semua nilai dengan kalender Python dan record libur mentah.
Fixture read-only menguji tanggal kabisat, duplikasi libur, label NULL, tahun ISO,
akhir pekan, serta penolakan rentang terbalik. Laporan:
`logs/reports/validation-hop-dim-calendar.json`.
Default menghasilkan 2.191 tanggal dan 126 tanggal libur dari 131 record sumber.
Tanggal libur sumber terakhir tetap 2026-08-25; ini bukan bukti bahwa kalender
nasional setelah tanggal tersebut sudah lengkap. Kalender ini belum cukup untuk
menetapkan TANPA_KETERANGAN tanpa evaluasi aturan dan kelengkapan sumber.

Artefak: sql/hop/dim_calendar.sql, sql/hop/extract_dim_calendar.sql,
scripts/setup_hop_calendar.py, scripts/validate_hop_calendar.py.

## Mapping fact_kehadiran dan keputusan review — 7 Oktober 2026

Pengguna meminta melanjutkan fact_kehadiran sesuai kesepakatan. Load awal diminta
untuk satu hari data; tanggal dan dataset final masih harus dipastikan. Pengguna
memilih: **kasus check-in tanpa check-out, jadwal ambigu, dan histori yang belum
terbukti disimpan untuk review, tidak masuk KPI final**. Ini menetapkan perlakuan
kasus pending, bukan mengesahkan aturan pasangan event atau histori yang belum ada.

### Temuan identitas dataset

Sumber seluruh dimensi Hop saat ini adalah dbabsen_restore. Inspeksi pg_class
menunjukkan perkiraan 89.466.776 record t_checkinout (estimasi, bukan COUNT aktual),
ukuran total sekitar 29 GB. Record ID terkecil mempunyai created_at
2024-01-01 00:00:56, ID terbesar 2026-09-01 00:24:56. Ini **bukan** klaim minimum
atau maksimum timestamp seluruh tabel, tetapi membuktikan sumber tidak hanya satu
hari. Indeks t_checkinout yang tersedia saat inspeksi hanya indeks unik ID;
metadata indeks tanggal dari inventaris sebelumnya tidak lagi boleh diasumsikan
berlaku. Audit full-table melewati statement_timeout dan dibatalkan; tidak ada
indeks/struktur sumber yang diubah.

Konfigurasi OLTP Python lama bernama epresensi_clean, berbeda dengan dbabsen_restore.
Laporan lama reconciliation-2026-09-01.json (dihapus saat perapian) berasal dari dataset/koneksi lama dan tidak
boleh menjadi bukti hasil untuk sumber restore. Fakta dari epresensi_clean tidak
boleh langsung di-lookup menggunakan ID dimensi dbabsen_restore hanya karena angka
ID kebetulan sama. Sumber/tanggal load ditanyakan ke pengguna sebelum deployment.

Audit sampel dapat dibuat ulang ke `logs/reports/audit-fact-mapping.json`, skrip
`scripts/audit_fact_mapping.py`. Sampel 10.000 event terakhir menurut ID cocok
jadwal/shift/departemen/jam master; tidak menjamin semua histori cocok. Sampel
memiliki checktype 1/2, timezone Asia/Jakarta, is_wfh=0. View aplikasi yang diperiksa
menggunakan DATE(created_at) dan label 1=Masuk, 2=Keluar; tidak membuktikan aturan
shift lintas tengah malam. Sampel izin memperlihatkan approval=false dengan
beragam status dan tanpa approval_at; tidak otomatis berarti ditolak.

### Grain dan mapping target yang direncanakan

Target epresensi_analytics_hop_dev.public.fact_kehadiran. Grain tetap satu identitas
pegawai sumber × tanggal kerja, termasuk ketika tersedia beberapa alternatif
reguler. Usulan kolom baru berikut menyesuaikan model lama dengan dimensi Hop:

| Sumber/aturan | Target | Transformasi dan batas |
|---|---|---|
| Populasi terpilih / event / izin | pegawai_id_sumber; pegawai_key | Lookup dim_pegawai menurut ID sumber, bukan NIP; tidak mencampur database sumber |
| Tanggal kerja terverifikasi | tanggal | Lookup dim_calendar.tanggal; lintas tengah malam tetap review sampai aturan final |
| Organisasi relevan pada tanggal | departemen_id_sumber; departemen_key | Bukti transaksi dibandingkan master; konflik/histori tidak ditebak |
| t_checkinout.jadwal_id | jadwal_id_sumber; shift_key | Lookup dim_shift.jadwal_id_sumber; cross-check work_code terhadap shift_id_sumber |
| Kandidat reguler departemen + hari | kandidat_shift | Pertahankan seluruh alternatif dalam proses/referensi audit; tidak menggandakan grain akhir |
| Pasangan event masuk tervalidasi | waktu_masuk | checktype=1; duplikat/konflik tidak diselesaikan dengan MIN sembarang |
| Pasangan event keluar tervalidasi | waktu_pulang | checktype=2; tidak memakai event terakhir sebagai keluar tanpa checktype |
| Snapshot jadwal terverifikasi | jadwal_mulai; jadwal_selesai | Simpan acuan evaluasi yang dipakai; prioritas konflik dengan master belum final |
| Kalender + libur individual + populasi/jadwal berlaku | is_wajib_kerja | TRUE hanya bila kewajiban terbukti; UNKNOWN tidak diubah FALSE atau TANPA_KETERANGAN |
| Dedup t_libur_shift per pegawai–tanggal | is_libur_shift | Tidak memperbanyak fakta; NULL pegawai/tanggal dan anomali dilaporkan |
| Izin approved yang relevan | has_valid_leave; izin_id_sumber | Validasi identitas via m_user, cakupan tanggal dan overlap; tidak memerlukan fakta izin terpisah |
| Aturan klasifikasi | status_kehadiran | IZIN mendahului HADIR; TANPA_KETERANGAN hanya sisa hari wajib yang evaluasinya selesai |
| Event is_wfh konsisten | mode_kerja | WFO/WFH; NULL pada izin/tidak bekerja; konflik masuk review |
| Waktu masuk dibanding acuan jadwal | is_terlambat; durasi_terlambat | Selisih positif dalam menit; NULL bila tidak relevan/tidak dapat dinilai, pembulatan/toleransi belum final |
| Bukti event sumber | jumlah_event; event_id_sumber | Jumlah dan identitas untuk rekonsiliasi; tidak menyalin lokasi/perangkat/alasan izin bila tidak diperlukan |
| Aturan review | perlu_review; alasan_review; is_kpi_final | Kasus pending disimpan, is_kpi_final=false; status bisnis belum final boleh NULL |
| Proses | waktu_proses | Insert/perubahan, rerun identik stabil |

Kolom teknis perlu_review/is_kpi_final adalah rancangan implementasi atas keputusan
review pengguna. Belum menetapkan label bisnis baru seperti NON_WORKING_DAY atau
PENDING sebagai status_kehadiran. Data review harus dikecualikan secara eksplisit
pada query/view KPI, bukan hanya diberi catatan. Hari Sabtu/Minggu/libur tidak
boleh menghasilkan TANPA_KETERANGAN. Penyimpanan hari nonwajib tetap terpisah dari
penetapan status harian; jangan menganggap seluruh master sebagai penyebut KPI.

### Perubahan yang diperlukan sebelum load

Target saat audit kosong. FK jadwal_id lama masih menunjuk dim_jadwal_kerja,
dan perizinan_id masih menunjuk fact_perizinan. Implementasi harus menyelaraskan
referensi ke dim_shift dan menyimpan ID izin sumber untuk audit tanpa memaksa
pembuatan dimensi/fakta izin tambahan. Boolean lama yang NOT NULL tidak boleh
memaksa UNKNOWN menjadi FALSE. Jangan memakai loader lama karena prioritas HADIR
atas izin, filter work_code=1, dan penentuan masuk/pulang berdasarkan urutan event
bertentangan dengan kesepakatan.

Rancangan Hop: ekstraksi periode → normalisasi/audit event dan izin → kandidat
pegawai–tanggal → alternatif jadwal dan pengecualian libur → pasangan event dan
ringkasan izin → lookup dimensi → klasifikasi/review → upsert grain unik →
rekonsiliasi jumlah event, baris, status, dan pengecualian KPI.

Sebelum deploy, pastikan sumber dan tanggal proses, serta populasi yang boleh
menjadi kandidat. Jika populasi historis belum terbukti, baris terkait hanya review
sesuai keputusan pengguna. Tidak ada perubahan tabel fakta atau pipeline fakta
yang dilakukan pada tahap audit/mapping ini.

### Implementasi backfill setelah persetujuan seluruh data (7–8 Oktober 2026)

Pengguna menyetujui seluruh histori `dbabsen_restore`, menggantikan asumsi awal
satu hari. Pengguna juga menetapkan kasus pending disimpan untuk review dan
tidak masuk KPI final. Bagian ini memperbarui status tahap audit di atas:
pipeline/workflow fakta dan struktur target sudah dibuat. Penyelesaian load
dibuktikan terpisah melalui checkpoint dan laporan validasi lengkap.

Implementasi menggunakan PostgreSQL dan Hop. Rentang ID event dibekukan saat
setup; tanggal minimum/maksimum baru ditetapkan setelah seluruh batch dibaca.
Snapshot referensi izin, libur individual, pegawai, shift gabungan, dan kalender
dipertahankan selama run. Tidak ada pemilihan shift alternatif secara sembarang.
Aturan dieksekusi di fungsi SQL target yang dipanggil pipeline Hop; detail operasi
dan resume ada pada `hop/README.md`.

Penyesuaian fisik terhadap rancangan mapping:

| Rancangan | Implementasi |
|---|---|
| Identitas pegawai/departemen | FK legacy `pegawai_id`/`departemen_id` dipertahankan; key Hop ditambahkan sebagai `pegawai_key`/`departemen_key`. Identitas sumber dilacak lewat dimensi. |
| Referensi jadwal gabungan | `shift_key` menunjuk `dim_shift`; `jadwal_id_sumber` menyimpan identitas jadwal. `jadwal_id` legacy dibiarkan NULL. |
| Referensi izin | `izin_id_sumber` berisi ID approved terurut, dipisah koma; `perizinan_id` legacy NULL. |
| Kewajiban hari kerja | Kolom fisik `is_expected_workday`, nullable. Tidak mengisi ketidakhadiran berdasarkan master saat ini. |
| Identitas event | Agregat per pegawai–tanggal menyimpan jumlah, hitungan per checktype, rentang ID, dan konsistensi atribut; ID mentah tetap dapat ditelusuri pada sumber restore. |
| Event tanpa tanggal | ID dan alasan disimpan di `hop_etl.event_rejects`, tersedia melalui view review. |
| Kandidat tanpa bukti transaksi | View `analytics.hop_missing_employee_days_review`, bukan materialisasi perkalian seluruh master × tanggal. Tetap bukan penyebut KPI. |
| Nilai bisnis pending | `status_kehadiran=NULL`, `perlu_review=true`, `is_kpi_final=false`; `status_usulan` menyimpan kandidat IZIN/HADIR bila ada. |

Pasangan normal hanya dinilai bila tepat satu masuk checktype=1 dan satu keluar
checktype=2, tanpa checktype lain, keluar tidak mendahului masuk, serta jadwal
reguler/hari/jam/shift pada transaksi konsisten dengan snapshot dimensi.
Perbedaan atribut, event berulang, jadwal lintas hari, fleksibel/manual, konflik
departemen, atau timezone/mode kerja yang tidak konsisten masuk review.
Hari akhir sumber dan tanggal setelah batas libur sumber yang tersedia juga
ditahan untuk review; ini pagar konservatif, bukan sertifikasi lengkapnya data
libur pada periode sebelumnya. Izin setengah hari, lupa presensi, identitas atau
periode tidak jelas, serta overlap approved tidak diselesaikan dengan tebakan.

Fakta fisik dibentuk untuk pegawai–tanggal yang memiliki event/izin/libur
individual di dalam rentang tanggal event. Referensi izin/libur di luar rentang
tetap tersimpan pada staging. Kasus referensi tanpa tanggal/pegawai yang dapat
dipetakan tidak dipaksa masuk grain fakta. Histori tanpa bukti kewajiban tidak
diubah menjadi TANPA_KETERANGAN. Prioritas IZIN tetap mendahului HADIR.

View final menahan publikasi selama backfill belum selesai. Rekonsiliasi jumlah
event (termasuk reject), tanggal, dan baris dilakukan sebelum fase `done`.
Validator lengkap juga membandingkan tabel fakta dengan log harian. Rerun atas
restore yang sama melanjutkan checkpoint atau menjadi no-op setelah selesai;
perubahan sumber setelah snapshot belum dicakup oleh implementasi ini.
