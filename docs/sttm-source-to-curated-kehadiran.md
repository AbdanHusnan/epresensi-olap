# STTM Source ke Curated — Kehadiran KPI

Status: **rancangan terkunci untuk review**. Dokumen ini merangkum keputusan
source-to-curated yang disepakati sebelum pemetaan curated ke mart.

## 1. Prinsip umum

1. Data sumber dari `dbabsen_restore` disalin apa adanya ke raw staging.
   Curated tidak membersihkan, mengganti, atau menghapus nilai bisnis sumber.
2. Curated membentuk grain aman, melakukan lookup snapshot historis,
   mengekspansi rentang izin, dan mengagregasikan event.
3. Perubahan master pegawai, departemen, shift, atau jadwal tidak boleh
   mengubah hasil historis. Validasi dan workday memakai snapshot tanggal terkait.
4. Event `t_checkinout` adalah bukti transaksi utama. Snapshot hanya dipakai
   untuk lookup dan validasi, bukan untuk menimpa nilai transaksi.
5. Semua objek menyimpan waktu snapshot/proses dan indikator review bila bukti
   atau relasi sumber tidak konsisten.

## 2. Objek curated dan grain

| Objek | Grain | Kunci bisnis |
|---|---|---|
| `cur_employee_workday` | pegawai × tanggal | `(pegawai_id, tanggal)` |
| `cur_event_attendance` | satu event presensi | `checkinout_id_sumber` |
| `cur_regular_event_daily` | pegawai × tanggal kerja | `(pegawai_id, tanggal_kerja)` |
| `cur_leave_daily` | pegawai × tanggal izin × pengajuan | `(perizinan_id_sumber, pegawai_id, tanggal_izin)` |
| `cur_attendance_regular_daily` | pegawai × tanggal | `(pegawai_id, tanggal)` |
| `cur_nonregular_event_daily` | pegawai × tanggal kerja × jadwal non-reguler | `(pegawai_id, tanggal_kerja, jadwal_id_sumber)` |

## 3. Snapshot historis dan update

### 3.1 Snapshot harian

Setiap tanggal proses, ETL menyimpan snapshot:

- status dan departemen pegawai;
- shift regular aktif per departemen;
- jadwal shift menurut hari;
- kalender, hari libur, dan libur shift individual.

```text
snapshot pegawai harian
+ snapshot shift–jadwal regular harian
+ snapshot kalender/libur harian
→ cur_employee_workday per tanggal
```

Perubahan status, departemen, shift, atau jadwal hanya berlaku bagi snapshot
sesudah perubahan. Record historis memakai snapshot tanggalnya sendiri.

### 3.2 Update tanggal berjalan dan koreksi

- Tanggal berjalan boleh dihitung ulang dan di-upsert menurut business key.
- Query workday memulai dari seluruh `m_pegawai`; status aktif diturunkan
  menjadi kolom, bukan filter awal. Perubahan aktif → nonaktif pada tanggal
  berjalan pun dapat mengubah kewajiban menjadi `false`.
- Tanggal yang telah ditutup tidak berubah karena refresh master harian.
- Reprocess historis dilakukan eksplisit, memakai snapshot tanggal terkait dan
  jejak audit revisi.
- Perubahan/persetujuan izin memicu reprocess seluruh tanggal dalam rentang
  izinnya; ini adalah koreksi transaksi, bukan refresh master.

## 4. `cur_employee_workday`

### 4.1 Tujuan

Objek ini adalah satu-satunya sumber denominator dashboard reguler. Ia
membentuk satu kandidat kewajiban per pegawai–tanggal, termasuk pegawai tanpa
event presensi dan pegawai dengan izin penuh.

### 4.2 STTM kolom

| Kolom target | Sumber | Aturan |
|---|---|---|
| `pegawai_id` | `m_pegawai.id` | Salin identitas pegawai. |
| `tanggal` | kalender ETL / `dim_calendar.tanggal` | Satu tanggal dalam periode proses. |
| `departemen_id` | snapshot `m_pegawai.departemen` | Departemen yang berlaku pada snapshot tanggal tersebut. |
| `is_employee_active` | snapshot `m_pegawai.status` | `true` bila status termasuk kategori aktif. |
| `has_regular_schedule` | snapshot `m_shift`, `m_jadwal` | Ada minimal satu kandidat regular aktif untuk departemen dan hari terkait. |
| `candidate_regular_schedule_count` | snapshot `m_shift`, `m_jadwal` | Jumlah kandidat; untuk audit, bukan pengali denominator. |
| `is_day_off` | kalender, `m_hari_libur`, `t_libur_shift` | Weekend, hari libur, atau libur individual. |
| `is_expected_workday` | turunan | Lihat rumus berikut. |
| `source_snapshot_at` | proses snapshot | Waktu snapshot sumber. |
| `source_updated_at` | sumber bila tersedia | Waktu sumber paling baru. |

Kandidat jadwal dibentuk lebih dahulu pada grain `departemen × hari`:

```text
m_pegawai.departemen = m_shift.departemen_id
m_shift.status = true
nama shift mengandung keyword "regular" (case-insensitive)
m_jadwal.jenis = m_shift.id
m_jadwal.hari = hari kalender yang diproses
```

Satu departemen dapat mempunyai banyak shift regular aktif pada hari sama.
Hal tersebut tidak menggandakan workday: pegawai cukup melakukan presensi pada
salah satu jadwal regular aktif.

```text
has_regular_schedule = candidate_regular_schedule_count > 0
is_day_off = is_weekend OR is_hari_libur OR has_libur_shift
is_expected_workday =
  is_employee_active AND has_regular_schedule AND NOT is_day_off
```

## 5. `cur_event_attendance`

### 5.1 Tujuan

Satu bukti event `t_checkinout` beserta lookup dan validasi historisnya.
Tahap ini tidak mengagregasikan event.

### 5.2 STTM kolom

| Kolom target | Sumber / aturan |
|---|---|
| `checkinout_id_sumber` | `t_checkinout.id` |
| `pegawai_id` | `t_checkinout.pegawai_id` |
| `tanggal_event`, `waktu_event` | `t_checkinout.created_at` dalam konteks Asia/Jakarta |
| `checktype` | `t_checkinout.checktype` |
| `departemen_id_event` | `t_checkinout.departemen` |
| `jadwal_id_sumber`, `work_code_sumber` | `t_checkinout.jadwal_id`, `t_checkinout.work_code` |
| `jam_masuk_sumber`, `jam_keluar_sumber` | `t_checkinout.jam_masuk`, `t_checkinout.jam_keluar` |
| `is_manual`, `is_wfh_sumber` | `t_checkinout.is_manual`, `t_checkinout.is_wfh` |
| `event_updated_at` | `t_checkinout.updated_at` |
| `shift_id_sumber`, `nama_shift_snapshot` | Lookup snapshot shift–jadwal tanggal event |
| `is_regular_shift`, `is_nonregular_shift` | Klasifikasi shift pada snapshot tanggal event |
| `event_type` | `MASUK` bila checktype 1; `PULANG` bila 2; selain itu `LAIN` |
| `is_valid_event_type` | `checktype IN (1,2)` |
| `perlu_review`, `alasan_review` | Hasil validasi historis |
| `source_snapshot_at` | Snapshot tanggal event |

Snapshot membuktikan konteks event pada tanggal kejadian. Ketidakcocokan
referensi tidak menghapus event; ia diberi review, misalnya
`JADWAL_TIDAK_DITEMUKAN_PADA_SNAPSHOT`,
`WORK_CODE_TIDAK_COCOK_DENGAN_SHIFT_JADWAL`,
`DEPARTEMEN_EVENT_TIDAK_COCOK_DENGAN_SNAPSHOT_PEGAWAI`, atau
`PEGAWAI_TIDAK_AKTIF_PADA_SNAPSHOT`.

Event manual tetap valid sebagai bukti KPI. Hanya checktype 1 dan 2 membentuk
metrik check-in/check-out. Event terlambat harus memakai snapshot tanggal event,
bukan snapshot tanggal pemrosesan.

## 6. `cur_regular_event_daily`

```text
Grain  : satu pegawai × satu tanggal kerja
Sumber : cur_event_attendance
Filter : is_regular_shift = true
         AND event_type IN ('MASUK', 'PULANG')
```

| Kolom target | Aturan |
|---|---|
| `pegawai_id`, `tanggal_kerja` | Key agregasi. |
| `departemen_id_event` | Departemen tercatat pada event. |
| `has_masuk`, `has_pulang` | Ada minimal satu event MASUK/PULANG. |
| `checkin_event_count`, `checkout_event_count` | Jumlah event per tipe untuk audit duplikasi. |
| `first_checkin_at`, `last_checkout_at` | Check-in paling awal dan check-out paling akhir. |
| `has_manual_event` | Ada minimal satu event manual. |
| `regular_schedule_count` | Jumlah jadwal regular transaksi yang muncul. |
| `is_complete_attendance` | `has_masuk AND has_pulang`. |
| `perlu_review`, `alasan_review` | Ambiguitas event, pasangan, atau jadwal. |
| `source_snapshot_at` | Referensi snapshot validasi event. |

Aturan tanggal kerja:

```text
check-in                   → tanggal event check-in
check-out hari yang sama   → tanggal event check-out
check-out lintas tengah malam → tanggal check-in pasangan
check-out tanpa pasangan   → tidak dipaksa ke hari sebelumnya; review
```

Pasangan lintas tengah malam minimal mempunyai pegawai yang sama, check-out
sesudah check-in, dan `jadwal_id_sumber` yang sama jika keduanya tersedia.
Jika kandidat lebih dari satu, sistem tidak memilih otomatis.

```text
checkin_days  = has_masuk
checkout_days = has_pulang
```

Keduanya independen dari kelengkapan presensi maupun status administratif.

## 7. `cur_leave_daily`

```text
Grain  : satu pegawai × satu tanggal izin × satu pengajuan
Sumber : t_perizinan, m_user, m_jenis_ijin, m_tipe_ijin
```

| Kolom target | Sumber / aturan |
|---|---|
| `perizinan_id_sumber` | `t_perizinan.id` |
| `pegawai_id` | `t_perizinan.pegawai_id`; validasi silang `user_id → m_user.pegawai_id` |
| `tanggal_izin` | Ekspansi inklusif rentang izin. |
| `departemen_id_izin` | `t_perizinan.departemen`, sebagai bukti transaksi. |
| `jenis_izin_id_sumber`, `nama_jenis_izin` | `t_perizinan.jenis_ijin → m_jenis_ijin` |
| `tipe_izin_id_sumber`, `nama_tipe_izin` | `m_jenis_ijin.tipe_id → m_tipe_ijin` |
| `approval`, `approval_at` | `t_perizinan.approval`, `t_perizinan.approval_at` |
| `is_full_day_leave` | `m_jenis_ijin.setengah_hari = false` |
| `is_partial_day_leave` | `m_jenis_ijin.setengah_hari = true` |
| `is_valid_leave` | Approved, identitas/rentang/referensi valid. |
| `perlu_review`, `alasan_review` | Ketidaksesuaian identitas, rentang, atau referensi. |
| `source_updated_at`, `source_snapshot_at` | Audit pembaruan dan snapshot. |

```text
tanggal_mulai = tgl_ijin
tanggal_akhir = COALESCE(tgl_ijin_sampai, tgl_ijin)
buat satu baris untuk setiap tanggal inklusif,
hanya bila tanggal_akhir >= tanggal_mulai
```

Izin penuh dan parsial sama-sama diekspansi. Jika overlap, izin penuh
berprioritas dalam hasil pegawai–tanggal, tetapi seluruh pengajuan tetap
tersimpan di tabel ini.

## 8. `cur_attendance_regular_daily`

Objek ini adalah record terpadu siap fakta reguler. Basis key adalah union
agar event atau izin tidak hilang:

```text
(pegawai_id, tanggal) dari cur_employee_workday
UNION
(pegawai_id, tanggal_kerja) dari cur_regular_event_daily
UNION
(pegawai_id, tanggal_izin) dari cur_leave_daily
```

| Kelompok | Kolom |
|---|---|
| Identitas | `pegawai_id`, `tanggal`, `departemen_id` |
| Kewajiban | `is_employee_active`, `has_regular_schedule`, `is_day_off`, `is_expected_workday` |
| Event | `has_masuk`, `has_pulang`, jumlah event, waktu pertama/terakhir, `has_manual_event` |
| Izin | `has_full_day_leave`, `has_partial_day_leave`, `selected_leave_coverage` |
| Kehadiran | `is_complete_attendance`, `status_kehadiran` |
| Keterlambatan | `is_late`, `late_minutes`, `late_schedule_id_sumber` |
| Audit | `perlu_review`, `alasan_review`, `source_snapshot_at` |

Aturan izin dan status:

```text
has_full_day_leave    = ada izin harian valid yang penuh
has_partial_day_leave = ada izin harian valid yang parsial

selected_leave_coverage =
  FULL    bila has_full_day_leave
  PARTIAL bila bukan FULL dan has_partial_day_leave
  NONE    selain itu

IZIN = has_full_day_leave
HADIR_LENGKAP = NOT has_full_day_leave AND has_masuk AND has_pulang
CHECKIN_BELUM_PULANG = NOT has_full_day_leave AND has_masuk AND NOT has_pulang
TANPA_KETERANGAN =
  NOT has_full_day_leave
  AND is_expected_workday
  AND NOT has_masuk
  AND NOT has_pulang
```

Izin parsial tidak menghapus kewajiban check-in/out dan tidak mengubah
denominator. Hanya izin penuh yang menghasilkan status administratif `IZIN`.

KPI flags:

```text
scheduled_regular_days   = is_expected_workday ? 1 : 0
checkin_days             = has_masuk ? 1 : 0
checkout_days            = has_pulang ? 1 : 0
complete_attendance_days = (has_masuk AND has_pulang) ? 1 : 0
leave_days               = has_full_day_leave ? 1 : 0
```

Izin penuh dan parsial tetap berada pada denominator
`scheduled_regular_days`.

Keterlambatan memakai nilai sumber pada event:

```text
waktu check-in aktual = t_checkinout.created_at
jam masuk seharusnya  = t_checkinout.jam_masuk

is_late = first_checkin_at > tanggal + jam_masuk_sumber
late_minutes = selisih menit positif antara keduanya
```

Snapshot jadwal memvalidasi konsistensi `jadwal_id`, `work_code`, dan jam
pada event. Jika beberapa jadwal transaksi atau referensinya ambigu,
keterlambatan dikosongkan dan record diberi review; check-in/out tetap tercatat.

## 9. `cur_nonregular_event_daily`

```text
Grain  : satu pegawai × satu tanggal kerja × satu jadwal non-reguler
Sumber : cur_event_attendance
Filter : is_nonregular_shift = true
         AND event_type IN ('MASUK', 'PULANG')
```

Kolom target:

```text
pegawai_id
tanggal_kerja
jadwal_id_sumber
shift_id_sumber
departemen_id_event
has_masuk
has_pulang
checkin_event_count
checkout_event_count
first_checkin_at
last_checkout_at
has_manual_event
mode_kerja_event
is_complete_attendance
perlu_review
alasan_review
source_snapshot_at
```

```text
has_masuk  = ada minimal satu event MASUK
has_pulang = ada minimal satu event PULANG
is_complete_attendance = has_masuk AND has_pulang
```

Tanggal kerja memakai aturan pairing yang sama dengan event regular. Event
manual tetap dihitung. Tabel ini tidak mempunyai `is_expected_workday`,
`scheduled_regular_days`, `leave_days`, ataupun attendance rate.

Dashboard non-reguler hanya boleh melaporkan metrik event, misalnya pegawai unik
dengan check-in atau check-out. Tanpa roster penugasan non-reguler, angka itu
bukan tingkat kepatuhan atau attendance rate.

## 10. Metrik reguler yang ditopang curated

```text
Check-in Rate =
  SUM(checkin_days) / SUM(scheduled_regular_days)

Attendance Rate =
  SUM(complete_attendance_days) / SUM(scheduled_regular_days)
```

`scheduled_regular_days` mencakup pegawai terjadwal dengan izin penuh maupun
parsial. `checkin_days` dan `checkout_days` adalah bukti event yang
independen dari status administratif.

