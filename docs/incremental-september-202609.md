# Fixture incremental September 2026

Fixture 1–30 September menggunakan **82.000 pegawai, 25 departemen, user,
jenis izin, dan jadwal yang sudah ada di OLTP**. Tidak membuat identitas baru.
Kalender mengikuti tabel sumber: 22 hari kerja Senin–Jumat, 8 hari nonkerja,
tanpa hari libur tambahan pada September. Ini adalah skenario sintetis,
termasuk transaksi 30 September meskipun penyiapan dilakukan 29 September.

Kategori saling eksklusif, dengan denominator **1.804.000 pegawai-hari kerja**.
Kuota tepat setiap hari pada seluruh pegawai; distribusi per departemen dapat
berbeda. Pegawai diacak deterministik setiap hari dengan seed `202609`.

| Kategori | Persentase | Pegawai-hari |
|---|---:|---:|
| WFO tepat waktu, pulang normal | 38% | 685.520 |
| WFH tepat waktu, pulang normal | 14% | 252.560 |
| WFO terlambat, pulang normal | 12% | 216.480 |
| WFH terlambat, pulang normal | 5% | 90.200 |
| WFO tepat waktu, pulang awal | 6% | 108.240 |
| WFO terlambat sekaligus pulang awal | 3% | 54.120 |
| WFO hanya masuk, tanpa absen pulang | 4% | 72.160 |
| Cuti disetujui | 5% | 90.200 |
| Sakit disetujui | 4% | 72.160 |
| Izin pribadi disetujui | 3% | 54.120 |
| Izin pribadi pending, tanpa absensi | 2% | 36.080 |
| Izin pribadi ditolak, tanpa absensi | 1% | 18.040 |
| Tidak absen dan tidak mengajukan izin | 3% | 54.120 |
| **Total** | **100%** | **1.804.000** |

Waktu mengikuti jam lokal sumber. Tepat waktu 0–25 menit sebelum jadwal,
terlambat 5–90 menit, pulang awal 5–75 menit, pulang normal 0–40 menit setelah
jadwal. Kategori tanpa pulang hanya memiliki satu event dan masuk tepat waktu.
Semua izin satu hari; tanggal pengajuan pada hari izin pukul 05.00, keputusan
pukul 05.30 jika ada. Timestamp seluruh izin baru melewati watermark Agustus.
Tidak ada event atau izin pada akhir pekan.

## Jumlah transaksi sumber

| Tabel | Tambahan September | Total Agustus + September |
|---|---:|---:|
| `t_checkinout` | 2.886.400 | 5.379.200 |
| `t_perizinan` | 270.600 | 426.400 |

Izin September: APPROVED 216.480, PENDING 36.080, REJECTED 18.040.
Hari tanpa absensi tidak diwakili event palsu; absennya event adalah kasus uji.

## Artifact dan pengamanan

- Generator/appender: `etl/dummy/append_september.py`.
- Artifact: `data/incremental-september-202609.jsonl.gz`.
- Manifest kategori total dan per tanggal: `data/incremental-september-202609-manifest.json`.
- Bukti commit, rentang awal ID, fingerprint baseline, dan checkpoint:
  `data/incremental-september-202609-applied.json`.
- Pemeriksaan sumber setelah commit: `data/incremental-september-202609-verified.json`.

Appended records menggunakan default sequence sumber. Sequence izin lama
tertinggal dari MAX(id); appender menyelaraskan sequence maju di dalam transaksi.
ID tidak di-reset ke awal dan tidak diwajibkan berurutan tanpa celah.
Penulisan hanya ke dua tabel transaksi, dalam satu commit; impor ulang ditolak
jika September sudah berisi event atau izin. Fingerprint seluruh baris master
yang digunakan serta transaksi lama dibandingkan sebelum/sesudah penambahan.

Tujuh tanggal kalender OLAP (24–30 September) dilengkapi sebagai prasyarat.
Fakta kehadiran/izin OLAP dan checkpoint tidak dimajukan saat penyiapan fixture.
ETL belum dijalankan terhadap tambahan September ini.

## Menjalankan test incremental

Baseline sebelum fixture: fakta kehadiran OLAP 2.542.000, fakta izin 155.800;
checkpoint absensi ID 2.492.800 dan izin `2026-08-29 10:00:00`.

```bash
# Preview; seluruh delta besar tetap ditransformasi/validasi, tanpa commit.
.venv/bin/python -m etl.pipeline.incremental

# Jalankan ketika siap menguji pemuatan September.
.venv/bin/python -m etl.pipeline.incremental --apply

# Ulangi untuk memeriksa tidak ada duplikasi; overlap izin tetap dibaca.
.venv/bin/python -m etl.pipeline.incremental --apply
```

Setelah incremental sukses, **tambahan fakta kehadiran September 1.695.760**:
HADIR 1.479.280 dan IZIN 216.480. Total fakta Agustus + September menjadi
4.237.760; fakta izin 426.400. Angka processed/updated di run log dapat berbeda
karena overlap izin Agustus dan pemrosesan employee-day berulang antar chunk.

Izin pending/ditolak tetap menjadi fakta izin. Karena belum ada fakta September
dan keduanya tidak menambah affected keys, incremental tidak membuat fakta
kehadiran untuk kedua kategori itu. Demikian pula kategori tidak absen tanpa
pengajuan dan hari nonkerja. Ini perilaku pipeline yang ada, bukan data hilang
dari fixture. Untuk memeriksa populasi lengkap, **setelah test incremental**:

```bash
.venv/bin/python -m etl.pipeline.master \
  --start-date 2026-09-01 --end-date 2026-09-30 --apply
```

Setelah populasi master: September 2.460.000 fakta, terdiri dari HADIR 1.479.280,
IZIN 216.480, TIDAK_ABSEN 108.240 (termasuk pending/ditolak), dan NON_WORKING_DAY
656.000. Total Agustus + September 5.002.000 fakta.

Flag lintas kategori: WFH 342.760; terlambat 360.800; pulang awal 162.360;
hadir tidak lengkap 72.160. Flag ini tumpang tindih dan tidak boleh dijumlahkan
sebagai kategori eksklusif.

Scheduler incremental tetap aktif: pada saat penyiapan, run berikutnya
**30 September 2026 pukul 01.00 WIB**. Run otomatis juga dapat memproses fixture
dan mengubah baseline sebelum test manual; periksa `pipeline_runs` terlebih dulu.

## Verifikasi

Query pembanding tersedia di `sql/validate_september_incremental.sql`.
Pengujian otomatis fixture meliputi seluruh kategori melalui transformasi asli,
ID pegawai/user tidak berurutan, rollback artifact tidak lengkap, preservation
master/transaksi lama, penolakan impor duplikat, incremental nyata, dan rerun:

```bash
RUN_POSTGRES_TESTS=1 .venv/bin/python -m unittest discover \
  -s tests -p test_append_september.py -v
```

Test PostgreSQL menggunakan skema terpisah yang selalu di-rollback. Seluruh
suite setelah penambahan fixture: **48 test lulus**.
