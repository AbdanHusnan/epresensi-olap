# Profiling Awal BKD Jatim - Kelompok A

Sumber: `dbabsen_restore`, snapshot production 1 September 2026. Semua skrip berisi `SELECT` dan transaksi `READ ONLY`. Tidak ada penulisan data. Hasil berupa agregat dengan hitungan 1-4 disamarkan.

## Urutan eksekusi

1. `A01_histori.sql`: **A1, A2, A3, A4, A7 (timestamp), A10**. Sekali scan logis untuk seluruh histori `t_checkinout`. Query ini berat (89.475.438 event); jalankan saat akses restore tersedia dan aktivitas rendah. Output: `test_id, metrik, segmen, nilai, denominator, persen`.
2. `A02_jendela.sql`: **A1/A2/A3/A4/A7 (sizing window), A5, A6, A7 (event berulang)**. Empat statement, masing-masing terbatas pada 2025-09-01 sampai sebelum 2026-09-01. Output hasil per statement disalin terpisah.
3. `A03_klasifikasi_lintas_hari.sql`: **A8, A9**. Tiga statement: kelas event dan multi-jadwal reguler; master jadwal malam; kandidat checkout-only. 

## Penamaan query

- `A-HIST-01`: A1, A2, A3, A4, A7, A10 (histori penuh, groupingsets)
- `A-WIN-01`: ukuran dampak pegawai-hari/departemen untuk A1, A2, A3, A4, A7
- `A-WIN-02`: A5, duplikat berdasarkan signature 8 kolom + near duplicate <1 menit
- `A-WIN-03`: A6, histogram event per pegawai-tanggal kalender
- `A-WIN-04`: A7, event checktype berulang per pegawai-jadwal-tanggal kalender
- `A-WIN-05`: A8, kelas berdasarkan jadwal/shift pada snapshot dan multi-jadwal reguler
- `A-MASTER-01`: A9, jumlah jadwal berindikasi lintas tengah malam
- `A-WIN-06`: A9, kandidat checkout-only dan indikasi check-in pada D-1

## Instruksi penggunaan

- Jalankan pada database restore, **bukan production**. Biarkan nilai `statement_timeout` bekerja; bila timeout, laporkan error dan durasi, jangan langsung jalankan ulang berkali-kali.
- Jika aplikasi SQL hanya dapat mengeksekusi satu statement, jalankan `BEGIN TRANSACTION READ ONLY`, `SET LOCAL statement_timeout='15min'`, kemudian satu query, dan `COMMIT`. Skrip memiliki satu transaksi untuk masing-masing file; hasil query tidak saling bergantung.
- Jangan menjalankan semua query paralel. Hasil cukup disalin sebagai agregat, **tanpa data baris per pegawai**.
- `pegawai_hari_teramati` = kombinasi pegawai-tanggal kalender **yang memiliki event**, bukan seluruh employee-day yang diharapkan atau denominator KPI.
- `tanggal kerja` masih **proksi** `created_at::date`; belum ditafsirkan sebagai tanggal mulai shift lintas hari.
- `departemen_snapshot` = `m_pegawai.departemen` di dump, belum dapat membuktikan departemen historis pada tanggal event.
- `reguler_aktif_snapshot` menggunakan nama yang mengandung REGULAR/REGULER dan `m_shift.status IS TRUE` **saat snapshot**; bukan jaminan status shift historis.
- `signature identik` hanya membandingkan 8 kolom profil (tidak seluruh kolom dalam tabel). Near-duplicate hanya indikasi kemiripan temporal, bukan penghapusan/correction rule. Query A5 membaca tambahan 1 menit sebelum jendela untuk mengurangi bias tepi awal, tetapi hanya menghitung event yang masuk jendela.
- Nilai `created_at` setelah **tanggal** snapshot menggunakan ambang `> 2026-09-01`. Event di tanggal 1 September dicatat terpisah karena jam batas dump tidak terkonfirmasi.
- Pada A9, kolom jam jadwal diasumsikan dapat dibaca sebagai `time` untuk pengujian **saja**. Jika cast `::time` gagal, simpan error untuk validasi skema/sumber, jangan melakukan pembersihan/cast alternatif sembarang.
- Sampel checkout pada kalender 2026-09-01 tidak digunakan sebagai bukti kelengkapan sesi 2026-08-31 karena snapshot 1 September parsial.
- Null `created_at` tidak dapat dipetakan ke employee-day jendela dan hanya terukur pada agregat histori.
- Pengecekan tahun ekstrem 0008, 0202, 2031, 2055, 3036 berada pada tabel izin/libur, sehingga dicakup saat Kelompok B dan D, bukan dikoreksi atau dicampurkan ke Kelompok A.

## Yang perlu ditempel ke chat

Salin output per query ID beserta row header, denominator, serta error/timeout (jika ada). Data pegawai tidak perlu dan tidak boleh dikirim. Tidak ada query ad-hoc pada paket ini (AD-HOC = 0).

## Exit criteria Kelompok A

- A1-A10 terukur untuk seluruh subtest, atau kegagalan query dicatat sebagai blocker teknis.
- Satuan event vs pegawai-hari tidak tercampur. Denominator dan pembatasan proksi dinyatakan eksplisit.
- Jumlah pegawai-hari serta departemen snapshot terdampak terukur pada jendela 12 bulan, atau gap hasil diidentifikasi.
- C-001, C-002 dan DEP-S04 tetap berstatus open: tidak menetapkan rule pemenang, tidak menyimpulkan MAX(timestamp).
- Temuan dipetakan ke PF-ID, DS/GAP/OP/C, klasifikasi, severity usulan, disposisi, dan eskalasi/pertanyaan sumber.
