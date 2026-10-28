# Penerapan schema mart dan serving — 28 Oktober 2026

Kontrak: [STTM curated ke serving](sttm-curated-to-serving-kehadiran.md).
Target: `epresensi-mart-postgres / mart_bkd` (PostgreSQL 16).

## Hasil

Inspeksi menunjukkan mart_bkd kosong, sehingga penyesuaian dilakukan dengan
membentuk objek baru sesuai kontrak, bukan mengubah atau menghapus fakta lama.
Schema analytics pada database dashboard lama tetap terpisah; tidak ada cutover.

Objek committed:

| Schema | Objek |
|---|---|
| mart_kehadiran | dim_calendar, dim_pegawai, dim_departemen, fact_kehadiran_daily |
| serving | agg_kehadiran_departemen_harian, attendance_date_state |
| serving | v_kehadiran_departemen_harian, v_kehadiran_instansi_harian, v_departemen_filter |
| etl_control | mart_batch |

Dimensi pegawai/departemen mempunyai constraint interval efektif tidak overlap
menggunakan extension btree_gist. Fact memiliki PK pegawai-tanggal, FK dimensi,
CHECK seluruh 12 measure terhadap flag curated, dan indeks tanggal/departemen.
Agregasi memakai bigint dan constraint rekonsiliasi. Rate view dihitung dari
pembilang/penyebut, termasuk pada ALL, dengan NULL saat denominator nol.

Kontrol kelengkapan tanggal default false. View mempertahankan provisional jika
state belum tersedia/tidak lengkap/belum closed, atau fact masih review/nonfinal.
Fact nonaktif tetap dapat disimpan dengan measure nol. Departemen UNKNOWN key 0
menjamin row yang belum terpetakan tetap masuk total instansi.

## Validasi

1. DDL dan fixture dijalankan dalam transaksi rollback: lulus.
2. DDL dipasang dan committed.
3. Uji kontrak dijalankan lagi pada schema committed dengan fixture rollback:
   lulus. Fixture memakai enam pegawai aktif dan satu nonaktif, dua tanggal,
   dua departemen terpetakan dan UNKNOWN.
4. Verifikasi akhir: seluruh tabel data/kontrol kosong, kecuali satu anggota
   dim_departemen UNKNOWN. Tidak ada fixture bisnis tertinggal.

Kasus yang diperiksa: seluruh 12 measure, total ALL termasuk UNKNOWN, dua shift
menjadi measure 1, izin penuh tetap ber-event, denominator nol/nonaktif,
provisional meskipun state complete/closed, PK duplicate, FK yang tidak ditemukan,
interval dimensi overlap, measure salah, serta close dengan cakupan tidak lengkap.
Ini uji schema dan query; bukan uji pipeline incremental atau benchmark dashboard.

Bukti:

- [DDL](../sql/mart/20261028_attendance_daily.sql)
- [Schema sebelum penerapan](../tests/mart_serving_20261028/schema_before.sql)
- [Dry-run](../tests/mart_serving_20261028/dry_run.txt)
- [Log penerapan](../tests/mart_serving_20261028/apply.txt)
- [Uji kontrak](../tests/mart_serving_20261028/contract.sql)
- [Hasil uji](../tests/mart_serving_20261028/contract_results.txt)
- [Verifikasi akhir](../tests/mart_serving_20261028/verification.txt)

## Operasi dan tahap berikutnya

DDL satu kali; menjalankan ulang terhadap schema existing akan gagal dan rollback,
bukan membuang objek. Pengulangan tes fixture hanya untuk target kosong ini;
jangan jalankan fixture langsung pada database yang sudah berisi data bisnis.

Belum ada pemuatan dimensi/populasi bisnis, pipeline curated→fact, outbox durable,
refresh agregasi otomatis, scheduler, atau perubahan dataset/chart dashboard.
Tabel kontrol disiapkan untuk kontrak tahap berikutnya, belum diisi otomatis.
Loader harus memvalidasi kesesuaian ID sumber dan interval dimensi untuk setiap
FK; FK sendiri hanya membuktikan keberadaan key. Refresh partisi lama dan baru,
delete, retry/idempotensi dan checkpoint atomik harus diuji saat pipeline dibuat.
Hak SELECT akun dashboard/ETL disiapkan saat integrasi akun dan cutover.
Kebijakan lintas malam, backfill populasi historis dan finalisasi masih mengikuti
batas curated; schema baru tidak menyelesaikan kebijakan tersebut secara implisit.
