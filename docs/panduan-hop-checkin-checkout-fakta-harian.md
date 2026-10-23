# Panduan Apache Hop untuk memperbarui fakta masuk dan pulang

Panduan ini menunjukkan cara membuat satu baris fakta per pegawai–tanggal: check-in membuat baris, lalu check-out memperbarui baris yang sama. Check-in tetap tersimpan dan tetap masuk indikator Sudah masuk. Kelengkapan presensi dan validasi lokasi dinilai terpisah.

Acuan keputusan: [rancangan fakta terbaru](kelayakan-dan-panduan-transformasi-fact-kehadiran-hop.md). Panduan ini adalah latihan dengan data dummy, bukan pipeline yang sudah dibuat atau dijalankan. Tidak ada pemuatan dimensi pada latihan ini.

## 1 Bentuk tabel latihan dan hasil yang dituju

Gunakan tabel terpisah dari public.fact_kehadiran yang sudah memiliki data dan aturan legacy. Jalankan SQL berikut sekali pada database pengembangan yang dipilih, memakai akun yang memiliki hak membuat tabel. Writer Hop memerlukan SELECT, INSERT, UPDATE dan akses sequence terkait. SQL ini belum dieksekusi oleh panduan.

```sql
CREATE TABLE public.fact_presensi_latihan (
    fact_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pegawai_id_sumber bigint NOT NULL,
    tanggal date NOT NULL,
    waktu_masuk timestamp,
    waktu_pulang timestamp,
    has_masuk boolean NOT NULL,
    has_pulang boolean NOT NULL,
    is_presensi_lengkap boolean,
    jumlah_event integer NOT NULL,
    perlu_review boolean NOT NULL,
    alasan_review text,
    UNIQUE (pegawai_id_sumber, tanggal)
);
```

Tabel ini sengaja hanya menguji mekanisme masuk–pulang. Ia belum menentukan HADIR final, izin, kewajiban hadir, lokasi, atau keterlambatan.

| Tahap | ID fakta | Pegawai | Tanggal | Masuk | Pulang | Sudah masuk | Lengkap |
|---|---|---|---|---|---|---|---|
| Setelah run pagi | ID yang dibentuk database | 1001 | 2026-08-03 | 07.55 | NULL | TRUE | FALSE |
| Setelah run sore | ID yang sama | 1001 | 2026-08-03 | 07.55 | 16.05 | TRUE | TRUE |

**Key pencocokan Hop adalah pegawai_id_sumber + tanggal, bukan event_id atau fact_id.** Fact_id dibentuk database hanya saat insert. Dua event sumber tetap memiliki identitas masing-masing.

## 2 Langkah membuat dan menjalankan pipeline

### Langkah 1 Buat pipeline di GUI

1. Buka project presensi dan environment yang menunjuk database pengembangan.
2. Buat pipeline baru, misalnya latihan_fakta_harian.hpl.
3. Pilih run configuration local dengan Hop Engine.
4. Tambahkan tiga transform berikut dan hubungkan berurutan:

**Table Input “Baca ringkasan dummy” → Select Values “Pilih kolom fakta” → Insert / Update “Simpan fakta harian”.**

Pada latihan ini, SQL di Table Input membuat data dummy dan ringkasannya agar Anda bisa langsung melihat perilaku insert/update tanpa menyiapkan sumber OLTP. Pengolahan event nyata dibahas pada bagian 3.

### Langkah 2 Atur parameter skenario

Pada pengaturan pipeline, tambahkan parameter `SKENARIO`, default `PAGI`. Nilai latihan yang digunakan adalah PAGI atau SORE.

Pada Table Input:

- Pilih koneksi presensi_target yang mengarah ke database tempat tabel latihan dibuat.
- Aktifkan penggantian variabel dalam SQL, umumnya berlabel Replace variables in script.
- Masukkan SQL berikut.

```sql
WITH event_dummy(event_id, pegawai_id_sumber, tanggal, checktype, waktu) AS (
    VALUES
      (101::bigint, 1001::bigint, DATE '2026-08-03', 1,
       TIMESTAMP '2026-08-03 07:55:00'),
      (102::bigint, 1001::bigint, DATE '2026-08-03', 2,
       TIMESTAMP '2026-08-03 16:05:00')
), event_run AS (
    SELECT * FROM event_dummy
    WHERE '${SKENARIO}' = 'SORE'
       OR ('${SKENARIO}' = 'PAGI' AND event_id = 101)
), ringkasan AS (
    SELECT pegawai_id_sumber, tanggal,
      count(*)::integer AS jumlah_event,
      count(*) FILTER (WHERE checktype = 1) AS n_masuk,
      count(*) FILTER (WHERE checktype = 2) AS n_pulang,
      count(*) FILTER (WHERE checktype IS NULL OR checktype NOT IN (1,2)) AS n_lain,
      min(waktu) FILTER (WHERE checktype = 1) AS calon_masuk,
      min(waktu) FILTER (WHERE checktype = 2) AS calon_pulang
    FROM event_run
    GROUP BY pegawai_id_sumber, tanggal
)
SELECT pegawai_id_sumber, tanggal,
  CASE WHEN n_masuk = 1 THEN calon_masuk END AS waktu_masuk,
  CASE WHEN n_pulang = 1 THEN calon_pulang END AS waktu_pulang,
  n_masuk > 0 AS has_masuk,
  n_pulang > 0 AS has_pulang,
  CASE
    WHEN n_lain > 0 OR n_masuk > 1 OR n_pulang > 1 THEN NULL::boolean
    WHEN n_masuk = 1 AND n_pulang = 1 AND calon_pulang < calon_masuk
      THEN NULL::boolean
    WHEN n_masuk = 1 AND n_pulang = 1 THEN true
    ELSE false
  END AS is_presensi_lengkap,
  jumlah_event,
  (n_lain > 0 OR n_masuk > 1 OR n_pulang > 1
   OR (n_masuk = 1 AND n_pulang = 1 AND calon_pulang < calon_masuk))
    AS perlu_review,
  CASE
    WHEN n_lain > 0 THEN 'JENIS_EVENT_BELUM_DISETUJUI'
    WHEN n_masuk > 1 OR n_pulang > 1 THEN 'PASANGAN_EVENT_AMBIGU'
    WHEN n_masuk = 1 AND n_pulang = 1 AND calon_pulang < calon_masuk
      THEN 'URUTAN_WAKTU_TIDAK_VALID'
  END AS alasan_review
FROM ringkasan;
```

MIN di sini hanya menghasilkan waktu yang dipakai jika jumlah jenis event tepat satu. Jika ada beberapa masuk/pulang, waktu terkait tidak dipilih sembarang dan kelengkapan menjadi NULL. SQL ini khusus kasus hari yang sama dengan satu jadwal yang sudah jelas; bukan aturan pairing seluruh histori.

Pada latihan hari berjalan, masuk tanpa pulang berarti belum lengkap, bukan otomatis pelanggaran. `perlu_review` di tabel latihan hanya menandai konflik event. Setelah batas evaluasi, proses produksi harus menambahkan pemeriksaan presensi tidak lengkap sesuai kesepakatan.

### Langkah 3 Preview sebelum menulis

Preview transform Table Input dengan SKENARIO=PAGI. Harus ada tepat satu baris:

- pegawai_id_sumber = 1001, tanggal = 2026-08-03.
- waktu_masuk = 07.55, waktu_pulang = NULL.
- has_masuk = TRUE, has_pulang = FALSE.
- is_presensi_lengkap = FALSE, jumlah_event = 1.

Jika tidak ada baris, periksa nilai parameter. Jika variabel belum terganti, periksa opsi penggantian variabel. Preview tahap input dahulu; jangan menjalankan output untuk menguji query yang belum benar.

### Langkah 4 Pilih kolom target

Pada Select Values, pilih semua kolom hasil SQL. Pertahankan tipe tanggal/waktu dan boolean. Jangan mengubah NULL menjadi string kosong, 00.00, atau FALSE.

Tidak perlu membuat atau membawa fact_id ke output; kolom itu diisi database.

### Langkah 5 Konfigurasi Insert / Update

Isi:

| Pengaturan | Nilai |
|---|---|
| Connection | presensi_target |
| Target schema | public |
| Target table | fact_presensi_latihan |
| Commit size | 100 untuk latihan |
| Don't perform any updates | Tidak dicentang |
| Jumlah salinan transform | 1 untuk latihan |

Pada bagian lookup keys:

| Table field | Comparator | Stream field |
|---|---|---|
| pegawai_id_sumber | = | pegawai_id_sumber |
| tanggal | = | tanggal |

Pada bagian Update Fields:

| Table field dan Stream field | Update |
|---|---|
| pegawai_id_sumber | N |
| tanggal | N |
| waktu_masuk | Y |
| waktu_pulang | Y |
| has_masuk | Y |
| has_pulang | Y |
| is_presensi_lengkap | Y |
| jumlah_event | Y |
| perlu_review | Y |
| alasan_review | Y |

Masukkan kedua key ke field insert dengan Update=N agar ikut ditulis saat baris baru dibuat tetapi tidak diubah saat update. Jangan memasukkan fact_id. Insert / Update melakukan lookup, memasukkan baris baru, memperbarui nilai berbeda, dan melewati nilai identik. Lihat [dokumentasi resmi Insert / Update](https://hop.apache.org/manual/latest/pipeline/transforms/insertupdate.html).

### Langkah 6 Run pagi

Jalankan dengan SKENARIO=PAGI. Kemudian periksa:

```sql
SELECT * FROM public.fact_presensi_latihan
WHERE pegawai_id_sumber = 1001 AND tanggal = DATE '2026-08-03';
```

Catat fact_id yang dihasilkan. Nilainya tidak harus 1; yang penting identitas ini tetap sama pada update berikutnya.

### Langkah 7 Run sore

Ubah SKENARIO=SORE. Preview harus menghasilkan satu ringkasan yang berisi **kedua event**, bukan checkout saja. Jalankan pipeline.

Query yang sama harus menghasilkan satu baris dengan fact_id tetap, waktu masuk tetap 07.55, waktu pulang menjadi 16.05, jumlah_event menjadi 2, dan is_presensi_lengkap menjadi TRUE.

**Jangan mengirim ringkasan checkout saja ke Insert / Update.** Itu dapat membawa waktu_masuk=NULL dan has_masuk=FALSE lalu menimpa check-in sebelumnya. Hitung ulang seluruh event pegawai–tanggal yang terdampak terlebih dahulu.

### Langkah 8 Uji rerun dan indikator dashboard

Jalankan SORE sekali lagi. Jumlah fakta dan seluruh nilai harus tetap sama. Gunakan query berikut untuk memeriksa indikator latihan:

```sql
SELECT
  count(*) FILTER (WHERE has_masuk) AS sudah_masuk,
  count(*) FILTER (WHERE is_presensi_lengkap IS TRUE) AS presensi_lengkap
FROM public.fact_presensi_latihan
WHERE tanggal = DATE '2026-08-03';
```

Setelah PAGI: sudah_masuk=1 dan presensi_lengkap=0. Setelah SORE: keduanya 1. Check-in tidak dihapus; indikator memang tumpang tindih.

Jangan menjalankan PAGI kembali setelah SORE pada target yang sama kecuali sengaja menguji snapshot mundur: PAGI merupakan sumber parsial yang lebih lama dan akan menimpa hasil sore. Produksi harus memakai snapshot terkini yang lengkap serta menghindari dua run yang saling menimpa.

## 3 Menerapkan pola latihan pada data nyata

**Mekanisme insert/update ini bisa dilakukan sekarang.** Menghasilkan HADIR final, kelengkapan lintas malam, dan kepatuhan lokasi memerlukan pengolahan tambahan berikut.

| Tahap produksi | Yang dilakukan di Hop | Kelayakan dan batas |
|---|---|---|
| Ambil perubahan | Table Input membaca event baru/koreksi dan menyimpan raw event menurut ID sumber | Bisa. ID baru saja tidak mendeteksi update lama atau penghapusan. |
| Tentukan hari terdampak | Kumpulkan pegawai dan tanggal kerja yang berubah | Bisa; koreksi tanggal harus memasukkan tanggal lama dan baru. Lintas malam mengikuti aturan pairing. |
| Baca kembali bukti lengkap | Table Input mengambil seluruh event untuk pegawai–tanggal terdampak dari sumber/staging lengkap | Wajib sebelum upsert. Jangan hanya menghitung batch checkout terbaru. |
| Pisahkan jenis event | Buat field indikator masuk/pulang menurut checktype yang diverifikasi | Bisa; checktype lain tetap dilaporkan. |
| Pasangkan dan ringkas | Sort Rows → Group By untuk kasus yang kunci tanggal kerja dan jadwalnya sudah ditentukan | Group By memerlukan input terurut. Dua event tidak otomatis satu pasangan sah. |
| Periksa lokasi | Cocokkan masuk dan pulang dengan penugasan WFO/WFH dan lokasi yang berlaku | Bersyarat: sumber penugasan, radius/aturan, dan masa berlaku harus tersedia. |
| Tentukan hasil bisnis | Gabungkan izin, kewajiban hari kerja, hasil pasangan, dan review | IZIN sah mendahului HADIR; lengkap tidak otomatis HADIR final. |
| Simpan fakta | Insert / Update menurut pegawai–tanggal | Bisa; sesuaikan mapping dengan skema target yang sebenarnya. |
| Rekonsiliasi | Cocokkan hasil baru dengan target dan tangani key lama yang hilang | Diperlukan untuk pembatalan, penghapusan, atau pemindahan tanggal. |

Bila memakai transform Group By di kanvas, kelompokkan berdasarkan key yang sudah disahkan pada tahap sebelumnya. Ringkas per alternatif dahulu bila diperlukan, kemudian kembali ke pegawai–tanggal sebelum output. Rujukan: [Group By](https://hop.apache.org/manual/latest/pipeline/transforms/groupby.html).

Untuk lokasi, perluas stream dengan lokasi_masuk_sesuai dan lokasi_pulang_sesuai yang bernilai TRUE/FALSE/NULL, serta alasan pemeriksaan. Hitung is_presensi_lengkap dari pasangan event, bukan dari kedua flag lokasi. Dengan demikian pegawai bisa masuk indikator Presensi lengkap sekaligus Lokasi tidak sesuai. NULL karena referensi tidak ada tidak dihitung sebagai tidak sesuai. Penambahan field ke tabel target dan mapping Hop harus dilakukan sebelum mengirimkannya.

Indikator Belum check-in tidak bisa dibentuk lengkap dari latihan event ini: diperlukan kandidat seluruh pegawai yang wajib hadir. View dashboard lama juga belum otomatis mengikuti hasil pipeline baru; sesuaikan query dan penyaringannya sebelum dipakai.

Nama fisik target existing dapat berbeda: pegawai_id legacy dan is_expected_workday tercatat dalam implementasi sebelumnya, sedangkan rancangan baru memakai pegawai_id_sumber dan is_wajib_kerja. Periksa metadata tabel dan mapping terlebih dahulu; jangan langsung mengarahkan tabel latihan ke fact_kehadiran.

Pada workflow produksi, susun aksi berurutan: **ekstraksi → daftar hari terdampak → hitung ulang → validasi → upsert → rekonsiliasi**. Lanjutkan hanya setelah tahap sebelumnya berhasil. Untuk awal, jalankan manual per tanggal; otomatisasi dijalankan setelah uji koreksi dan rerun lolos. Latihan ini belum menguji performa seluruh histori ataupun aturan bisnis yang masih terbuka.
