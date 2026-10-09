DO $$ BEGIN IF current_database()<>'epresensi_analytics_hop_dev' THEN RAISE EXCEPTION 'Wrong target'; END IF; END $$;
CREATE SCHEMA IF NOT EXISTS hop_etl;
CREATE TABLE IF NOT EXISTS hop_etl.fact_checkpoint (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), phase text NOT NULL DEFAULT 'events',
 first_id bigint NOT NULL, next_id bigint NOT NULL, last_id bigint NOT NULL,
 event_rows bigint NOT NULL DEFAULT 0, rejected_event_rows bigint NOT NULL DEFAULT 0,
 first_date date, next_date date, last_date date,
 batch_size integer NOT NULL DEFAULT 1000000, days_per_step integer NOT NULL DEFAULT 1,
 fact_rows bigint NOT NULL DEFAULT 0, changed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS hop_etl.fact_batches (
 start_id bigint PRIMARY KEY,end_id bigint NOT NULL,event_rows bigint NOT NULL,
 rejected_rows bigint NOT NULL, finished_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS hop_etl.event_day (
 tanggal date NOT NULL,pegawai_id integer NOT NULL,
 n bigint,
 n_in bigint,
 n_out bigint,
 n_other bigint,
 n_manual bigint,
 jadwal_id_min integer,
 jadwal_id_max integer,
 jadwal_id_nulls bigint,
 work_code_min integer,
 work_code_max integer,
 work_code_nulls bigint,
 departemen_min integer,
 departemen_max integer,
 departemen_nulls bigint,
 is_wfh_min smallint,
 is_wfh_max smallint,
 is_wfh_nulls bigint,
 timezone_min text,
 timezone_max text,
 timezone_nulls bigint,
 jam_masuk_min time,
 jam_masuk_max time,
 jam_masuk_nulls bigint,
 jam_keluar_min time,
 jam_keluar_max time,
 jam_keluar_nulls bigint,
 masuk_min timestamp,
 masuk_max timestamp,
 pulang_min timestamp,
 pulang_max timestamp,
 updated_max timestamp,
 event_min integer,
 event_max integer,
 PRIMARY KEY(tanggal,pegawai_id)
);
CREATE TABLE IF NOT EXISTS hop_etl.leave_source (
 id integer PRIMARY KEY,pegawai_id integer,user_pegawai_id integer,departemen integer,
 approval boolean,approval_at timestamp,awal date,akhir date,jenis_ijin integer,
 setengah_hari boolean,tipe_id integer,nama_jenis text,updated_at timestamp,
 periode daterange GENERATED ALWAYS AS (CASE WHEN akhir>=awal THEN daterange(awal,akhir,'[]') ELSE NULL END) STORED
);
CREATE INDEX IF NOT EXISTS hop_leave_period_idx ON hop_etl.leave_source USING gist(periode);
CREATE INDEX IF NOT EXISTS hop_leave_start_idx ON hop_etl.leave_source(awal);
CREATE INDEX IF NOT EXISTS hop_leave_invalid_start_idx ON hop_etl.leave_source(awal) WHERE periode IS NULL;
CREATE TABLE IF NOT EXISTS hop_etl.off_source (id integer PRIMARY KEY,pegawai_id integer,tanggal date,updated_at timestamp);
CREATE INDEX IF NOT EXISTS hop_off_date_idx ON hop_etl.off_source(tanggal,pegawai_id);
CREATE TABLE IF NOT EXISTS hop_etl.fact_days (
 tanggal date PRIMARY KEY,rows_written bigint NOT NULL,final_rows bigint NOT NULL,
 review_rows bigint NOT NULL,event_rows bigint NOT NULL,finished_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS hop_etl.employee_snapshot AS
 SELECT pegawai_id,pegawai_id_sumber,pegawai_key,departemen_id,departemen_id_sumber,departemen_key FROM public.dim_pegawai WITH NO DATA;
CREATE UNIQUE INDEX IF NOT EXISTS hop_employee_snapshot_pk ON hop_etl.employee_snapshot(pegawai_id);
CREATE TABLE IF NOT EXISTS hop_etl.shift_snapshot AS SELECT * FROM public.dim_shift WITH NO DATA;
CREATE UNIQUE INDEX IF NOT EXISTS hop_shift_snapshot_schedule ON hop_etl.shift_snapshot(jadwal_id_sumber);
CREATE TABLE IF NOT EXISTS hop_etl.calendar_snapshot AS SELECT * FROM public.dim_calendar WITH NO DATA;
CREATE UNIQUE INDEX IF NOT EXISTS hop_calendar_snapshot_date ON hop_etl.calendar_snapshot(tanggal);

CREATE TABLE IF NOT EXISTS hop_etl.event_rejects(id integer PRIMARY KEY,pegawai_id integer,reason text NOT NULL);
