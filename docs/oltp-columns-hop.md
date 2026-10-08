# Seluruh kolom sumber OLTP untuk review mapping Hop

Snapshot metadata: 2026-09-29T09:24:14.511042+00:00

Cakupan: seluruh kolom pada 11 tabel sumber ETL saat ini, bukan seluruh tabel OLTP. Metadata diambil langsung dari PostgreSQL dalam transaksi read-only. Tidak ada nilai data pegawai maupun kredensial yang diekspor.

Nullable YA berarti database mengizinkan NULL. FK hanya menunjukkan constraint yang benar-benar terpasang. Kolom target dan keputusan mapping pada CSV sengaja kosong untuk review pengguna; keberadaan kolom tidak berarti harus dimuat ke OLAP.

| Tabel | Jumlah kolom |
|---|---:|
| m_departemen | 19 |
| m_pegawai | 24 |
| m_user | 28 |
| m_shift | 8 |
| m_jadwal | 9 |
| m_tipe_ijin | 3 |
| m_jenis_ijin | 9 |
| m_hari_libur | 4 |
| t_libur_shift | 8 |
| t_perizinan | 20 |
| t_checkinout | 31 |

## m_departemen

| No | Kolom | Tipe PostgreSQL | Nullable | Default | Constraint |
|---:|---|---|---|---|---|
| 1 | id | integer | TIDAK | nextval('m_departemen_id_seq'::regclass) | PRIMARY KEY (id); NOT NULL id |
| 2 | kode | character varying(40) | YA | — | UNIQUE (kode) |
| 3 | nama_departemen | character varying(200) | YA | — | — |
| 4 | parent | integer | YA | 0 | — |
| 5 | latlong | character varying(200) | YA | — | — |
| 6 | created_at | timestamp without time zone | YA | — | — |
| 7 | address | text | YA | — | — |
| 8 | logo | character varying(200) | YA | — | — |
| 9 | lokasi | integer | YA | — | FOREIGN KEY (lokasi) REFERENCES m_lokasi(id) ON UPDATE SET NULL ON DELETE SET NULL |
| 10 | logo_qr | character varying(200) | YA | — | — |
| 11 | opd_parent | integer | YA | — | — |
| 12 | kode_lengkap | text | YA | — | — |
| 13 | order | integer | YA | — | — |
| 14 | is_remun | integer | YA | 0 | — |
| 15 | is_allow_wfh | integer | YA | 0 | — |
| 16 | unit_kerja_induk | integer | YA | — | — |
| 17 | is_using_wajah | integer | YA | 0 | — |
| 18 | upload_wajah | integer | YA | — | — |
| 19 | hari_senam | character varying(10) | YA | 'wed'::character varying | — |

Constraint tabel:

- `m_departemen_id`: `PRIMARY KEY (id)`
- `m_departemen_id_not_null`: `NOT NULL id`
- `m_departemen_kode`: `UNIQUE (kode)`
- `m_departemen_lokasi_fkey`: `FOREIGN KEY (lokasi) REFERENCES m_lokasi(id) ON UPDATE SET NULL ON DELETE SET NULL`

Index aktual:

- `CREATE INDEX idx_departemen_kode ON public.m_departemen USING btree (kode)`
- `CREATE UNIQUE INDEX m_departemen_id ON public.m_departemen USING btree (id)`
- `CREATE INDEX m_departemen_id_index ON public.m_departemen USING btree (id)`
- `CREATE UNIQUE INDEX m_departemen_kode ON public.m_departemen USING btree (kode)`
- `CREATE INDEX m_departemen_lokasi ON public.m_departemen USING btree (lokasi)`
- `CREATE INDEX m_departemen_parent ON public.m_departemen USING btree (parent)`
- `CREATE INDEX m_departemen_temp_lokasi ON public.m_departemen USING btree (lokasi)`

## m_pegawai

| No | Kolom | Tipe PostgreSQL | Nullable | Default | Constraint |
|---:|---|---|---|---|---|
| 1 | id | integer | TIDAK | nextval('m_pegawai_id_seq'::regclass) | PRIMARY KEY (id); NOT NULL id |
| 2 | nip | character varying(200) | TIDAK | — | UNIQUE (nip); NOT NULL nip |
| 3 | nama | character varying(200) | TIDAK | — | NOT NULL nama |
| 4 | departemen | integer | TIDAK | — | FOREIGN KEY (departemen) REFERENCES m_departemen(id) ON UPDATE RESTRICT ON DELETE RESTRICT; NOT NULL departemen |
| 5 | alamat | text | YA | — | — |
| 6 | jenis_kelamin | integer | YA | — | — |
| 7 | created_at | timestamp without time zone | YA | — | — |
| 8 | updated_at | timestamp without time zone | YA | — | — |
| 9 | email | character varying(100) | YA | — | — |
| 10 | foto | character varying(200) | YA | — | — |
| 11 | jabatan | character varying(200) | YA | — | — |
| 12 | status | integer | YA | 1 | FOREIGN KEY (status) REFERENCES m_previleges(id) ON UPDATE RESTRICT ON DELETE RESTRICT |
| 13 | qr_code | text | YA | — | — |
| 14 | unit_kerja_induk | integer | YA | — | — |
| 15 | status_shift | integer | YA | 5 | — |
| 16 | pangkat | character varying(100) | YA | — | — |
| 17 | jenis_jabatan | character varying(250) | YA | — | — |
| 18 | eselon | character varying(250) | YA | — | — |
| 19 | other_attr | character varying(10) | YA | — | — |
| 20 | kelas_jabatan | character varying(10) | YA | — | — |
| 21 | nip_lama | character varying(200) | YA | — | — |
| 22 | jenis_tpp | integer | YA | — | — |
| 23 | attrs | text | YA | — | — |
| 24 | is_foto_approved | integer | YA | 0 | — |

Constraint tabel:

- `m_pegawai_departemen_fkey`: `FOREIGN KEY (departemen) REFERENCES m_departemen(id) ON UPDATE RESTRICT ON DELETE RESTRICT`
- `m_pegawai_departemen_not_null`: `NOT NULL departemen`
- `m_pegawai_id`: `PRIMARY KEY (id)`
- `m_pegawai_id_not_null`: `NOT NULL id`
- `m_pegawai_nama_not_null`: `NOT NULL nama`
- `m_pegawai_nip`: `UNIQUE (nip)`
- `m_pegawai_nip_not_null`: `NOT NULL nip`
- `m_pegawai_status_fkey`: `FOREIGN KEY (status) REFERENCES m_previleges(id) ON UPDATE RESTRICT ON DELETE RESTRICT`

Index aktual:

- `CREATE INDEX idx_pegawai_departemen ON public.m_pegawai USING btree (departemen)`
- `CREATE INDEX idx_pegawai_status_shift ON public.m_pegawai USING btree (status_shift)`
- `CREATE UNIQUE INDEX m_pegawai_id ON public.m_pegawai USING btree (id)`
- `CREATE INDEX m_pegawai_id_index ON public.m_pegawai USING btree (id)`
- `CREATE INDEX m_pegawai_nama ON public.m_pegawai USING btree (nama)`
- `CREATE UNIQUE INDEX m_pegawai_nip ON public.m_pegawai USING btree (nip)`
- `CREATE INDEX m_pegawai_previleges_id ON public.m_pegawai USING btree (status)`

## m_user

| No | Kolom | Tipe PostgreSQL | Nullable | Default | Constraint |
|---:|---|---|---|---|---|
| 1 | id | integer | TIDAK | nextval('m_user_id_seq'::regclass) | NOT NULL id; PRIMARY KEY (id) |
| 2 | email | character varying(100) | TIDAK | — | NOT NULL email |
| 3 | salt | character varying(100) | YA | — | — |
| 4 | password | character varying(100) | YA | — | — |
| 5 | nama | character varying(100) | TIDAK | — | NOT NULL nama |
| 6 | is_login | integer | YA | — | — |
| 7 | last_login | timestamp without time zone | YA | — | — |
| 8 | deskripsi | text | YA | — | — |
| 9 | is_active | boolean | YA | true | — |
| 10 | group_id | integer | YA | — | FOREIGN KEY (group_id) REFERENCES m_group(id) ON UPDATE CASCADE ON DELETE RESTRICT |
| 11 | api_key | character varying(400) | YA | — | — |
| 12 | imei | character varying(50) | YA | — | — |
| 13 | latlong | character varying(400) | YA | — | — |
| 14 | last_latlong | character varying(400) | YA | — | — |
| 15 | pegawai_id | integer | YA | — | FOREIGN KEY (pegawai_id) REFERENCES m_pegawai(id) ON UPDATE CASCADE ON DELETE CASCADE |
| 16 | created_at | timestamp without time zone | YA | — | — |
| 17 | updated_at | timestamp without time zone | YA | — | — |
| 18 | last_activity | character varying(200) | YA | — | — |
| 19 | last_activity_at | timestamp without time zone | YA | — | — |
| 20 | fcm_web | text | YA | — | — |
| 21 | fcm_mobile | text | YA | — | — |
| 22 | unit_kerja | integer | YA | — | — |
| 23 | msg_id | character varying(100) | YA | — | — |
| 24 | msg_token | text | YA | — | — |
| 25 | created_by | character varying(100) | YA | — | — |
| 26 | updated_by | character varying(100) | YA | — | — |
| 27 | ip | character varying(50) | YA | — | — |
| 28 | versi | character(50) | YA | — | — |

Constraint tabel:

- `m_user_email_not_null`: `NOT NULL email`
- `m_user_group_id_fkey`: `FOREIGN KEY (group_id) REFERENCES m_group(id) ON UPDATE CASCADE ON DELETE RESTRICT`
- `m_user_id_not_null`: `NOT NULL id`
- `m_user_nama_not_null`: `NOT NULL nama`
- `m_user_pegawai_id_fkey`: `FOREIGN KEY (pegawai_id) REFERENCES m_pegawai(id) ON UPDATE CASCADE ON DELETE CASCADE`
- `m_user_pkey`: `PRIMARY KEY (id)`

Index aktual:

- `CREATE INDEX fk2 ON public.m_user USING btree (group_id)`
- `CREATE INDEX id ON public.m_user USING btree (id)`
- `CREATE INDEX m_user_anggota_id ON public.m_user USING btree (pegawai_id)`
- `CREATE INDEX m_user_api_key ON public.m_user USING btree (api_key)`
- `CREATE INDEX m_user_is_active ON public.m_user USING btree (is_active)`
- `CREATE UNIQUE INDEX m_user_pkey ON public.m_user USING btree (id)`
- `CREATE INDEX m_user_unit_kerja ON public.m_user USING btree (unit_kerja)`

## m_shift

| No | Kolom | Tipe PostgreSQL | Nullable | Default | Constraint |
|---:|---|---|---|---|---|
| 1 | id | integer | TIDAK | nextval('m_shift_id_seq'::regclass) | PRIMARY KEY (id); NOT NULL id |
| 2 | nama | character varying(200) | TIDAK | — | NOT NULL nama |
| 3 | status | boolean | YA | true | — |
| 4 | departemen_id | integer | YA | — | FOREIGN KEY (departemen_id) REFERENCES m_departemen(id) ON UPDATE CASCADE ON DELETE CASCADE |
| 5 | created_at | timestamp without time zone | YA | — | — |
| 6 | created_by | integer | YA | — | — |
| 7 | event_id | integer | YA | — | — |
| 8 | is_flexible | integer | YA | 0 | — |

Constraint tabel:

- `m_shift_departemen_id_fkey`: `FOREIGN KEY (departemen_id) REFERENCES m_departemen(id) ON UPDATE CASCADE ON DELETE CASCADE`
- `m_shift_id`: `PRIMARY KEY (id)`
- `m_shift_id_not_null`: `NOT NULL id`
- `m_shift_nama_not_null`: `NOT NULL nama`

Index aktual:

- `CREATE INDEX m_shift_departemen_id ON public.m_shift USING btree (departemen_id)`
- `CREATE UNIQUE INDEX m_shift_id ON public.m_shift USING btree (id)`

## m_jadwal

| No | Kolom | Tipe PostgreSQL | Nullable | Default | Constraint |
|---:|---|---|---|---|---|
| 1 | id | integer | TIDAK | nextval('m_jadwal_id_seq'::regclass) | PRIMARY KEY (id); NOT NULL id |
| 2 | jenis | integer | TIDAK | — | FOREIGN KEY (jenis) REFERENCES m_shift(id) ON UPDATE CASCADE ON DELETE CASCADE; NOT NULL jenis |
| 3 | hari | character varying(200) | TIDAK | — | NOT NULL hari |
| 4 | jam_masuk | time without time zone | TIDAK | — | NOT NULL jam_masuk |
| 5 | jam_keluar | time without time zone | TIDAK | — | NOT NULL jam_keluar |
| 6 | created_at | timestamp without time zone | YA | — | — |
| 7 | jam_masuk_awal | time without time zone | TIDAK | — | NOT NULL jam_masuk_awal |
| 8 | jam_keluar_akhir | time without time zone | TIDAK | — | NOT NULL jam_keluar_akhir |
| 9 | flexible_time | time without time zone | YA | — | — |

Constraint tabel:

- `m_jadwal_hari_not_null`: `NOT NULL hari`
- `m_jadwal_id`: `PRIMARY KEY (id)`
- `m_jadwal_id_not_null`: `NOT NULL id`
- `m_jadwal_jam_keluar_akhir_not_null`: `NOT NULL jam_keluar_akhir`
- `m_jadwal_jam_keluar_not_null`: `NOT NULL jam_keluar`
- `m_jadwal_jam_masuk_awal_not_null`: `NOT NULL jam_masuk_awal`
- `m_jadwal_jam_masuk_not_null`: `NOT NULL jam_masuk`
- `m_jadwal_jenis_fkey`: `FOREIGN KEY (jenis) REFERENCES m_shift(id) ON UPDATE CASCADE ON DELETE CASCADE`
- `m_jadwal_jenis_not_null`: `NOT NULL jenis`

Index aktual:

- `CREATE UNIQUE INDEX m_jadwal_id ON public.m_jadwal USING btree (id)`
- `CREATE INDEX m_jadwal_jenis ON public.m_jadwal USING btree (jenis)`

## m_tipe_ijin

| No | Kolom | Tipe PostgreSQL | Nullable | Default | Constraint |
|---:|---|---|---|---|---|
| 1 | id | integer | TIDAK | nextval('m_tipe_ijin_id_seq'::regclass) | PRIMARY KEY (id); NOT NULL id |
| 2 | nama | character varying(200) | TIDAK | — | NOT NULL nama |
| 3 | tipe | character varying(10) | YA | '[1, 2, 3]'::character varying | — |

Constraint tabel:

- `m_tipe_ijin_id`: `PRIMARY KEY (id)`
- `m_tipe_ijin_id_not_null`: `NOT NULL id`
- `m_tipe_ijin_nama_not_null`: `NOT NULL nama`

Index aktual:

- `CREATE UNIQUE INDEX m_tipe_ijin_id ON public.m_tipe_ijin USING btree (id)`

## m_jenis_ijin

| No | Kolom | Tipe PostgreSQL | Nullable | Default | Constraint |
|---:|---|---|---|---|---|
| 1 | id | integer | TIDAK | nextval('m_jenis_ijin_id_seq'::regclass) | PRIMARY KEY (id); NOT NULL id |
| 2 | nama | character varying(200) | TIDAK | — | NOT NULL nama |
| 3 | kode | character varying(50) | YA | — | — |
| 4 | setengah_hari | boolean | YA | false | — |
| 5 | created_at | timestamp without time zone | YA | — | — |
| 6 | tipe_id | integer | YA | — | FOREIGN KEY (tipe_id) REFERENCES m_tipe_ijin(id) ON UPDATE CASCADE ON DELETE CASCADE |
| 7 | potongan | character varying(5) | YA | — | — |
| 8 | is_aktif | integer | YA | 1 | — |
| 9 | label_kode | character varying(100) | YA | — | — |

Constraint tabel:

- `m_jenis_ijin_id`: `PRIMARY KEY (id)`
- `m_jenis_ijin_id_not_null`: `NOT NULL id`
- `m_jenis_ijin_nama_not_null`: `NOT NULL nama`
- `m_jenis_ijin_tipe_id_fkey`: `FOREIGN KEY (tipe_id) REFERENCES m_tipe_ijin(id) ON UPDATE CASCADE ON DELETE CASCADE`

Index aktual:

- `CREATE UNIQUE INDEX m_jenis_ijin_id ON public.m_jenis_ijin USING btree (id)`
- `CREATE INDEX m_jenis_ijin_kode ON public.m_jenis_ijin USING btree (kode)`
- `CREATE INDEX m_jenis_ijin_tipe_id ON public.m_jenis_ijin USING btree (tipe_id)`

## m_hari_libur

| No | Kolom | Tipe PostgreSQL | Nullable | Default | Constraint |
|---:|---|---|---|---|---|
| 1 | id | integer | TIDAK | nextval('m_hari_libur_id_seq'::regclass) | PRIMARY KEY (id); NOT NULL id |
| 2 | tanggal | date | TIDAK | — | NOT NULL tanggal |
| 3 | keterangan | character varying(200) | YA | — | — |
| 4 | created_at | timestamp without time zone | YA | — | — |

Constraint tabel:

- `m_hari_libur_id`: `PRIMARY KEY (id)`
- `m_hari_libur_id_not_null`: `NOT NULL id`
- `m_hari_libur_tanggal_not_null`: `NOT NULL tanggal`

Index aktual:

- `CREATE UNIQUE INDEX m_hari_libur_id ON public.m_hari_libur USING btree (id)`

## t_libur_shift

| No | Kolom | Tipe PostgreSQL | Nullable | Default | Constraint |
|---:|---|---|---|---|---|
| 1 | id | integer | TIDAK | nextval('t_libur_shift_id_seq'::regclass) | PRIMARY KEY (id); NOT NULL id |
| 2 | departemen_id | integer | YA | — | — |
| 3 | pegawai_id | integer | YA | — | FOREIGN KEY (pegawai_id) REFERENCES m_pegawai(id) ON UPDATE SET NULL ON DELETE SET NULL |
| 4 | tanggal | date | YA | — | — |
| 5 | keterangan | character varying(200) | YA | — | — |
| 6 | created_at | timestamp without time zone | YA | — | — |
| 7 | updated_at | timestamp without time zone | YA | — | — |
| 8 | created_by | integer | YA | — | — |

Constraint tabel:

- `t_libur_shift_id`: `PRIMARY KEY (id)`
- `t_libur_shift_id_not_null`: `NOT NULL id`
- `t_libur_shift_pegawai_id_fkey`: `FOREIGN KEY (pegawai_id) REFERENCES m_pegawai(id) ON UPDATE SET NULL ON DELETE SET NULL`

Index aktual:

- `CREATE UNIQUE INDEX t_libur_shift_id ON public.t_libur_shift USING btree (id)`

## t_perizinan

| No | Kolom | Tipe PostgreSQL | Nullable | Default | Constraint |
|---:|---|---|---|---|---|
| 1 | id | integer | TIDAK | nextval('t_perizinan_id_seq'::regclass) | PRIMARY KEY (id); NOT NULL id |
| 2 | user_id | integer | TIDAK | — | FOREIGN KEY (user_id) REFERENCES m_user(id) ON UPDATE RESTRICT ON DELETE RESTRICT; NOT NULL user_id |
| 3 | nama | character varying(200) | TIDAK | — | NOT NULL nama |
| 4 | departemen | integer | TIDAK | — | NOT NULL departemen |
| 5 | tipe_ijin | integer | TIDAK | — | NOT NULL tipe_ijin |
| 6 | jenis_ijin | integer | TIDAK | — | FOREIGN KEY (jenis_ijin) REFERENCES m_jenis_ijin(id) ON UPDATE SET NULL ON DELETE SET NULL; NOT NULL jenis_ijin |
| 7 | alasan | text | TIDAK | — | NOT NULL alasan |
| 8 | berkas | character varying(200) | YA | — | — |
| 9 | catatan | text | YA | — | — |
| 10 | approval | boolean | YA | false | — |
| 11 | approval_at | timestamp without time zone | YA | — | — |
| 12 | created_at | timestamp without time zone | YA | — | — |
| 13 | tgl_ijin | date | TIDAK | — | NOT NULL tgl_ijin |
| 14 | tgl_ijin_sampai | date | YA | — | — |
| 15 | pegawai_id | integer | YA | — | — |
| 16 | updated_at | timestamp without time zone | YA | — | — |
| 17 | status | smallint | YA | '1'::smallint | — |
| 18 | updated_user | integer | YA | — | — |
| 19 | latlong | character varying(60) | YA | — | — |
| 20 | tgl_emaster | date | YA | — | — |

Constraint tabel:

- `t_perizinan_alasan_not_null`: `NOT NULL alasan`
- `t_perizinan_departemen_not_null`: `NOT NULL departemen`
- `t_perizinan_id`: `PRIMARY KEY (id)`
- `t_perizinan_id_not_null`: `NOT NULL id`
- `t_perizinan_jenis_ijin_fkey`: `FOREIGN KEY (jenis_ijin) REFERENCES m_jenis_ijin(id) ON UPDATE SET NULL ON DELETE SET NULL`
- `t_perizinan_jenis_ijin_not_null`: `NOT NULL jenis_ijin`
- `t_perizinan_nama_not_null`: `NOT NULL nama`
- `t_perizinan_tgl_ijin_not_null`: `NOT NULL tgl_ijin`
- `t_perizinan_tipe_ijin_not_null`: `NOT NULL tipe_ijin`
- `t_perizinan_user_id_fkey`: `FOREIGN KEY (user_id) REFERENCES m_user(id) ON UPDATE RESTRICT ON DELETE RESTRICT`
- `t_perizinan_user_id_not_null`: `NOT NULL user_id`

Index aktual:

- `CREATE INDEX t_perizinan_departemen ON public.t_perizinan USING btree (departemen)`
- `CREATE UNIQUE INDEX t_perizinan_id ON public.t_perizinan USING btree (id)`
- `CREATE INDEX t_perizinan_pegawai_id ON public.t_perizinan USING btree (pegawai_id)`
- `CREATE INDEX t_perizinan_status ON public.t_perizinan USING btree (status)`
- `CREATE INDEX t_perizinan_user_id ON public.t_perizinan USING btree (user_id)`

## t_checkinout

| No | Kolom | Tipe PostgreSQL | Nullable | Default | Constraint |
|---:|---|---|---|---|---|
| 1 | id | integer | TIDAK | nextval('t_checkinout_id_seq'::regclass) | PRIMARY KEY (id); NOT NULL id |
| 2 | pegawai_id | integer | TIDAK | — | FOREIGN KEY (pegawai_id) REFERENCES m_pegawai(id) ON UPDATE RESTRICT ON DELETE RESTRICT; NOT NULL pegawai_id |
| 3 | latlong | character varying(60) | YA | — | — |
| 4 | departemen | integer | YA | — | — |
| 5 | location | integer | YA | — | — |
| 6 | jarak | double precision | YA | — | — |
| 7 | checktype | integer | YA | — | — |
| 8 | imei | character varying(50) | YA | — | — |
| 9 | approval | boolean | YA | false | — |
| 10 | approval_at | timestamp without time zone | YA | — | — |
| 11 | created_at | timestamp without time zone | YA | — | — |
| 12 | updated_at | timestamp without time zone | YA | — | — |
| 13 | current_location | text | YA | — | — |
| 14 | ijin | integer | YA | — | — |
| 15 | keterangan | text | YA | — | — |
| 16 | file | character varying(200) | YA | — | — |
| 17 | type_ijin | boolean | YA | false | — |
| 18 | deskripsi | text | YA | — | — |
| 19 | timezone | character varying(500) | YA | — | — |
| 20 | is_wfh | smallint | YA | '0'::smallint | — |
| 21 | work_code | integer | TIDAK | — | NOT NULL work_code |
| 22 | selisih_waktu | time without time zone | YA | — | — |
| 23 | jadwal_id | integer | YA | — | — |
| 24 | hari | character varying(20) | YA | — | — |
| 25 | jam_masuk | time without time zone | YA | — | — |
| 26 | jam_keluar | time without time zone | YA | — | — |
| 27 | jam_masuk_awal | time without time zone | YA | — | — |
| 28 | jam_keluar_akhir | time without time zone | YA | — | — |
| 29 | flexible_time | time without time zone | YA | — | — |
| 30 | is_manual | boolean | YA | false | — |
| 31 | temp_current_location | text | YA | — | — |

Constraint tabel:

- `t_checkinout_id`: `PRIMARY KEY (id)`
- `t_checkinout_id_not_null`: `NOT NULL id`
- `t_checkinout_pegawai_id_fkey`: `FOREIGN KEY (pegawai_id) REFERENCES m_pegawai(id) ON UPDATE RESTRICT ON DELETE RESTRICT`
- `t_checkinout_pegawai_id_not_null`: `NOT NULL pegawai_id`
- `t_checkinout_work_code_not_null`: `NOT NULL work_code`

Index aktual:

- `CREATE INDEX t_checkinout_created_at ON public.t_checkinout USING btree (created_at)`
- `CREATE INDEX t_checkinout_departemen ON public.t_checkinout USING btree (departemen)`
- `CREATE UNIQUE INDEX t_checkinout_id ON public.t_checkinout USING btree (id)`
- `CREATE INDEX t_checkinout_jadwal_id ON public.t_checkinout USING btree (jadwal_id)`
- `CREATE INDEX t_checkinout_location ON public.t_checkinout USING btree (location)`
- `CREATE INDEX t_checkinout_pegawai_id ON public.t_checkinout USING btree (pegawai_id)`
- `CREATE INDEX t_checkinout_updated_at ON public.t_checkinout USING btree (updated_at)`
- `CREATE INDEX t_checkinout_work_code ON public.t_checkinout USING btree (work_code)`

## Hal yang perlu dikonfirmasi saat mapping

- `m_pegawai.status` merujuk `m_previleges.id`; jangan langsung dipetakan sebagai status aktif pegawai. Transformasi saat ini mengisi status_aktif dengan NULL.
- `m_user.is_active` adalah atribut akun; maknanya berbeda dari status kepegawaian. Kolom autentikasi tercantum untuk kelengkapan skema, bukan usulan untuk dimuat ke analitik.
- `t_checkinout.checktype`, `jadwal_id`, `timezone`, `approval`, dan snapshot jam jadwal tersedia, tetapi belum dipakai perhitungan presensi saat ini. Makna nilai perlu dikonfirmasi sebelum mapping baru.
- `t_perizinan.approval` menentukan APPROVED/REJECTED/PENDING pada ETL sekarang; `status` belum dipakai sebagai penggantinya.
- `t_perizinan.pegawai_id` tidak memiliki FK aktual ke m_pegawai; relasi logis harus divalidasi.
- Departemen fact perizinan saat ini berasal dari referensi pegawai, bukan langsung dari `t_perizinan.departemen`.
- `m_jenis_ijin.setengah_hari` tersedia tetapi belum dipakai perhitungan izin saat ini.
- Relasi ke m_previleges, m_lokasi, dan m_group tercantum sesuai constraint aktual; seluruh kolom ketiga tabel tersebut belum termasuk karena bukan bagian dari 11 tabel sumber yang sedang direview.
