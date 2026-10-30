# Bulk curated → fact → agregasi — 29 Oktober 2026

> Superseded: this bulk test dataset and its tagged source fixtures were removed
> on 30 October 2026 at the user’s request. The current dataset and verification
> are documented in [the source-to-dashboard rerun](../source_to_dashboard_20261030/README.md).
> Historical scripts and reports below are audit evidence, not current database state.

**LULUS.** Menggunakan seluruh hasil curated bulk existing, tanpa membuat skenario
baru atau mengulang raw→curated. Kondisi yang dimuat adalah hasil setelah koreksi
izin: approval skenario 4 telah dicabut, skenario 7 menjadi izin pulang.

## Lingkungan dan data

| Peran | Container | Database |
|---|---|---|
| Referensi read-only | epresensi-staging-postgres | staging_bkd_bulk_20261028 |
| Salinan sumber untuk outbox | epresensi-staging-postgres | staging_bkd_mart_bulk_20261029 |
| Target fact/serving | epresensi-mart-postgres | mart_bkd_bulk_20261029 |

Dua tabel curated disalin seluruhnya: cur_employee_population_daily dan
cur_attendance_daily. Semua 2.400 baris masing-masing tabel dibandingkan terhadap
referensi, termasuk generated measures. Tidak ada perubahan nilai snapshot,
departemen, event, izin, atau tanggal. Data tetap mencakup satu tanggal,
28 Oktober 2026, 12 skenario × 200 pegawai dan 757 departemen. Sebanyak 690
departemen mempunyai lebih dari satu pegawai (maksimum 4 pada dataset ini).

Kode SQL dan HPL/HWF sama dengan pipeline utama. File uji hanya mengganti nama
koneksi dan path child pipeline. Metadata koneksi tersimpan di runtime Hop tanpa
mengekspor kredensial ke artefak lokal. Harness memakai helper verifikasi dari
`tests/mart_small_20261029/run.py` dengan database dan direktori output khusus.

## Pelaksanaan dan hasil

1. Persiapan salinan sumber, schema target dan metadata koneksi khusus.
2. Bootstrap satu tanggal menghasilkan satu batch immutable berisi 2.400 key.
3. Workflow Hop menjalankan apply fact/agregasi atomik, lalu memverifikasi receipt
   committed melalui koneksi baru dan melakukan acknowledgement di staging.
4. Semua 2.400 fact dibandingkan dengan curated, termasuk 12 measure, flags,
   departemen dan timestamp. Departemen/status juga cocok dengan snapshot harian.
5. Seluruh 757 partisi agregasi dibandingkan dengan GROUP BY curated menggunakan
   ID departemen sumber, bukan hanya mengelompokkan kembali surrogate key fact.
6. Lookup dimensi pegawai/departemen diperiksa terhadap identitas sumber dan
   interval efektif. Empat persentase diperiksa pada setiap departemen serta ALL.
7. Workflow dijalankan kembali dengan antrean kosong. Tidak ada versi baris fact
   maupun agregasi yang berubah; tidak ada batch atau receipt tambahan.

| Objek | Hasil |
|---|---:|
| Fact pegawai-harian | 2.400 |
| Agregasi tanggal-departemen | 757 |
| Batch APPLIED / receipt | 1 / 1 |
| Batch pending | 0 |
| Selisih measure/partisi | 0 |

| KPI | Nilai |
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

Seluruh hasil tetap provisional. Kelengkapan populasi produksi dan finalisasi
tanggal tidak diasumsikan dari keberhasilan load uji.

## Pengukuran awal

- Satu pemanggilan Hop untuk load: 11,180 detik wall-clock termasuk startup JVM;
  log mencatat durasi workflow internal 2,674 detik.
- Pemanggilan antrean kosong: 9,587 detik termasuk startup JVM.
- Satu pengukuran EXPLAIN ANALYZE read-only: query view KPI instansi 3,030 ms;
  query perbandingan seluruh departemen 3,606 ms.

Angka ini berasal dari satu tanggal dan satu pengukuran lokal setelah load,
bukan SLA dashboard, benchmark histori besar atau akses pengguna bersamaan.
Tidak mengulang simulasi koreksi/failure pada volume ini: cakupan tersebut telah
diuji pada uji kecil. Bulk ini memvalidasi pemuatan dataset existing hingga serving.

## Artefak dan perlindungan data

- [Ringkasan](summary.json)
- [Hasil load dan KPI](bulk_load.json)
- [Rekonsiliasi seluruh departemen](bulk_load_departments.json)
- [Log workflow](bulk_load.log)
- [Waktu pemanggilan Hop](bulk_load_hop.json)
- [Rencana dan waktu query](query_plans.json)
- [Kondisi sebelum](protected_before.json) / [sesudah](protected_after.json)

Hash seluruh curated harian referensi tetap sama. mart_bkd aktif tetap memiliki
nol fact/agregasi/batch/receipt. staging_bkd aktif tetap nol daily/outbox,
bootstrap false dan sequence 0. Database uji kecil sebelumnya tidak digunakan
sebagai target pengujian ini. Tidak ada cutover dashboard atau scheduler baru.

Database uji dipertahankan untuk inspeksi. `run.py setup` menolak target existing;
jangan membuat ulang atau menjalankan setup setelah hasil tersedia. `run.py load`
menjalankan workflow, sehingga bukan perintah inspeksi. Untuk memeriksa ulang:

```bash
python3 tests/mart_bulk_20261029/run.py verify
```

Verifikasi hanya membaca fact/curated/serving; hasil laporan dicatat pada file
lokal dan schema test_small di sumber uji. Tidak memuat ulang data bisnis.
