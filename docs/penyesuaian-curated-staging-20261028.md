# Penyesuaian curated staging — 28 Oktober 2026

> **Pembaruan ETL 28 Oktober 2026:** pipeline Hop dan fungsi incremental raw ke
> curated sudah dipasang dan diuji. Data bisnis belum dimuat; producer raw masih
> perlu mengirim manifest ID berubah. Lintas malam tetap provisional/unresolved.
> Petunjuk dan batas implementasi ada di [panduan ETL](../hop/README.md).

## Hasil

Migrasi diterapkan ke `epresensi-staging-postgres / staging_bkd`.
Schema `curated` kini berisi lima tabel kosong sesuai kontrak populasi aktif:

| Tabel | Grain |
|---|---|
| `cur_employee_population_daily` | pegawai × tanggal |
| `cur_event_attendance` | satu event sumber |
| `cur_attendance_event_daily` | pegawai × tanggal, seluruh shift |
| `cur_leave_daily` | pengajuan × pegawai × tanggal izin |
| `cur_attendance_daily` | pegawai × tanggal, populasi/event/izin terpadu |

Tidak ada pengisian ulang atau perubahan source/raw. Database pilot
`staging_bkd_test_20261027` juga tidak diubah.

## Temuan sebelum migrasi

Curated lama masih memisahkan regular/non-regular dan memakai konsep workday.
Estimasi statistik PostgreSQL: 13.919.866 event, 6.570.909 ringkasan nonregular,
362.612 ringkasan regular, 584.121 baris izin dan 921.430 hasil harian regular.
Tabel workday dan kalender kosong. Angka tersebut adalah estimasi statistik,
bukan COUNT aktual atau angka KPI.

Tidak ada koneksi lain ke database saat pemeriksaan/migrasi. Tidak ditemukan
view database yang merujuk curated atau foreign key lintas tabel. Pipeline Hop
curated yang diperiksa masih scaffold `SELECT 1 ... WHERE FALSE`; data existing
berasal dari backfill SQL. Skrip lama belum cocok dengan kontrak baru.

## Penanganan data dan metadata lama

Schema lama diubah nama menjadi `curated_legacy_20261028` secara transaksional.
Record tetap utuh, tidak disalin dan tidak dihapus. Dengan demikian curated aktif
bersih tanpa kehilangan baseline. Schema arsip bukan sumber KPI saat ini.

Metadata 12 batch disalin ke `etl_control.backfill_batch_legacy_20261028`.
Enam batch LOADED/VALIDATED ditandai FAILED dengan catatan
`INVALIDATED_CURATED_V2_20261028`, karena hasilnya berada di arsip, bukan curated
aktif. Ini invalidasi hasil kontrak lama, bukan kegagalan migrasi. Enam batch
PLANNED tetap belum dijalankan. Jangan menjalankan ulang backfill lama terhadap
schema baru. `etl_control.curated_contract_revision` mencatat status
`PENDING_POLICY_AND_ETL`.

## Detail kontrak fisik

- PK menjamin grain; indeks tanggal/departemen mendukung agregasi dan reload.
- Pada tabel ringkasan, `has_masuk` dan `has_pulang` adalah generated columns
  dari hitungan event. Enam measure pada `cur_attendance_daily` juga generated;
  loader tidak boleh mengisi kolom generated secara eksplisit.
- Tabel event mempertahankan tanggal kalender dan tanggal pelaporan terpisah.
  Atribusi UNRESOLVED mensyaratkan tanggal pelaporan NULL; PROVISIONAL/RESOLVED
  memerlukan tanggal, pegawai, dan identitas kebijakan atribusi.
- `paired_checkin_id_sumber` tersedia sebagai jejak pasangan jika kebijakan
  lintas malam nantinya memakainya; belum ada algoritme pairing yang diterapkan.
- `is_date_final` default false. Nilai ini baru boleh diubah setelah atribusi,
  cakupan ekstraksi, dan kebijakan penutupan tanggal tervalidasi.
- Populasi membedakan AS_OF_DATE_SNAPSHOT dari EXTRACTION_SNAPSHOT. Status aktif
  tidak diketahui tidak berkontribusi ke measure; loader harus menandainya untuk
  review, bukan menyimpulkan pegawai nonaktif.
- Izin beririsan dengan flag event/tidak-event. Tidak ada constraint yang
  memaksa satu shift, urutan masuk/pulang global, atau partisi hadir/izin/absen.

## Validasi

Dry-run migrasi dan pengujian kontrak dilakukan dalam transaksi rollback,
kemudian migrasi committed dan kontrak diuji ulang dengan rollback fixture.
Hasil: dua shift menghasilkan satu ringkasan MIN/MAX; delapan kasus KPI
(tanpa event, masuk saja, pulang saja, dua shift, izin tanpa/dengan event,
nonaktif, status unknown) sesuai nilai yang diharapkan. Keunikan grain,
identitas aktif=masuk+tidak masuk dan aktif=pulang+tidak pulang, serta penolakan
tanggal pada event unresolved juga lolos.

Lima tabel aktif berisi nol baris setelah pengujian. OID dan ukuran fisik seluruh
11 tabel raw serta 7 tabel arsip sama sebelum/sesudah migrasi. Pemeriksaan ini
bukan rekonsiliasi ulang isi raw terhadap sumber; migrasi memang tidak melakukan
DML ke raw maupun database sumber.

Artefak:

- [SQL migrasi](../sql/staging/20261028_curated_population_v2.sql)
- [DDL sebelum migrasi](../tests/curated_v2_20261028/schema_before.sql)
- [Uji kontrak](../tests/curated_v2_20261028/contract.sql)
- [Hasil uji](../tests/curated_v2_20261028/contract_results.txt)
- [Verifikasi akhir](../tests/curated_v2_20261028/verification.txt)

## Pekerjaan berikutnya

Pipeline Hop raw ke curated kini telah dipasang; lihat [panduan ETL](../hop/README.md).
Sebelum pemuatan bisnis, sambungkan manifest ID berubah dari producer raw dan
pastikan kelengkapan snapshot pegawai. Basis populasi backfill serta atribusi
lintas malam masih memerlukan keputusan. STTM curated ke serving belum
diselaraskan. Tidak menjalankan backfill historis atau cutover dashboard.
