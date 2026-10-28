# STTM Source ke Curated — Kehadiran KPI

> **Pembaruan ETL 28 Oktober 2026:** pipeline Hop dan fungsi incremental raw ke
> curated sudah dipasang dan diuji. Data bisnis belum dimuat; producer raw masih
> perlu mengirim manifest ID berubah. Lintas malam tetap provisional/unresolved.
> Petunjuk dan batas implementasi ada di [panduan ETL](../hop/README.md).

> **Status fisik 28 Oktober 2026:** schema curated baru sudah dibuat di
> `staging_bkd` dan masih kosong; data lama berada di `curated_legacy_20261028`.
> ETL sudah dipasang; pengisian ulang data bisnis belum dijalankan. Lihat
> [hasil pemeriksaan dan migrasi](penyesuaian-curated-staging-20261028.md).

Status: **revisi rancangan 28 Oktober 2026**. Menggantikan kontrak workday berbasis
keyword regular/reguler. Acuan: [data lineage KPI](data-lineage-dashboard-kpi.md).
Pipeline sudah dipasang; atribusi tanggal lintas malam belum final.

Revisi izin: pengecualian memakai `t_perizinan.tipe_ijin` sesuai view sumber
`v_perizinan`: 1 penuh, 2 tidak absen masuk, 3 tidak absen pulang. Flag
`m_jenis_ijin.setengah_hari` dipertahankan untuk audit, bukan penentu cakupan.

## 1. Prinsip dan objek

Database aplikasi tidak diubah. Raw menyimpan nilai asli beserta metadata
ekstraksi. Curated melakukan lookup, ekspansi izin, dan agregasi; tidak mencari
shift reguler, mewariskan jadwal induk, atau menyimpulkan kewajiban pegawai.

| Objek | Grain / kunci |
|---|---|
| `cur_employee_population_daily` | pegawai × tanggal; `(pegawai_id, tanggal)` |
| `cur_event_attendance` | satu event; `checkinout_id_sumber` |
| `cur_attendance_event_daily` | pegawai × tanggal; `(pegawai_id, tanggal)` |
| `cur_leave_daily` | pegawai × tanggal izin × pengajuan |
| `cur_attendance_daily` | pegawai × tanggal; `(pegawai_id, tanggal)` |

## 2. Populasi harian

`cur_employee_population_daily` menggantikan `cur_employee_workday`.
Snapshot boleh mencakup seluruh pegawai dengan flag aktif untuk mempertahankan
konteks event pegawai di luar populasi KPI.

| Kolom | Sumber / aturan |
|---|---|
| `pegawai_id` | `m_pegawai.id` |
| `tanggal` | Tanggal pelaporan yang diproses. |
| `departemen_id` | Usulan: snapshot `m_pegawai.departemen`; satu departemen KPI per pegawai-hari. |
| `status_sumber`, `is_employee_active` | Nilai asli `m_pegawai.status` dan mapping aktif yang diverifikasi terhadap aplikasi. |
| `population_basis` | Snapshot tanggal terkait atau master saat ekstraksi; bedakan eksplisit. |
| `source_snapshot_at`, `source_updated_at` | Waktu snapshot dan pembaruan sumber bila tersedia. |

Tidak ada syarat `has_regular_schedule`, `is_expected_workday`, weekend, atau
libur untuk populasi aktif. Izin tetap masuk populasi aktif; denominator kewajiban
masuk/pulang mengecualikan sisi yang dibebaskan izin valid. Snapshot sekarang
bukan bukti status/departemen historis. Perubahan master tidak boleh diam-diam
menimpa hasil tanggal tertutup; koreksi historis memerlukan jejak revisi.

## 3. Event presensi

| Kolom `cur_event_attendance` | Sumber / aturan |
|---|---|
| `checkinout_id_sumber`, `pegawai_id` | `t_checkinout.id`, `pegawai_id` |
| `tanggal_event`, `waktu_event` | `created_at` dalam konteks Asia/Jakarta; periksa tipe timestamp agar tidak menggeser zona dua kali. |
| `checktype`, `event_type` | Nilai asli; 1 = MASUK, 2 = PULANG, selain itu LAIN. |
| `departemen_id_event` | Departemen transaksi untuk audit, bukan pengali grain. |
| `jadwal_id_sumber`, `work_code_sumber` | Nilai transaksi asli. |
| `jam_masuk_sumber`, `jam_keluar_sumber` | Jam rencana pada transaksi, bukan timestamp aktual. |
| `is_manual`, `is_wfh_sumber` | Nilai asli transaksi. |
| `shift_id_sumber`, `nama_shift_snapshot` | LEFT JOIN jadwal ke shift tanpa filter nama/status shift saat ini. |
| `tanggal` | Tanggal pelaporan menurut kebijakan atribusi; nullable bila belum dapat ditentukan. |
| `date_assignment_status`, `date_assignment_reason` | Status/bukti atribusi, termasuk unresolved. |
| `perlu_review`, `alasan_review` | Referensi hilang, konflik identitas/tanggal, inkonsistensi sumber. |
| `event_updated_at`, `source_snapshot_at` | Timestamp sumber/snapshot. |

Semua event dipertahankan. Event manual atau lookup jadwal gagal bukan otomatis
dibuang dari KPI. Identitas dan tanggal pelaporan harus jelas untuk agregasi.

## 4. Ringkasan seluruh shift

`cur_attendance_event_daily` mengambil checktype 1/2 tanpa klasifikasi
regular/non-regular. GROUP BY hanya pegawai dan tanggal pelaporan, bukan jadwal,
shift, atau departemen transaksi.

| Kolom | Aturan |
|---|---|
| `pegawai_id`, `tanggal` | Kunci unik. |
| `has_masuk`, `has_pulang` | Ada minimal satu event tipe terkait. |
| `checkin_event_count`, `checkout_event_count` | Jumlah event asli per tipe. |
| `first_checkin_at` | MIN timestamp aktual hanya untuk checktype 1. |
| `last_checkout_at` | MAX timestamp aktual hanya untuk checktype 2. |
| `has_manual_event` | Ada event manual. |
| `schedule_count`, `shift_count` | Jumlah ID berbeda yang diketahui; audit, bukan pengali KPI. |
| `perlu_review`, `alasan_review` | Konflik relevan tanpa menghilangkan bukti event. |

Pertahankan keterlacakan ke seluruh ID event. Banyak shift maupun event berulang
tetap satu flag masuk/pulang per pegawai-hari. MIN/MAX bukan bukti satu sesi,
durasi kerja sah, atau kewajiban shift tertentu.

Tanggal same-day memakai tanggal lokal event. Arah lintas malam adalah hari
check-in untuk checkout yang terbukti terkait, tetapi perilaku aplikasi lama,
batas durasi, dan algoritme pasangan belum dikonfirmasi. ID jadwal bisa berbeda;
jangan mewajibkan ID sama atau menggeser semua checkout ke D-1. Event ambigu
memerlukan penyelesaian sebelum tanggal terdampak final dan tidak boleh dihitung
dua kali. Simpan tanggal kalender event terpisah dari tanggal pelaporan.

## 5. Izin harian

| Kolom `cur_leave_daily` | Sumber / aturan |
|---|---|
| `perizinan_id_sumber` | `t_perizinan.id` |
| `pegawai_id` | `t_perizinan.pegawai_id`; validasi silang `user_id → m_user.pegawai_id`. |
| `tanggal_izin` | Ekspansi inklusif `tgl_ijin` sampai `COALESCE(tgl_ijin_sampai,tgl_ijin)`; rentang terbalik masuk review. |
| `departemen_id_izin` | Departemen transaksi untuk audit. |
| `jenis_izin_id_sumber`, `nama_jenis_izin` | Lookup `jenis_ijin → m_jenis_ijin`, serta `m_tipe_ijin`. |
| `approval`, `approval_at` | Nilai sumber. |
| `tipe_ijin_sumber` | Salin `t_perizinan.tipe_ijin`: 1 penuh, 2 bebas masuk, 3 bebas pulang. |
| `tipe_izin_id_sumber`, `nama_tipe_izin` | Kategori `m_tipe_ijin` melalui master jenis izin; berbeda dari tipe transaksi. |
| `setengah_hari_jenis_sumber` | Salin flag master untuk audit. Ketidaksamaan dengan tipe transaksi tidak mengganti tipe transaksi. |
| `is_full_day_leave`, `is_partial_day_leave` | Tipe transaksi 1 = penuh; 2/3 = parsial; kode NULL/tidak dikenal menghasilkan NULL dan review. |
| `is_valid_leave` | Approved, identitas/rentang/referensi valid, dan tipe transaksi 1/2/3. |
| `excuses_checkin`, `excuses_checkout` | Generated: izin valid tipe 1/2 membebaskan masuk; izin valid tipe 1/3 membebaskan pulang. |
| `perlu_review`, `alasan_review`, `source_updated_at`, `source_snapshot_at` | Audit. |

Ringkas izin menjadi satu pegawai × tanggal sebelum join ke populasi:
`has_valid_leave = ada minimal satu izin valid`. Banyak pengajuan dan izin
penuh/parsial tidak menggandakan total Pegawai Izin. Komposisi jenis overlap
memerlukan kategori MULTIPLE atau aturan prioritas jika harus eksklusif.
Izin tidak meniadakan bukti event. Izin valid mengurangi Tidak Absen pada sisi
yang dikecualikan. Gabungkan pengecualian dengan BOOL_OR per pegawai-tanggal:
izin penuh membebaskan kedua sisi; overlap tipe 2 dan 3 juga membebaskan kedua
sisi tanpa mengubah kedua pengajuannya menjadi satu pengajuan penuh.
Tidak ada kewajiban check-in kembali setelah izin masuk. Arah pengecualian tidak
perlu ditebak dari jam, nama shift, atau flag setengah hari pada master.

## 6. Record terpadu dan measure

Basis key `cur_attendance_daily` adalah union key populasi, event bertanggal
jelas, dan izin harian; LEFT JOIN ringkasan masing-masing yang sudah unik.
Bukti di luar populasi aktif tetap tersimpan tanpa masuk KPI utama.

| Kelompok | Kolom |
|---|---|
| Identitas/populasi | `pegawai_id`, `tanggal`, `departemen_id`, `is_employee_active`, `population_basis` |
| Event | `has_masuk`, `has_pulang`, jumlah event, `first_checkin_at`, `last_checkout_at` |
| Izin | `has_valid_leave`, `has_full_day_leave`, `has_partial_day_leave`, `has_excused_checkin`, `has_excused_checkout` |
| Audit | `source_snapshot_at`, `perlu_review`, `alasan_review`, metadata finalisasi tanggal |

```text
active_employee_days = is_employee_active ? 1 : 0
checkin_days         = (is_employee_active AND has_masuk) ? 1 : 0
no_checkin_days      = (is_employee_active AND NOT has_excused_checkin AND NOT has_masuk) ? 1 : 0
checkout_days        = (is_employee_active AND has_pulang) ? 1 : 0
no_checkout_days     = (is_employee_active AND NOT has_excused_checkout AND NOT has_pulang) ? 1 : 0
leave_days           = (is_employee_active AND has_valid_leave) ? 1 : 0

required_checkin_days  = (is_employee_active AND NOT has_excused_checkin) ? 1 : 0
required_checkout_days = (is_employee_active AND NOT has_excused_checkout) ? 1 : 0
excused_checkin_days   = (is_employee_active AND has_excused_checkin) ? 1 : 0
excused_checkout_days  = (is_employee_active AND has_excused_checkout) ? 1 : 0
required_checkin_present_days  = (is_employee_active AND NOT has_excused_checkin AND has_masuk) ? 1 : 0
required_checkout_present_days = (is_employee_active AND NOT has_excused_checkout AND has_pulang) ? 1 : 0
```

Join tanpa event/izin menghasilkan flag keberadaan false. Status aktif tidak
diketahui tidak dimasukkan ke populasi aktif dan harus ditandai untuk audit.
Tidak Absen Masuk/Pulang bukan TANPA_KETERANGAN atau penilaian disiplin.
Persentase bukti event memakai populasi aktif. Persentase pemenuhan kewajiban
masuk/pulang memakai `required_*_present_days / required_*_days`, bukan seluruh
event. Pegawai izin penuh yang tetap ber-event tidak menaikkan pembilang kewajiban.
Denominator nol menghasilkan NULL. Kewajiban ini adalah aturan dashboard setelah
pengecualian izin, bukan pembuktian roster/workday individual.

## 7. Refresh, validasi, dan migrasi

- Perubahan event memicu recompute tanggal lama dan baru yang terdampak atribusi,
  termasuk lintas malam; perubahan izin mencakup rentang lama dan baru.
- Perubahan populasi tanggal berjalan menghitung ulang pembilang/penyebut pada
  basis snapshot sama. Koreksi historis dicatat, bukan refresh master diam-diam.
- Pastikan ringkasan unik sebelum join. Departemen belum terpetakan tetap
  tertampung agar jumlah per departemen sama dengan ALL.
- Uji `aktif = wajib_masuk + bebas_masuk`, `aktif = wajib_pulang + bebas_pulang`,
  `wajib_masuk = pemenuhan_masuk + tidak_masuk`, dan padanannya untuk pulang.
  Rumus lama aktif = seluruh event + tidak absen tidak lagi berlaku saat ada izin.
- Perubahan `tipe_ijin` ikut fingerprint izin, sehingga perubahan arah izin saja
  memicu rekalkulasi. Pencabutan approval, penghapusan, koreksi rentang/identitas,
  serta overlap memeriksa kembali seluruh izin pada kunci lama dan baru.
- Uji tanpa keyword reguler, dua shift, event berulang, masuk/pulang saja, izin,
  nonaktif, referensi kosong, dan atribusi lintas malam.

| Nama/konsep lama | Pengganti |
|---|---|
| `cur_employee_workday` | `cur_employee_population_daily` |
| `cur_regular_event_daily`, `cur_nonregular_event_daily` | `cur_attendance_event_daily` seluruh shift |
| `cur_attendance_regular_daily` | `cur_attendance_daily` |
| `scheduled_regular_days` | Konsep baru `active_employee_days`, bukan sekadar rename. |
| `absent_days` / TANPA_KETERANGAN | Dua measure `no_checkin_days`, `no_checkout_days`. |

STTM curated ke serving sudah diselaraskan dengan kontrak fact harian seluruh shift
dan agregasi tanggal-departemen; lihat [kontrak downstream](sttm-curated-to-serving-kehadiran.md). Pipeline Hop raw ke curated
sudah dipasang sesuai [panduan ETL](../hop/README.md); belum ada pemuatan data
bisnis atau cutover dashboard.
