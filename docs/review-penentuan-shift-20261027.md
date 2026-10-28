# Review penentuan shift dan pertanyaan admin — 27 Oktober 2026

Status: usulan revisi rencana, menunggu keputusan bisnis admin. Eksplorasi database dilakukan read-only pada `dbabsen_restore` dan `staging_bkd_test_20261027`. Ini dump/pilot, bukan validasi konfigurasi aplikasi live. Tidak ada aktivasi shift, perubahan jadwal, perubahan denominator, atau pengiriman pesan ke admin pada audit ini.

## Temuan yang terverifikasi

Hasil query staging cocok dengan breakdown: 960 departemen, 20.666 pegawai aktif belum mempunyai kandidat reguler menurut aturan pilot.

| Kelompok | Departemen | Pegawai aktif |
|---|---:|---:|
| Tidak ada nama regular/reguler | 758 | 16.837 |
| Tidak memiliki shift langsung | 200 | 3.784 |
| Reguler ada tetapi tanpa rincian jadwal | 2 | 45 |

Dari kelompok tanpa nama reguler, 488 departemen (10.751 pegawai) mempunyai shift aktif dengan baris Selasa dan jam masuk/pulang terisi serta berbeda; 1 departemen (11 pegawai) punya baris Selasa tetapi tidak memenuhi pemeriksaan jam tersebut; 269 departemen (6.075 pegawai) tidak mempunyai baris Selasa pada shift aktif. Pemeriksaan jam ini hanya penyaringan kandidat, bukan bukti kewajiban atau validitas jadwal.

Contoh sumber: departemen 30989, FUNGSIONAL di SMKN 5 Jember, memiliki shift aktif 15989 `SMKN 5 Jember - Guru`: Senin–Jumat 07.00–15.30 dan Sabtu/Minggu 00.00–00.00. Nama tanpa kata reguler dapat memiliki pola kerja rutin. Arti 00.00–00.00 tetap harus dikonfirmasi, bukan otomatis libur atau kerja 24 jam.

Shift reguler 20498 (Terminal Larangan, departemen 33059) dan 18795 (Sub Bagian Umum dan Kepegawaian, departemen 33795) benar-benar tidak mempunyai baris `m_jadwal`. Kedua departemen memiliki shift lain dengan rincian jadwal; keberadaan shift pengamanan/pagi/malam tidak membuktikan semua pegawai ditugaskan ke sana.

20.665 pegawai memiliki ancestor dengan kandidat reguler Selasa, tetapi hanya 4.756 pada parent langsung; sisanya ditemukan sampai tingkat 2–5. Satu pegawai di Sekretariat Daerah (30115) tidak mempunyai ancestor kandidat. Jangan mewariskan jadwal Dinas Pendidikan/Kesehatan ke sekolah/rumah sakit hanya karena dapat dijangkau melalui hierarki.

## Petunjuk tambahan dari database sumber

- Relasi eksplisit: `m_pegawai.departemen → m_departemen.id`, `m_shift.departemen_id → m_departemen.id`, `m_jadwal.jenis → m_shift.id`. Ini menunjukkan kepemilikan jadwal, belum penugasan individu.
- `m_pegawai.status_shift` berisi 1, 2, 5, 6, atau NULL. Populasi aktif masing-masing 6.273, 434, 74.318, 1.092, dan 2. Tidak ada foreign key dari kolom ini dan tidak ada `m_shift.id` 1, 2, 5, 6 di dump. Jangan memperlakukannya sebagai ID shift; arti kode belum diketahui.
- Ada 312 shift tanpa departemen, 13 aktif. Kemungkinan penggunaan sebagai shift bersama perlu dijelaskan admin; belum ada bukti penugasannya.
- `t_libur_shift` menyediakan pengecualian per pegawai/tanggal. `t_pegawai_lokasi` memiliki hari dan rentang tanggal, tetapi tidak memiliki kolom shift/jadwal; tidak cukup untuk dianggap roster shift.
- `t_log_jadwal` kosong pada dump. Struktur `m_shift`/`m_jadwal` tidak menyediakan kolom masa berlaku mulai/akhir yang eksplisit.
- Dalam inventaris 39 base table schema public, belum ditemukan tabel roster eksplisit pegawai × tanggal × shift. Ini bukan bukti roster tidak ada: logika aplikasi, schema/sistem lain, atau atribut teks bisa menyimpan aturan. `attrs` dan `other_attr` pegawai terisi, tetapi isi dan maknanya belum diaudit.
- Riwayat `t_checkinout.jadwal_id` dapat menjadi bukti jadwal yang digunakan, bukan bukti penugasan pegawai yang tidak hadir. Audit ini belum memindai riwayat transaksi; indeks sumber yang terlihat hanya pada ID, sehingga pencarian historis perlu periode/strategi ekstraksi terukur.

## Pertanyaan untuk admin (siap digunakan)

1. **Dasar jadwal wajib:** apakah kata regular/reguler masih menjadi satu-satunya penanda wajib? Untuk nama seperti `SMKN 5 Jember - Guru`, `PELAYANAN NON SHIFT`, dan `5 HARI KERJA`, mohon klasifikasi per ID shift: wajib rutin, roster bergilir, kegiatan khusus, atau tidak berlaku. Apakah klasifikasi berbeda menurut kelompok pegawai?
2. **Arti status_shift:** apa arti kode 1, 2, 5, 6 dan NULL pada `m_pegawai.status_shift`? Apakah kode menentukan pola hari kerja, hak memilih shift, atau aturan lainnya? Mohon referensi konfigurasi atau kode aplikasi yang menerapkannya.
3. **Departemen tanpa shift:** untuk 200 departemen/3.784 pegawai, apakah jadwal berasal dari parent, `opd_parent`, `unit_kerja_induk` pegawai/departemen, shift bersama, atau penugasan khusus? Sebutkan ID sumber yang berlaku, batas pewarisan, dan pengecualiannya. Contoh: departemen 32523 di SMKN 1 Lamongan.
4. **Prioritas aturan:** jika ada jadwal langsung, jadwal induk, penugasan individu, dan kegiatan khusus pada tanggal sama, mana yang berlaku? Apakah fallback induk dibolehkan saat shift langsung nonaktif atau tidak memiliki rincian jadwal?
5. **Banyak pilihan shift:** apakah semua pilihan berlaku untuk semua pegawai, bebas dipilih, atau dibatasi jabatan/kelompok/roster? Di mana roster pegawai–tanggal–shift disimpan, termasuk pegawai yang tidak presensi? Mohon contoh rumah sakit dan petugas keamanan.
6. **Master kosong/nonaktif:** siapa yang melengkapi jadwal shift 20498 dan 18795, dengan hari serta jam apa? Untuk shift yang hanya nonaktif, apakah memang tidak berlaku atau dump belum mencerminkan konfigurasi live? Jangan meminta aktivasi massal tanpa daftar yang disetujui.
7. **Kalender dan jam:** apa arti 00.00–00.00, pola 5/6 hari, libur pada shift bergilir, shift melewati tengah malam, serta prioritas libur nasional/individual terhadap roster? Apakah akhir pekan selalu libur atau mengikuti penugasan?
8. **Masa berlaku:** sejak tanggal berapa setiap keputusan berlaku? Bagaimana aturan Ramadan, event, mutasi departemen, dan perubahan shift ditentukan untuk tanggal historis? Apakah tersedia histori master atau log aplikasi lain?
9. **Kasus belum terjawab:** setujukah ditampilkan sebagai `PERLU_KONFIRMASI_JADWAL`, dipisahkan dari wajib/tidak wajib, serta tidak otomatis menjadi tanpa keterangan sampai aturan jelas? Siapa pemilik keputusan dan pemeriksa hasil per OPD?

Format jawaban yang disarankan: `departemen_id`, `kelompok_pegawai/pegawai_id bila diperlukan`, `shift_id/jadwal_id`, `jenis_kewajiban`, `sumber_penugasan`, `departemen_sumber_jika_mewarisi`, `prioritas`, `berlaku_mulai`, `berlaku_sampai`, `aturan_libur`, `pengecualian`, `pemberi_persetujuan`, `bukti`. Gunakan ID serta parent karena nama departemen berulang. Data individu hanya dipertukarkan melalui kanal internal yang sesuai.

## Usulan perubahan rencana

1. Pertahankan hasil pilot/revisi 1 sebagai baseline teknis. Angka 61.452 adalah hasil aturan pilot setelah aktivasi sebelumnya, belum angka wajib hadir organisasi yang tervalidasi.
2. Tambahkan tahap keputusan bisnis sebelum memperluas denominator: klasifikasi shift berbasis ID dan masa berlaku, cakupan pegawai, aturan pewarisan, prioritas, kalender, serta sumber roster. Keyword tetap menjadi petunjuk awal dan jejak audit.
3. Rancang resolver penugasan yang menyimpan kandidat, sumber aturan, dan alasan keputusan; urutan prioritas mengikuti jawaban admin. Hindari memilih ID terkecil, menyimpulkan dari presensi saja, atau mewariskan ancestor otomatis.
4. Pisahkan kewajiban tiga keadaan: wajib, tidak wajib yang terbukti, dan belum diketahui. Dalam pilot saat ini `n=0` menghasilkan `is_expected_workday=false`; ini belum membedakan tidak wajib dengan belum diketahui. Usulan perubahan memerlukan penyesuaian kontrak curated, transformasi, dan dashboard; belum diterapkan pada audit ini.
5. Tampilkan cakupan pemetaan dan jumlah belum terkonfirmasi bersama KPI. Evaluasi tanpa keterangan hanya pada kewajiban yang terbukti setelah batas penutupan hari sesuai aturan; kasus unknown tidak disembunyikan sebagai libur/tidak wajib.
6. Setelah jawaban admin tersedia, uji sampel sekolah, rumah sakit, unit tanpa shift, dua master kosong, shift bersama, dan kasus prioritas ganda. Bandingkan dampak denominator/status dengan baseline sebelum mengintegrasikan perubahan ke Hop.

## Bukti dan reproduksi

- [Breakdown departemen](../tests/source_to_curated_20261027/breakdown_departemen.csv)
- [Query eksplorasi staging read-only](../tests/source_to_curated_20261027/explore_shift_assignment.sql)
- [Hasil query staging](../tests/source_to_curated_20261027/explore_shift_assignment_results.txt)
- [Aturan pilot](../tests/source_to_curated_20261027/workday.sql)

Jalankan query staging dengan `docker exec -i epresensi-staging-postgres psql -X -v ON_ERROR_STOP=1 -U admin_staging -d staging_bkd_test_20261027 < tests/source_to_curated_20261027/explore_shift_assignment.sql`.
