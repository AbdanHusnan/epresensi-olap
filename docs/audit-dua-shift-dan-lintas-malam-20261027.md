# Audit dua shift dan lintas tengah malam

Pemeriksaan 27 Oktober 2026, read-only pada database restore `dbabsen_restore`. Tidak mengubah master, transaksi, atau pipeline. Angka bukan metrik pegawai aktif atau kewajiban hadir; seluruh event checktype 1/2 dalam periode diperiksa tanpa filter status pegawai dan status shift saat ini.

## Cakupan dan hasil dua shift

Periode transaksi 1–31 Agustus 2026 (`created_at`), 3.152.168 event masuk/pulang. Satu unit hitung adalah pegawai × departemen pada transaksi × tanggal kalender; bukan pegawai unik bulanan dan belum tanggal kerja hasil pairing.

- 24.878 kombinasi memiliki lebih dari satu ID shift hasil lookup `t_checkinout.jadwal_id → m_jadwal.id → m_jadwal.jenis → m_shift.id`.
- 12.464 kombinasi memiliki check-in pada setidaknya dua shift.
- 1.387 kombinasi memiliki setidaknya dua shift yang masing-masing memuat check-in dan check-out, dengan masuk paling awal mendahului pulang paling akhir. Ini penyaringan bukti transaksi, bukan pairing final atau bukti dua penugasan sah.
- 2.062 kombinasi multi-shift terkait jam yang berindikasi lintas malam, mengutamakan jam pada transaksi, lalu master jika NULL.
- 40 event tidak memperoleh ID shift melalui lookup. Dua event memiliki `work_code` berbeda dari ID shift hasil lookup (termasuk kemungkinan NULL menurut `IS DISTINCT FROM`).

Output tambahan `known_owners_match` menggunakan BOOL_AND dan mengabaikan pemilik shift NULL: 68 kombinasi pada 26 departemen. Angka ini **bukan** jumlah kasus yang semua shift-nya pasti dimiliki departemen transaksi. Contoh pemilik NULL dapat berupa shift bersama; interpretasi bisnis belum dikonfirmasi.

## Contoh konkret satu pegawai, dua shift, departemen sama

Identitas pegawai tidak diekspor. Setiap sampel mengelompokkan pegawai yang sama di database.

Departemen **36545 — BIDANG PELAYANAN MEDIK**, 2 Agustus 2026:

| Shift | Jadwal | Check-in | Check-out |
|---|---|---|---|
| 22731 — SHIFT PAGI | 125516, 07.00–14.00 | 06:56:45 | 14:07:20 |
| 22732 — SHIFT SIANG | 125523, 14.00–21.00 | 13:06:38 | 21:29:50 |

Kedua shift dimiliki departemen 36545. Keempat event nonmanual. Check-in shift siang terjadi sebelum check-out shift pagi; jangan memasangkan dengan urutan masuk/pulang global atau menyatakan dua sesi tidak boleh tumpang tindih. Kewajaran jam aktual tetap perlu review.

Departemen **36274 — INSTALASI FARMASI**, 1 Agustus 2026:

- Shift 23376 PAGI FARMASI 3: masuk 07:05:14 **dan 14:01:14**, pulang 14:02:58.
- Shift 23406 SIANG FARMASI 3: masuk 14:02:34, pulang 21:04:12.

Ini menunjukkan dua shift sekaligus pengulangan check-in dalam salah satunya. Tidak boleh mengubah setiap check-in menjadi sesi baru tanpa aturan.

## Dua ID shift belum tentu dua sesi kerja

Sampel departemen 30151, 3 Agustus 2026: shift 32855 `SET. DPRD` dan shift bersama 33064 `PEMPROV 5 HARI KERJA (2026)` sama-sama memiliki jam rencana 07.30–16.00. Check-in masing-masing 06:25:12 dan 06:25:18; check-out 16:00:37 dan 16:00:47. Ini kandidat pencatatan ganda/alternatif, bukan bukti pasti dua shift kerja berurutan. Jangan otomatis digabung atau dihitung dua sesi sah.

## Bukti transaksi lintas tengah malam

Master mempunyai 9.909 rincian jadwal dengan jam keluar < jam masuk, pada 1.483 shift. Ini indikasi lintas malam, bukan validasi semua jam master (ada pola yang tetap memerlukan review).

Pemeriksaan lanjutan memakai **500.000 ID transaksi terbaru**, kemudian disaring ke Agustus 2026. Sampel tidak mewakili seluruh bulan, dan ID terbaru bukan jaminan urutan tanggal. Ditemukan **5.343 kandidat pasangan pada 313 departemen**: satu check-in pada hari D dan satu check-out pada D+1 untuk pegawai, departemen transaksi, serta shift yang sama, dengan durasi positif maksimum 24 jam dan indikasi jadwal malam. Seluruh kandidat tersebut memiliki ID jadwal masuk dan pulang yang berbeda. Batas 24 jam hanya filter eksplorasi, belum kebijakan produksi; tidak menerapkan filter manual/approval pada audit lintas malam ini.

Contoh departemen 30016, shift **35471 — SHIFT MALAM ISLAMIC CENTRE SURABAYA**, jam rencana 19.00–07.00:

| Event | Timestamp | jadwal_id | work_code/shift_id | Hari jadwal |
|---|---|---|---|---|
| Masuk | 2026-08-26 18:54:15 | 212665 | 35471 | Wed |
| Pulang | 2026-08-27 07:41:00 | 212666 | 35471 | Thu |
| Masuk berikutnya | 2026-08-27 18:32:56 | 212666 | 35471 | Thu |

Dua event pada 27 Agustus memakai jadwal harian yang sama, tetapi secara urutan dan rentang shift merupakan kandidat dua sesi berbeda: pulang untuk sesi sebelumnya dan masuk untuk sesi berikutnya. Mengelompokkan pegawai × tanggal × jadwal saja akan mencampur keduanya.

Dengan demikian, aturan tanggal kerja yang diusulkan adalah tanggal mulai sesi untuk pasangan yang sudah dapat ditentukan. Check-out tanpa check-in, jam yang berubah, atau pasangan ganda tetap unknown/review; jangan menggeser semua check-out shift malam ke D-1 tanpa pemeriksaan rentang dan konteks.

Audit lama `A03_WIN06` mensyaratkan ID jadwal sama antara D dan D-1. Temuan baru menjelaskan mengapa syarat itu dapat melewatkan pasangan nyata; hasil nol pada audit lama bukan bukti tidak adanya pasangan lintas hari.

Catatan eksekusi: percobaan pertama sampel dibatalkan karena planner memilih nested-loop pada estimasi CTE yang terlalu kecil. Query diselesaikan setelah menonaktifkan nested-loop dan JIT hanya pada transaksi read-only tersebut. Tidak ada perubahan konfigurasi global.

## Implikasi rancangan

1. Pertahankan event mentah dan seluruh referensinya. Simpan tanggal kalender event terpisah dari tanggal kerja sesi.
2. Bentuk kandidat sesi dengan pegawai, identitas shift, jadwal yang berlaku, dan rentang waktu; `jadwal_id` harian saja belum cukup untuk lintas hari.
3. Pisahkan pengulangan event, kandidat dua shift berurutan, kandidat shift alternatif/duplikat, dan pasangan lintas malam. Konflik diberi alasan review, tidak diselesaikan MIN/MAX harian.
4. Satu sesi memiliki identitas tersendiri serta referensi event masuk/pulang; event yang ambigu tidak dipakai pada dua sesi sekaligus tanpa keputusan eksplisit.
5. Detail sesi diagregasi ke pegawai × tanggal kerja untuk metrik orang. Dashboard aktivitas per tanggal kalender tetap dapat dibuat, tetapi tanggal tersebut harus diberi definisi yang berbeda dari tanggal kerja sesi.
6. Dua sesi tercatat tidak membuktikan roster wajib. Dashboard populasi aktif tetap mengikuti definisi admin; ketidaklengkapan sesi dan tidak ada aktivitas harian adalah ukuran berbeda.

## Artefak

- [Query dua shift](../tests/source_to_curated_20261027/audit_multi_shift.sql)
- [Hasil dua shift, sampel anonim](../tests/source_to_curated_20261027/audit_multi_shift_results.txt)
- [Query sampel lintas malam](../tests/source_to_curated_20261027/audit_overnight_pair.sql)
- [Hasil sampel lintas malam](../tests/source_to_curated_20261027/audit_overnight_pair_results.txt)
