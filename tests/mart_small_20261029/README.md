# Uji kecil curated → fact → serving — 29 Oktober 2026

Uji melalui workflow Hop aktual, memakai dua database khusus:

| Peran | Container | Database |
|---|---|---|
| Referensi, hanya dibaca | epresensi-staging-postgres | staging_bkd_bulk_20261028 |
| Sumber uji | epresensi-staging-postgres | staging_bkd_mart_small_20261029 |
| Target uji | epresensi-mart-postgres | mart_bkd_small_20261029 |

Sampel awal: satu pegawai per skenario 0–11 dari `test_bulk.cohort`, dipilih
berdasarkan urutan n terkecil. Data mengikuti kondisi **setelah koreksi bulk**:
skenario 4 approval sudah dicabut, skenario 7 sudah menjadi izin pulang.
Hanya snapshot populasi dan curated harian disalin, termasuk generated measures.
Kolom input non-generated dimuat lalu seluruh hasil disamakan dengan sumber.
Tidak ada penyalinan nama/NIP/kontak; artefak berisi ID, waktu, flag dan measure.

Pipeline uji menyalin kode HPL/HWF yang sama dengan pipeline utama. Perbedaan hanya
nama koneksi dan path child pipeline. SQL terpasang berasal dari migration yang
sama. Metadata koneksi khusus ada di runtime Hop, bukan kredensial di artefak.
Tidak menjalankan ulang raw→curated atau mengubah sumber bulk. Koreksi dilakukan
pada curated uji untuk menguji kontrak downstream secara terkontrol.

## Ekspektasi awal

| Aktif | Masuk | Pulang | Tidak masuk | Tidak pulang | Izin |
|---:|---:|---:|---:|---:|---:|
| 12 | 5 | 5 | 5 | 3 | 6 |

Wajib masuk/pulang 9/7, bebas masuk/pulang 3/5, pemenuhan wajib masuk/pulang 4/4.
Oracle berasal dari skenario bulk terkoreksi dan perhitungan Python terpisah;
seluruh 12 measure, flag, timestamp dan kunci fact dibandingkan dengan curated.
Agregasi diperiksa per partisi dan rate diperiksa berdasarkan jumlah pembilang/
penyebut. Semua hasil tetap provisional; kelengkapan/finalisasi tidak diasumsikan.

## Skenario

- Bootstrap 12 baris melalui outbox dan workflow Hop.
- Antrean kosong dan timestamp-only no-op: versi baris fact/agregasi tidak berubah.
- Checkout incremental pada pegawai yang sebelumnya hanya masuk.
- Mutasi: snapshot tanggal 29 Oktober di B, histori 28 Oktober tetap di A.
- Event terlambat pada 28 Oktober memakai snapshot A, bukan snapshot terbaru B.
- Koreksi arah pengecualian izin.
- Kegagalan refresh agregasi setelah perubahan fact: seluruh transaksi target
  rollback, source tetap pending; retry melalui workflow harus berhasil.
- Rollback perubahan curated membatalkan outbox dan kenaikan sequence juga.
- Commit mart tanpa ack (menjalankan child apply saja), kemudian workflow retry:
  tidak menggandakan receipt atau menulis ulang fact/agregasi.
- Dua versi curated diantrekan sebelum delivery; batch pertama tetap memuat
  versi pertama walaupun source sudah berubah lagi.
- Fixture sintetis tambahan: departemen UNKNOWN, pegawai nonaktif ber-event,
  denominator nol, koreksi key sintetis, serta delete sampai partisi kosong.
- Penolakan payload replay berubah, batch tidak berurutan, receipt belum committed,
  dan percobaan mengubah payload outbox yang sudah committed.

Mutasi departemen tidak mengubah snapshot lama. Fixture koreksi key terpisah dari
pegawai sampel, sehingga tidak dipakai untuk memodelkan mutasi biasa. Uji historis
ini membuktikan penerusan kontrak snapshot curated ke fact; producer snapshot
raw→curated tidak dijalankan ulang pada tahap ini. Tanggal masa depan pada fixture
sintetis hanya untuk pemeriksaan partisi/denominator di database uji.

## Artefak dan kelanjutan

- `sample_manifest.json`: snapshot sampel awal dan skenario.
- `baseline.json`: hasil awal beserta seluruh KPI/rate.
- `department_history.json`: bukti departemen per tanggal.
- `*_hop.json`, `*.log`: kode keluar, durasi dan log eksekusi Hop.
- `rollback_evidence.json`: bukti target tetap utuh saat kegagalan disisipkan.
- `protected_before.json`, `protected_after.json`: bukti referensi bulk dan
  tabel aktif tetap sama pada pemeriksaan sebelum/sesudah.
- `summary.json`, `final.json`: status akhir jika seluruh rangkaian selesai lulus.

`run.py setup` menolak database existing; tidak ada reset/drop otomatis.
`run.py baseline` hanya untuk fase awal, bukan setelah skenario koreksi selesai.
`scenarios.py` mencatat mutasi dalam transaksi beserta checkpoint fase sehingga
fase yang lulus dapat dilewati saat melanjutkan. Setelah kegagalan tak terduga,
inspeksi log/status sebelum melanjutkan. Database dan fixture dipertahankan untuk
review; jangan menganggap hasil uji sebagai data absensi bisnis nyata.

Verifikasi read-only setelah pengujian:

```bash
python3 tests/mart_small_20261029/run.py verify
```

Verifikasi membaca tabel bisnis; ia hanya menyimpan laporan/checkpoint pada schema
test_small database uji dan file artefak. Uji kecil ini bukan benchmark volume
historis, pairing lintas malam, atau bukti kelengkapan snapshot produksi.

## Hasil pelaksanaan — LULUS

Seluruh rangkaian selesai. **16 eksekusi Hop: 15 sukses dan 1 gagal yang sengaja
disisipkan untuk uji rollback**; retry setelah kegagalan tersebut sukses.
Tidak diperlukan perubahan kode pipeline untuk meluluskan skenario ini.

- Load awal: tepat 12 fact dari 12 curated, dengan KPI awal sesuai tabel ekspektasi.
- Histori departemen tetap A pada 28 Oktober, B pada snapshot 29 Oktober.
  Event terlambat 28 Oktober tetap di A. Pemeriksaan akhir juga mencocokkan
  departemen/status daily dengan snapshot populasi untuk setiap key.
- No-op dan replay mempertahankan versi baris fact/agregasi. Baris fact yang
  tidak terdampak pada skenario koreksi tidak ditulis ulang.
- Kegagalan refresh tidak meninggalkan perubahan fact/agregasi/checkpoint;
  outbox tetap pending. Retry dan commit-before-ack recovery lulus.
- Payload lama tetap immutable meskipun curated sudah mempunyai versi baru.
- UNKNOWN, nonaktif ber-event, NULL rate, koreksi key sintetis, serta pembersihan
  partisi kosong setelah delete lulus.
- Pemeriksaan akhir: 14 fact (12 baris awal + 1 hari baru pegawai yang mutasi +
  1 baris audit pegawai nonaktif sintetis). Angka ini adalah baris pegawai-hari,
  bukan 14 pegawai aktif. Fixture UNKNOWN yang dipindah/dihapus sudah hilang.
- Total akhir lintas tanggal diperiksa independen: aktif 13 pegawai-hari,
  masuk 7, pulang 6, tidak masuk 5, tidak pulang 3, izin 6; wajib masuk/pulang
  11/7, bebas 2/6, pemenuhan wajib 6/4.
- Hash seluruh curated harian bulk serta kondisi tabel aktif sebelum/sesudah
  cocok. `mart_bkd` aktif tetap kosong dan capture staging aktif belum dinyalakan.

Ringkasan mesin: [summary.json](summary.json). Detail hasil awal:
[baseline.json](baseline.json). Pemeriksaan snapshot terakhir:
[manual_verify.json](manual_verify.json). Bukti rollback:
[rollback_evidence.json](rollback_evidence.json).
