# Inventaris ETL Lama

Tanggal inventaris: 12 Oktober 2026 (WIB)  
Sumber utama: snapshot Git sebelum migrasi ke Apache Hop, commit induk
`9c7fa59^` (commit penghapusan: `9c7fa59`, 8 Oktober 2026). Fakta pipeline
Hop yang juga telah dihapus dicatat dari `4454f04` (9 Oktober 2026).

> Status artefak: **historis/terhapus dari working tree**, tetapi masih dapat
> dibaca melalui Git. Jangan menjalankan modul Python lama terhadap basis data
> produksi tanpa review koneksi, schema, dan migrasi data.

## 1. Pipeline lama

| Pipeline / entry point | Modul historis | Cakupan |
|---|---|---|
| Master orchestration | `etl/pipeline/master.py` | Dimensi, kalender, incremental fact, perizinan, dan penggantian fact harian dalam satu transaksi. |
| Initial load | `etl/pipeline/initial_load.py`, `initial_load_preflight.py` | Pemeriksaan prasyarat, pemuatan awal, reset checkpoint. |
| Incremental | `etl/pipeline/incremental.py` | Delta attendance/perizinan berdasarkan watermark dan overlap. |
| Dimensi | `calendar.py`, `departemen.py`, `pegawai.py`, `jadwal_kerja.py`, `jenis_izin.py` | Extract-transform-load dimensi dan kalender. |
| Fact kehadiran | `etl/pipeline/fact_kehadiran.py` | Rekonstruksi daily attendance; transform dipisah ke `etl/transform/fact_kehadiran/`. |
| Fact perizinan | `etl/pipeline/fact_perizinan/pipeline.py` | Extract, normalisasi, approval, coverage, validasi, dan load izin. |
| Dummy/source bootstrap | `etl/dummy/{database,generate,seed,jatim,append_september}.py` | Pembuatan dan pengisian data uji. |

Manifest legacy Python berisi 68 file di `etl/`: `config` (2), `connectors`
(3), `control` (3), `dummy` (7), `extract` (10), `load` (8), `pipeline`
(12), dan `transform` (23). Selain itu ada tiga pemeriksaan koneksi
(`etl/test_connections.py`, `test_read_oltp.py`, `test_write_olap.py`) dan
test suite root/`tests/` untuk initial load, incremental, dummy, master, dan
fact perizinan.

### Penjadwalan dan pengganti

Unit lama yang dihapus: `deploy/systemd/olap-master.{service,timer}` dan
`deploy/systemd/olap-incremental.{service,timer}`. Masing-masing memakai
`StandardError=journal`; master menggunakan `Restart=on-failure`.

Migrasi memperkenalkan Apache Hop. Artefak fact Hop yang kemudian dihapus:
`hop/presensi/pipelines/fact_ingest_events.hpl`,
`hop/presensi/pipelines/fact_kehadiran.hpl`,
`hop/presensi/workflows/fact_ingest_events_all.hwf`,
`hop/presensi/workflows/fact_kehadiran_all.hwf`, dan
`scripts/run_hop_fact.py`. SQL pendukung fact tetap ada di `sql/hop/`.

## 2. Script pendukung lama

| Kelompok | Artefak |
|---|---|
| Koneksi & konfigurasi | `etl/connectors/{oltp,olap}.py`, `etl/config/fact_kehadiran.py` |
| Kontrol operasi | `etl/control/{checkpoint,locking,run_log}.py` |
| Extract | `etl/extract/{calendar,departemen,fact_kehadiran,incremental,jadwal_kerja,jenis_izin,pegawai}.py` dan `extract/fact_perizinan/` |
| Load | `etl/load/{calendar,departemen,fact_kehadiran,jadwal_kerja,jenis_izin,pegawai}.py` dan `load/fact_perizinan/` |
| Transform | `etl/transform/{calendar,departemen,incremental,cross_fact_validation}.py`, `transform/fact_kehadiran/`, dan `transform/fact_perizinan/` |
| Operasional root | `test_*_fact_perizinan.py`, `tests/test_{initial_load,incremental,master,seed_source_schema,...}.py`, `sql/validate_september_incremental.sql` |

Untuk pemulihan, gunakan `git show 9c7fa59^:<path>` untuk membaca satu
artefak. Hindari `git checkout` terhadap file lama karena dapat menimpa
perubahan kerja saat ini.

## 3. Schema dan kontrak data

### OLTP dummy/source

Definisi lengkap ada di `etl/dummy/source.sql`. Tabelnya:

`m_departemen`, `m_previleges`, `m_pegawai`, `m_user`, `m_shift`, `m_jadwal`,
`m_tipe_ijin`, `m_jenis_ijin`, `m_hari_libur`, `t_libur_shift`, `t_perizinan`,
dan `t_checkinout`.

Relasi penting: pegawai → departemen/privilege; user → pegawai; shift →
departemen; jadwal → shift; perizinan → user/departemen/pegawai/tipe/jenis
izin; check-in/out → pegawai/departemen. Ada indeks
`dummy_attendance_date` pada `t_checkinout(created_at)`.

### OLAP target dan kontrol

DDL target OLAP tidak tersimpan sebagai satu file legacy. Kontrak yang
divalidasi oleh `etl/pipeline/initial_load_preflight.py` dan dipakai modul
kontrol adalah:

| Objek | Peran |
|---|---|
| `etl_control.pipeline_runs` | Riwayat run: `run_id`, `pipeline_name`, `status`, waktu selesai, jumlah row extract/insert/update, dan `error_message`. |
| `etl_control.pipeline_state` | Watermark/checkpoint per pipeline. |
| Dimensi | `dim_departemen`, `dim_pegawai`, `dim_jadwal_kerja`, `dim_jenis_izin`, `dim_calendar`. |
| Fakta | `fact_kehadiran`, `fact_perizinan`. |

Schema dashboard historis juga menciptakan `analytics`,
`mart_dirty_dates`, `mart_refresh_state`, dan tiga mart harian attendance di
`sql/dashboard/marts.sql`; view berada di `sql/dashboard/views.sql`.

## 4. Error log dan temuan kegagalan

Tidak ada file raw error log yang terlacak: `.gitignore` lama mengecualikan
`*.log`. Detail runtime dimaksudkan tersimpan di systemd journal dan tabel
`etl_control.pipeline_runs`; stage progress ditulis ke stderr/journal.

Satu bukti kegagalan yang terdokumentasi ada di
`docs/dashboard-readiness-audit.md` (snapshot sebelum 8 Oktober 2026):

| Metrik / kejadian | Nilai |
|---|---|
| Incremental sukses | 929 |
| Incremental gagal | 1 |
| Initial load sukses | 1 |
| Run gagal | 864 |
| Pesan error | `prepare_permissions() got an unexpected keyword argument 'pegawai_reference'` |
| Kondisi setelahnya | Run berikutnya sukses dengan 0 perubahan; audit menyatakan ini belum membuktikan jalur perubahan izin telah diuji ulang di scheduler produksi. |

Penanganan error pada `etl/pipeline/master.py`: data transaction di-rollback,
kemudian status `FAILED` dan pesan error dicoba ditulis ke `pipeline_runs`.
Jika basis data terputus, pencatatan akhir itu sendiri dapat gagal; error asli
tetap ada di stderr/journal. Run `RUNNING` yang ditinggalkan ditandai `FAILED`
oleh master/incremental penerus setelah memperoleh advisory lock.

### Kueri pengambilan log yang direkomendasikan

```sql
SELECT run_id, pipeline_name, status, started_at, finished_at,
       rows_extracted, rows_inserted, rows_updated, error_message
FROM etl_control.pipeline_runs
WHERE pipeline_name IN ('master_orchestration', 'incremental_facts')
ORDER BY run_id DESC;
```

Untuk host systemd lama, ambil journal unit historis (bila retensi masih ada):
`journalctl --user -u olap-master.service -u olap-incremental.service`.

## 5. Bukti dan tindak lanjut

- Migrasi/penghapusan utama: `9c7fa59` — *add: hop pipepline del: old files*.
- Penghapusan pipeline fact Hop: `4454f04` — *delete: fact pipeline*.
- Tidak ada raw log di Git; pengambilan aktual memerlukan akses ke database
  OLAP lama dan/atau journal host lama.
- Dua dokumen baru yang belum terlacak di working tree tidak diubah oleh
  inventaris ini.
