# Rancangan tabel fakta kehadiran dan langkah pembentukannya

Acuan: [kesepakatan mapping presensi](kesepakatan-mapping-presensi-hop.md), bagian “Pembentukan fakta yang direncanakan” dan “Grain dan mapping target yang direncanakan”. Diperbarui 9 Oktober 2026, termasuk keputusan tampilan presensi dan lokasi dalam diskusi terbaru.

**Tabel fakta dapat dibentuk. Yang belum dapat dipastikan adalah pengisian status final untuk seluruh pegawai pada seluruh tanggal historis.** Berikut bentuk tabel yang Anda usulkan, urutan pembentukannya, dan batas pelaksanaan setiap langkah. Ini panduan untuk dibuat di Apache Hop; belum merupakan perubahan tabel atau pipeline.

Panduan praktik GUI untuk mekanisme check-in dan check-out: [Panduan Apache Hop fakta harian](panduan-hop-checkin-checkout-fakta-harian.md).

## 1 Bentuk tabel fakta yang Anda usulkan

Target: `epresensi_analytics_hop_dev.public.fact_kehadiran`.

**Satu baris mewakili satu pegawai pada satu tanggal kerja.** Jika pegawai memiliki dua alternatif shift pada hari yang sama, hasil akhirnya tetap satu baris, bukan dua baris.

Masuk dan pulang berada pada baris fakta yang sama. **Kelengkapan presensi, kesesuaian lokasi, dan status kehadiran dinilai terpisah.** Presensi dapat lengkap meskipun lokasi pulangnya tidak sesuai; lengkap tidak otomatis berarti HADIR final.

Nama kolom mengikuti rancangan awal dengan tambahan usulan teknis untuk keputusan terbaru. Nama dan tipe fisik kolom tambahan belum diterapkan pada database. Penyesuaian struktur existing perlu dilakukan terpisah sebelum load.

| Kelompok | Kolom yang diusulkan | Isi yang diharapkan |
|---|---|---|
| Identitas pegawai | `pegawai_id_sumber`, `pegawai_key` | ID pegawai sumber dan key referensinya. Gunakan ID pegawai, bukan NIP, untuk pencocokan. |
| Tanggal | `tanggal` | Tanggal kerja yang sedang dinilai. |
| Organisasi | `departemen_id_sumber`, `departemen_key` | Departemen pegawai yang relevan pada tanggal tersebut. |
| Jadwal yang digunakan | `jadwal_id_sumber`, `shift_key` | Jadwal yang dibuktikan oleh presensi. Tidak dipilih sembarang ketika ada beberapa alternatif. |
| Jam aktual | `waktu_masuk`, `waktu_pulang` | Waktu event masuk dan keluar yang telah diperiksa. |
| Bukti masuk dan pulang | `has_masuk`, `has_pulang` | TRUE bila jenis event terkait tercatat; tidak otomatis membuktikan kepatuhan lokasi. |
| Kelengkapan presensi | `is_presensi_lengkap` | TRUE bila pasangan masuk dan pulang untuk tanggal kerja tersebut sudah dapat ditentukan; FALSE bila salah satunya belum tercatat; NULL bila pasangan masih ambigu. Tidak bergantung pada hasil validasi lokasi. |
| Penugasan kerja | `mode_kerja_penugasan` | WFO/WFH yang diizinkan pada tanggal tersebut, berdasarkan bukti penugasan; bukan sekadar pilihan mode pada event. |
| Validasi lokasi per event | `lokasi_masuk_sesuai`, `lokasi_pulang_sesuai` | TRUE sesuai aturan, FALSE terbukti tidak sesuai, NULL jika event atau bukti pembanding belum tersedia. |
| Penjelasan lokasi | `alasan_validasi_lokasi` | Menjelaskan event yang tidak sesuai atau penyebab lokasi belum dapat dinilai. |
| Acuan jadwal | `jadwal_mulai`, `jadwal_selesai` | Tanggal dan jam jadwal yang dipakai untuk menilai presensi. |
| Kewajiban hadir | `is_wajib_kerja` | TRUE jika wajib hadir terbukti; FALSE jika nonwajib terbukti; NULL jika belum diketahui. |
| Libur individual | `is_libur_shift` | Penanda libur pegawai pada tanggal tersebut. |
| Izin | `has_valid_leave`, `izin_id_sumber` | Apakah ada izin approved yang sah dan relevan, beserta ID sumbernya. |
| Status harian | `status_kehadiran` | IZIN, HADIR, atau TANPA_KETERANGAN sesuai bukti. NULL jika status belum dapat dipastikan. |
| Mode kerja | `mode_kerja` | WFO atau WFH jika terbukti; NULL pada izin/tidak relevan atau belum dapat dinilai. |
| Keterlambatan | `is_terlambat`, `durasi_terlambat` | Penanda terlambat dan selisih positif menit terhadap jadwal. NULL jika tidak dapat dinilai. |
| Bukti event | `jumlah_event`, `event_id_sumber` | Jumlah dan referensi event untuk menelusuri hasil. |
| Pemeriksaan | `perlu_review`, `alasan_review`, `is_kpi_final` | Menandai hasil yang perlu diperiksa dan tidak boleh masuk KPI final. |
| Waktu proses | `waktu_proses` | Waktu insert/perubahan; rerun identik tidak mengubahnya. |

`kandidat_shift` dalam rancangan dipertahankan sebagai daftar alternatif pada proses/tabel kerja pendukung. Daftar ini tidak boleh menggandakan baris fakta. Bentuk fisik daftar ID event, izin, dan alternatif perlu ditetapkan saat menyusun tabel; jangan memaksanya menjadi satu ID jika sumbernya lebih dari satu.

Kunci unik yang diusulkan: **`pegawai_id_sumber` + `tanggal`**. Referensi jadwal, waktu, status, dan ukuran yang belum diketahui harus dapat bernilai NULL.

**Contoh penyajian dashboard yang disepakati**

Data berikut adalah dummy. Anggap penugasan dan aturan lokasi setiap pegawai sudah tersedia. Tanggal kerja seluruh contoh adalah 3 Agustus 2026.

| Pegawai | Penugasan | Masuk | Pulang | Kelengkapan presensi | Validasi lokasi |
|---|---|---|---|---|---|
| Andi | WFO | 07.55 | 16.05 | Lengkap | Masuk dan pulang sesuai |
| Citra | WFH | 07.58 | 16.02 | Lengkap | Sesuai aturan lokasi WFH |
| Dedi | WFO | 07.57 | — | Belum lengkap | Masuk sesuai; pulang belum tersedia |
| Eka | WFO | 07.56 | 16.01 | Lengkap | Lokasi pulang tidak sesuai |
| Fajar | WFO | 07.59 | 16.04 | Lengkap | Belum dapat dinilai karena referensi lokasi tidak tersedia |

Eka tetap dihitung sebagai **presensi lengkap**, tetapi juga masuk indikator **lokasi tidak sesuai**. Fajar tidak boleh dimasukkan ke lokasi tidak sesuai hanya karena referensinya belum tersedia. Tanda — mewakili NULL, bukan jam 00.00.

| Indikator dashboard | Dasar penyajian |
|---|---|
| Sudah masuk | Pegawai–tanggal dengan `has_masuk=true`; validasi lokasi ditampilkan terpisah. |
| Belum check-in | Pegawai–tanggal yang wajib hadir sudah terbukti dan belum memiliki event masuk dalam cakupan data yang sudah diperiksa. Bukan otomatis TANPA_KETERANGAN. |
| Presensi lengkap | `is_presensi_lengkap=true`, tanpa menggabungkannya dengan syarat lokasi. |
| Lokasi tidak sesuai | Setidaknya salah satu validasi lokasi bernilai FALSE. Hitung satu kali per pegawai–tanggal meskipun kedua event tidak sesuai. |

Tidak digunakan label “Menunggu pulang”. Sebelum check-out tercatat, kolom pulang berisi — dan kelengkapan berisi “Belum lengkap”. Pada hari berjalan, ini belum berarti pelanggaran; pemeriksaan akhir mengikuti batas evaluasi yang ditetapkan.

Indikator bisa tumpang tindih dan tidak dijumlahkan sebagai total pegawai. Untuk rentang beberapa hari, unitnya pegawai–hari; jumlah pegawai unik harus diberi label tersendiri.

Status bisnis tetap terpisah: IZIN sah mengalahkan HADIR; TANPA_KETERANGAN membutuhkan kewajiban dan kelengkapan sumber yang terbukti. Keputusan tampilan terbaru tidak menetapkan check-in saja sebagai HADIR final, tidak otomatis menjadikan lokasi tidak sesuai sebagai absen, dan tidak menetapkan radius atau kewajiban lokasi WFH. Kasus yang belum terselesaikan mengikuti aturan review.

## 2 Langkah awal sampai tabel fakta terbentuk

**Mulai dari satu tanggal dan kelompok pegawai kecil untuk uji.** Jangan langsung memuat seluruh histori. Contoh tanggal pada tabel di atas hanya ilustrasi, bukan penetapan periode proses.

| Langkah | Yang Anda lakukan | Hasil yang harus tersedia sebelum lanjut |
|---|---|---|
| **1. Tentukan periode dan pegawai** | Pilih tanggal uji dan daftar pegawai. Catat apakah keanggotaan pegawai pada periode itu sudah terbukti atau masih asumsi. | Daftar pegawai dan periode yang akan dinilai. |
| **2. Siapkan tabel fakta uji** | Gunakan struktur bagian 1, kunci unik pegawai–tanggal, dan kolom nullable untuk unknown. Periksa perbedaan dengan tabel existing sebelum mapping. | Tabel tujuan uji yang tidak tercampur dengan hasil lama. |
| **3. Ambil event, izin, dan libur individual** | Baca `t_checkinout`, `t_perizinan` beserta referensi identitas/jenisnya, serta `t_libur_shift`. Pertahankan ID, checktype, mode event, dan bukti lokasi yang relevan. Telusuri sumber penugasan WFO/WFH serta aturan lokasi yang berlaku. | Event, izin, libur, dan referensi penugasan/lokasi; referensi yang belum ditemukan ditandai unknown. Jangan memfilter `work_code=1`. |
| **4. Bentuk kandidat pegawai–tanggal** | Pasangkan daftar pegawai langkah 1 dengan tanggal dalam periode. Sertakan pegawai tanpa event. Tambahkan bukti di luar daftar sebagai kasus review agar tidak hilang. | Satu kandidat per pegawai–tanggal, termasuk calon ketidakhadiran. |
| **5. Tentukan kewajiban dan alternatif jadwal** | Periksa hari kerja, libur, organisasi, dan seluruh alternatif reguler yang berlaku. Jangan memilih satu jadwal dengan ID terkecil. | Penanda wajib/tidak/unknown dan daftar alternatif per kandidat. |
| **6. Periksa pasangan event** | Bedakan checktype masuk dan keluar; cocokkan jadwal transaksi. Tandai event berulang, tidak lengkap, atau lintas malam yang belum jelas. | Waktu masuk/pulang, has_masuk/has_pulang, dan kelengkapan. Event ambigu tidak dianggap lengkap hanya karena jumlahnya dua. |
| **7. Validasi lokasi masuk dan pulang** | Bandingkan setiap event dengan lokasi yang diizinkan untuk penugasan WFO/WFH pada tanggal terkait. Simpan hasil TRUE/FALSE/NULL dan alasannya secara terpisah. | Lokasi masuk dan pulang dinilai sendiri-sendiri; kelengkapan presensi tidak berubah karena hasil lokasi. |
| **8. Ringkas izin dan libur per hari** | Jabarkan rentang izin valid menjadi tanggal, periksa approval dan identitas. Ringkas izin dan dedup libur individual sebelum digabungkan. | Maksimal satu ringkasan izin dan satu ringkasan libur per pegawai–tanggal. |
| **9. Tentukan status dan ukuran** | Gabungkan kandidat dengan ringkasan. Utamakan IZIN sah, lalu HADIR. TANPA_KETERANGAN hanya jika kewajiban dan kelengkapan sumber terbukti. Hitung keterlambatan bila acuan sah. Jangan menyamakan presensi lengkap dengan HADIR final atau lokasi tidak sesuai dengan absen. | Satu calon baris fakta, termasuk penanda review untuk kasus belum jelas. |
| **10. Periksa lalu simpan** | Pastikan tidak ada duplikasi, prioritas status benar, dan join tidak menambah baris. Insert pegawai–tanggal baru; update nilai yang berubah. | Fakta uji tersimpan dan dapat ditelusuri ke sumber. |
| **11. Uji ulang** | Uji contoh Andi–Fajar, check-out yang baru masuk, lokasi tanpa referensi, data identik, dan koreksi event/izin/penugasan. Cocokkan jumlah, key, status, dan nilai dengan hasil yang diharapkan. | Bukti bahwa rerun tidak menggandakan data dan koreksi memperbarui hasil. |

Di Hop, pembacaan dapat memakai Table Input; pemilihan field memakai Select Values; percabangan pemeriksaan memakai Filter Rows; ringkasan memakai Sort Rows → Group By; penggabungan ringkasan memakai Merge Join; penyimpanan memakai Insert / Update.

Untuk Merge Join, kedua input harus terurut pada key yang sama. Pastikan ringkasan event/izin/libur unik per pegawai–tanggal sebelum digabungkan ke kandidat. Join alternatif jadwal memang boleh menghasilkan banyak baris kerja, tetapi harus diringkas kembali sebelum menulis fakta. Rujukan: [Merge Join](https://hop.apache.org/manual/latest/pipeline/transforms/mergejoin.html) dan [Group By](https://hop.apache.org/manual/latest/pipeline/transforms/groupby.html).

Urutan sederhana di workflow: **ambil sumber → bentuk kandidat → evaluasi jadwal/event/izin → kelengkapan dan validasi lokasi → klasifikasi → validasi → simpan → rekonsiliasi**. Jalankan tahap berikutnya setelah tahap yang dibutuhkannya berhasil selesai.

## 3 Apakah langkah tersebut bisa dilakukan sekarang

**“Bisa bersyarat” berarti transformasinya bisa dibuat, tetapi sebagian hasil belum boleh dinyatakan final.** Penilaian berikut berdasarkan bukti sumber dalam kesepakatan, bukan audit database terbaru.

| Langkah | Bisa dilakukan? | Kejelasan dan alasannya |
|---|---|---|
| **1. Periode dan pegawai** | **Bisa memilih lingkup uji. Populasi historis lengkap belum terbukti.** | Kategori/status pegawai sekarang tidak menjelaskan tanggal mulai/akhir bekerja. Untuk histori, perlu daftar masa berlaku atau bukti tambahan. |
| **2. Tabel fakta uji** | **Bisa.** | Struktur dan kunci unik dapat dibuat. Ini tidak berarti seluruh kolom langsung memiliki nilai yang sah. |
| **3. Mengambil sumber** | **Bisa.** | Tabel sumber tersedia dalam dokumentasi. Event/izin/libur yang identitas atau tanggalnya tidak valid harus dicatat, bukan dibuang diam-diam. |
| **4. Kandidat pegawai–tanggal** | **Bisa.** | Operasi penggabungan pegawai dengan tanggal dapat dilakukan. Namun kandidat dari populasi yang belum terverifikasi belum membuktikan kewajiban hadir. |
| **5. Kewajiban dan alternatif** | **Bisa bersyarat.** | Semua alternatif reguler dapat ditemukan. Yang belum terbukti lengkap adalah organisasi dan masa berlaku jadwal pada tanggal historis. Tidak boleh memakai status aktif sekarang untuk seluruh masa lalu. |
| **6. Pasangan event** | **Bisa untuk kasus jelas; kasus lain review.** | Checktype membedakan masuk/keluar. Aturan event berulang, manual, tanpa pasangan, dan lintas malam belum seluruhnya final. |
| **7. Validasi lokasi** | **Bisa dibuat; hasil nyata bersyarat.** | Kolom seperti location, latlong, jarak, dan is_wfh tercatat pada inventaris event. Makna, satuan jarak, sumber lokasi resmi, radius, penugasan WFO/WFH, dan masa berlakunya belum diverifikasi untuk rancangan ini. Tidak boleh menyimpulkan lokasi sah hanya dari is_wfh atau koordinat yang terisi. |
| **8. Izin dan libur** | **Bisa untuk data valid.** | Izin setengah hari, overlap, konflik identitas, rentang tidak jelas, dan prioritas izin pada hari libur masih membutuhkan keputusan. Approval false tidak otomatis berarti ditolak. |
| **9. Status dan ukuran** | **Bisa bersyarat.** | IZIN/HADIR dapat dinilai pada kasus yang cukup bukti. TANPA_KETERANGAN seluruh histori belum sah tanpa populasi wajib, jadwal berlaku, kalender lengkap, serta penutupan event dan izin. |
| **10. Validasi dan simpan** | **Bisa.** | Hasil belum pasti tetap disimpan untuk review sesuai kesepakatan, dengan status dapat NULL dan dikeluarkan dari KPI final. |
| **11. Rerun dan koreksi** | **Bisa.** | Insert/update menangani key baru atau nilai berubah. Jika koreksi memindahkan tanggal atau menghapus bukti sumber, key lama juga perlu direkonsiliasi; insert/update saja tidak menghapusnya. |

**Yang perlu dipastikan khusus untuk lokasi:** sumber penugasan WFO/WFH per pegawai–tanggal; lokasi yang diizinkan untuk masing-masing jenis event; radius atau aturan pembanding beserta satuannya; masa berlaku lokasi; dan pengecualian seperti dinas luar. Data event tanpa referensi tersebut hanya membuktikan lokasi yang tercatat, belum membuktikan kepatuhannya. WFH tidak otomatis diwajibkan presensi di kantor ataupun pada satu lokasi rumah tanpa aturan.

Batas yang penting saat menjalankan langkah di atas:

- **Lengkap dan sesuai lokasi adalah dua hasil berbeda.** Satu masuk dan satu pulang yang telah dipasangkan dapat menghasilkan lengkap meskipun salah satu lokasinya tidak sesuai. NULL pada validasi lokasi bukan FALSE.
- **Tidak ada event bukan otomatis absen.** TANPA_KETERANGAN membutuhkan bukti wajib hadir dan data yang sudah lengkap. Check-in tanpa checkout tampil sebagai belum lengkap; setelah batas evaluasi, kasus belum terselesaikan mengikuti aturan review, bukan disamakan dengan tidak ada presensi.
- **Izin sah tidak memerlukan pasangan presensi untuk membuktikan izin.** Validasi izin dilakukan terpisah; ketidakjelasan identitas, cakupan, atau jenis izin tetap diperiksa.
- **Beberapa shift bukan otomatis ambigu.** Menyimpan semua alternatif dan memeriksa apakah salah satunya terpenuhi bisa dilakukan. Jika lebih dari satu terpenuhi, pemilihan shift tunggal dan ukuran keterlambatan harian masih memerlukan aturan.
- **Histori yang tidak tercatat tidak bisa direkonstruksi secara pasti dari snapshot sekarang.** Data tambahan atau keputusan eksplisit diperlukan; mengganti transform Hop tidak menyelesaikan kekurangan informasi.

Untuk penyimpanan, Insert / Update dapat memasukkan baris baru, memperbarui nilai berbeda, dan melewati nilai identik. Jangan memasukkan waktu proses baru sebagai nilai pembanding pada setiap rerun karena itu akan membuat semua baris tampak berubah. Rujukan: [Insert / Update](https://hop.apache.org/manual/latest/pipeline/transforms/insertupdate.html).

**Hasil awal yang realistis:** satu periode uji menghasilkan satu fakta per pegawai–tanggal dengan masuk dan pulang, kelengkapan, serta hasil lokasi terpisah. Tampilan lengkap dan lokasi tidak sesuai dapat muncul bersamaan; bukti sumber dapat ditelusuri, kasus belum jelas ditandai, dan rerun tidak menggandakan data. Kelengkapan KPI seluruh histori baru dapat dinyatakan setelah bukti kewajiban historis dan aturan yang masih terbuka diselesaikan.
