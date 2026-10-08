# ERD sumber OLTP untuk migrasi Apache Hop

Diverifikasi dari metadata database OLTP dan pembacaan sumber ETL pada 29 September 2026. Cakupan: 11 tabel yang dibaca ETL saat ini, bukan seluruh database aplikasi. Kolom ditampilkan secara selektif.

PK = primary key aktual; FK = foreign key aktual. Label LOGIS menunjukkan relasi yang digunakan ETL tetapi tidak dijamin constraint database. Garis titik pada Mermaid merupakan relasi non-identifying, bukan penanda ketiadaan FK. Kardinalitas relasi logis menggambarkan tujuan pemetaan; orphan harus divalidasi.

```mermaid
erDiagram
    mDepartemen["m_departemen"] {
        int id PK
        varchar kode
        varchar nama_departemen
    }
    mPegawai["m_pegawai"] {
        int id PK
        varchar nip
        varchar nama
        int departemen FK
        timestamp updated_at
    }
    mUser["m_user"] {
        int id PK
        int pegawai_id FK
        boolean is_active
        timestamp last_login
    }
    mShift["m_shift"] {
        int id PK
        int departemen_id FK
        varchar nama
        int is_flexible
    }
    mJadwal["m_jadwal"] {
        int id PK
        int jenis FK
        varchar hari
        time jam_masuk
        time jam_keluar
        time jam_masuk_awal
        time jam_keluar_akhir
    }
    tCheckinout["t_checkinout"] {
        int id PK
        int pegawai_id FK
        int departemen
        int work_code
        smallint is_wfh
        timestamp created_at
        timestamp updated_at
    }
    tLiburShift["t_libur_shift"] {
        int id PK
        int pegawai_id FK
        int departemen_id
        date tanggal
        varchar keterangan
    }
    mHariLibur["m_hari_libur"] {
        int id PK
        date tanggal
        varchar keterangan
    }
    mTipeIjin["m_tipe_ijin"] {
        int id PK
        varchar nama
        varchar tipe
    }
    mJenisIjin["m_jenis_ijin"] {
        int id PK
        int tipe_id FK
        varchar nama
        varchar kode
    }
    tPerizinan["t_perizinan"] {
        int id PK
        int user_id FK
        int pegawai_id "LOGIS ke m_pegawai.id"
        int departemen
        int tipe_ijin
        int jenis_ijin FK
        boolean approval
        date tgl_ijin
        date tgl_ijin_sampai
        timestamp updated_at
    }
    mDepartemen ||..o{ mPegawai : "FK departemen"
    mDepartemen o|..o{ mShift : "FK departemen_id"
    mShift ||..o{ mJadwal : "FK jenis"
    mPegawai o|..o{ mUser : "FK pegawai_id"
    mPegawai ||..o{ tCheckinout : "FK pegawai_id"
    mPegawai o|..o{ tLiburShift : "FK pegawai_id"
    mUser ||..o{ tPerizinan : "FK user_id"
    mTipeIjin o|..o{ mJenisIjin : "FK tipe_id"
    mJenisIjin ||..o{ tPerizinan : "FK jenis_ijin"
    mPegawai o|..o{ tPerizinan : "LOGIS pegawai_id"
```

## Fungsi tabel dalam migrasi

| Tabel | Fungsi |
|---|---|
| m_departemen | Sumber dimensi departemen dan lingkup jadwal |
| m_pegawai | Sumber dimensi pegawai dan populasi dasar pegawai-hari |
| m_shift, m_jadwal | Sumber jadwal kerja per departemen dan hari |
| m_hari_libur | Sumber kalender hari libur berdasarkan tanggal; tidak memiliki FK ke tabel presensi |
| t_libur_shift | Pengecualian hari kerja per pegawai dan tanggal |
| t_checkinout | Event presensi; ETL saat ini memilih work_code = 1 |
| m_tipe_ijin, m_jenis_ijin | Referensi klasifikasi izin |
| t_perizinan | Pengajuan, rentang tanggal, dan keputusan izin |
| m_user | Sumber analytical_user pada initial load, serta induk user_id pada pengajuan izin; bukan sumber role SSO final |

## Catatan relasi dan business rule

- Diagram menampilkan jalur relasi utama yang relevan untuk ETL. Kolom departemen pada t_checkinout/t_perizinan dan departemen_id pada t_libur_shift tidak memiliki FK departemen pada database yang diperiksa. t_perizinan.tipe_ijin juga tidak memiliki FK; hubungan tipe yang dijamin adalah m_jenis_ijin.tipe_id ke m_tipe_ijin.id.
- ETL menghubungkan izin ke pegawai melalui t_perizinan.pegawai_id, bukan semata-mata melalui user_id. Validasi kesesuaian kedua identitas perlu dirancang di Hop.
- Tidak ada jaminan satu akun per pegawai hanya dari FK m_user.pegawai_id. Jangan menganggap relasi 1:1 tanpa pemeriksaan constraint/data.
- Jadwal ETL saat ini ditentukan melalui departemen pegawai -> m_shift -> m_jadwal, lalu dicocokkan dengan hari. Kombinasi departemen dan hari harus tidak ambigu.
- t_checkinout juga memiliki checktype dan jadwal_id, tetapi belum dipakai oleh transformasi presensi saat ini. Arti serta kelengkapan datanya perlu divalidasi sebelum mengubah aturan di Hop.
- m_pegawai.status merujuk m_previleges, bukan otomatis status aktif/nonaktif pegawai. m_previleges, m_lokasi, dan m_group adalah referensi aplikasi di luar cakupan ekstraksi ETL saat ini.
- Tidak ada tabel sumber khusus untuk tidak masuk tanpa izin. Status tersebut diturunkan dari pegawai x tanggal, jadwal wajib kerja, tidak adanya presensi, dan tidak adanya izin sah.
- Kalender lengkap dibentuk saat ETL; m_hari_libur hanya menyediakan tanggal pengecualian.
- Kolom created_at/updated_at dan kolom payload lainnya disederhanakan di diagram. Diagram ini bukan daftar SELECT final untuk pipeline Hop.
