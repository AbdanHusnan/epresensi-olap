--
-- PostgreSQL database dump
--

\restrict TTJUPNDLqctXicFdRpfyKtJBxmnDyKxUXhKUxupI9Q2LWxkMtovZCYs54A69DjD

-- Dumped from database version 16.14 (Debian 16.14-1.pgdg13+1)
-- Dumped by pg_dump version 16.14 (Debian 16.14-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: curated; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA curated;


--
-- Name: raw; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA raw;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: cur_attendance_regular_daily; Type: TABLE; Schema: curated; Owner: -
--

CREATE TABLE curated.cur_attendance_regular_daily (
    pegawai_id integer NOT NULL,
    tanggal date NOT NULL,
    departemen_id integer,
    is_employee_active boolean,
    has_regular_schedule boolean,
    is_day_off boolean,
    is_expected_workday boolean,
    has_masuk boolean,
    has_pulang boolean,
    checkin_event_count integer,
    checkout_event_count integer,
    first_checkin_at timestamp without time zone,
    last_checkout_at timestamp without time zone,
    has_manual_event boolean,
    has_full_day_leave boolean,
    has_partial_day_leave boolean,
    selected_leave_coverage character varying(10),
    is_complete_attendance boolean,
    status_kehadiran character varying(30),
    is_late boolean,
    late_minutes integer,
    late_schedule_id_sumber integer,
    scheduled_regular_days integer,
    checkin_days integer,
    checkout_days integer,
    complete_attendance_days integer,
    leave_days integer,
    perlu_review boolean,
    alasan_review text,
    source_snapshot_at timestamp with time zone
);


--
-- Name: cur_employee_workday; Type: TABLE; Schema: curated; Owner: -
--

CREATE TABLE curated.cur_employee_workday (
    pegawai_id integer NOT NULL,
    tanggal date NOT NULL,
    departemen_id integer,
    is_employee_active boolean,
    has_regular_schedule boolean,
    candidate_regular_schedule_count integer,
    is_day_off boolean,
    is_expected_workday boolean,
    source_snapshot_at timestamp with time zone,
    source_updated_at timestamp without time zone
);


--
-- Name: cur_event_attendance; Type: TABLE; Schema: curated; Owner: -
--

CREATE TABLE curated.cur_event_attendance (
    checkinout_id_sumber integer NOT NULL,
    pegawai_id integer,
    tanggal_event date,
    waktu_event timestamp without time zone,
    checktype integer,
    departemen_id_event integer,
    jadwal_id_sumber integer,
    work_code_sumber integer,
    jam_masuk_sumber time without time zone,
    jam_keluar_sumber time without time zone,
    is_manual boolean,
    is_wfh_sumber smallint,
    event_updated_at timestamp without time zone,
    shift_id_sumber integer,
    nama_shift_snapshot character varying(200),
    is_regular_shift boolean,
    is_nonregular_shift boolean,
    event_type character varying(10),
    is_valid_event_type boolean,
    perlu_review boolean,
    alasan_review text,
    source_snapshot_at timestamp with time zone
);


--
-- Name: cur_leave_daily; Type: TABLE; Schema: curated; Owner: -
--

CREATE TABLE curated.cur_leave_daily (
    perizinan_id_sumber integer NOT NULL,
    pegawai_id integer NOT NULL,
    tanggal_izin date NOT NULL,
    departemen_id_izin integer,
    jenis_izin_id_sumber integer,
    nama_jenis_izin character varying(200),
    tipe_izin_id_sumber integer,
    nama_tipe_izin character varying(200),
    approval boolean,
    approval_at timestamp without time zone,
    is_full_day_leave boolean,
    is_partial_day_leave boolean,
    is_valid_leave boolean,
    perlu_review boolean,
    alasan_review text,
    source_updated_at timestamp without time zone,
    source_snapshot_at timestamp with time zone
);


--
-- Name: cur_nonregular_event_daily; Type: TABLE; Schema: curated; Owner: -
--

CREATE TABLE curated.cur_nonregular_event_daily (
    pegawai_id integer NOT NULL,
    tanggal_kerja date NOT NULL,
    jadwal_id_sumber integer NOT NULL,
    shift_id_sumber integer,
    departemen_id_event integer,
    has_masuk boolean,
    has_pulang boolean,
    checkin_event_count integer,
    checkout_event_count integer,
    first_checkin_at timestamp without time zone,
    last_checkout_at timestamp without time zone,
    has_manual_event boolean,
    mode_kerja_event smallint,
    is_complete_attendance boolean,
    perlu_review boolean,
    alasan_review text,
    source_snapshot_at timestamp with time zone
);


--
-- Name: cur_regular_event_daily; Type: TABLE; Schema: curated; Owner: -
--

CREATE TABLE curated.cur_regular_event_daily (
    pegawai_id integer NOT NULL,
    tanggal_kerja date NOT NULL,
    departemen_id_event integer,
    has_masuk boolean,
    has_pulang boolean,
    checkin_event_count integer,
    checkout_event_count integer,
    first_checkin_at timestamp without time zone,
    last_checkout_at timestamp without time zone,
    has_manual_event boolean,
    regular_schedule_count integer,
    is_complete_attendance boolean,
    perlu_review boolean,
    alasan_review text,
    source_snapshot_at timestamp with time zone
);


--
-- Name: ref_calendar; Type: TABLE; Schema: curated; Owner: -
--

CREATE TABLE curated.ref_calendar (
    tanggal date NOT NULL,
    is_weekend boolean NOT NULL,
    generated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: raw_checkinout; Type: TABLE; Schema: raw; Owner: -
--

CREATE TABLE raw.raw_checkinout (
    id integer NOT NULL,
    pegawai_id integer,
    latlong character varying(60),
    departemen integer,
    location integer,
    jarak double precision,
    checktype integer,
    imei character varying(50),
    approval boolean,
    approval_at timestamp without time zone,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    current_location text,
    ijin integer,
    keterangan text,
    file character varying(200),
    type_ijin boolean,
    deskripsi text,
    timezone character varying(500),
    is_wfh smallint,
    work_code integer,
    selisih_waktu time without time zone,
    jadwal_id integer,
    hari character varying(20),
    jam_masuk time without time zone,
    jam_keluar time without time zone,
    jam_masuk_awal time without time zone,
    jam_keluar_akhir time without time zone,
    flexible_time time without time zone,
    is_manual boolean,
    temp_current_location text,
    extracted_at timestamp with time zone NOT NULL,
    pipeline_run_id text NOT NULL
);


--
-- Name: raw_departemen; Type: TABLE; Schema: raw; Owner: -
--

CREATE TABLE raw.raw_departemen (
    id integer NOT NULL,
    kode character varying(40),
    nama_departemen character varying(200),
    parent integer,
    latlong character varying(200),
    created_at timestamp without time zone,
    address text,
    logo character varying(200),
    lokasi integer,
    logo_qr character varying(200),
    opd_parent integer,
    kode_lengkap text,
    "order" integer,
    is_remun integer,
    is_allow_wfh integer,
    unit_kerja_induk integer,
    is_using_wajah integer,
    upload_wajah integer,
    hari_senam character varying(10),
    extracted_at timestamp with time zone NOT NULL,
    pipeline_run_id text NOT NULL
);


--
-- Name: raw_hari_libur; Type: TABLE; Schema: raw; Owner: -
--

CREATE TABLE raw.raw_hari_libur (
    id integer NOT NULL,
    tanggal date,
    keterangan character varying(200),
    created_at timestamp without time zone,
    extracted_at timestamp with time zone NOT NULL,
    pipeline_run_id text NOT NULL
);


--
-- Name: raw_jadwal; Type: TABLE; Schema: raw; Owner: -
--

CREATE TABLE raw.raw_jadwal (
    id integer NOT NULL,
    jenis integer,
    hari character varying(200),
    jam_masuk time without time zone,
    jam_keluar time without time zone,
    created_at timestamp without time zone,
    jam_masuk_awal time without time zone,
    jam_keluar_akhir time without time zone,
    flexible_time time without time zone,
    extracted_at timestamp with time zone NOT NULL,
    pipeline_run_id text NOT NULL
);


--
-- Name: raw_jenis_ijin; Type: TABLE; Schema: raw; Owner: -
--

CREATE TABLE raw.raw_jenis_ijin (
    id integer NOT NULL,
    nama character varying(200),
    kode character varying(50),
    setengah_hari boolean,
    created_at timestamp without time zone,
    tipe_id integer,
    potongan character varying(5),
    is_aktif integer,
    label_kode character varying(100),
    extracted_at timestamp with time zone NOT NULL,
    pipeline_run_id text NOT NULL
);


--
-- Name: raw_libur_shift; Type: TABLE; Schema: raw; Owner: -
--

CREATE TABLE raw.raw_libur_shift (
    id integer NOT NULL,
    departemen_id integer,
    pegawai_id integer,
    tanggal date,
    keterangan character varying(200),
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by integer,
    extracted_at timestamp with time zone NOT NULL,
    pipeline_run_id text NOT NULL
);


--
-- Name: raw_pegawai; Type: TABLE; Schema: raw; Owner: -
--

CREATE TABLE raw.raw_pegawai (
    id integer NOT NULL,
    nip character varying(200),
    nama character varying(200),
    departemen integer,
    alamat text,
    jenis_kelamin integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    email character varying(100),
    foto character varying(200),
    jabatan character varying(200),
    status integer,
    qr_code text,
    unit_kerja_induk integer,
    status_shift integer,
    pangkat character varying(100),
    jenis_jabatan character varying(250),
    eselon character varying(250),
    other_attr character varying(10),
    kelas_jabatan character varying(10),
    nip_lama character varying(200),
    jenis_tpp integer,
    attrs text,
    is_foto_approved integer,
    extracted_at timestamp with time zone NOT NULL,
    pipeline_run_id text NOT NULL
);


--
-- Name: raw_perizinan; Type: TABLE; Schema: raw; Owner: -
--

CREATE TABLE raw.raw_perizinan (
    id integer NOT NULL,
    user_id integer,
    nama character varying(200),
    departemen integer,
    tipe_ijin integer,
    jenis_ijin integer,
    alasan text,
    berkas character varying(200),
    catatan text,
    approval boolean,
    approval_at timestamp without time zone,
    created_at timestamp without time zone,
    tgl_ijin date,
    tgl_ijin_sampai date,
    pegawai_id integer,
    updated_at timestamp without time zone,
    status smallint,
    updated_user integer,
    latlong character varying(60),
    tgl_emaster date,
    extracted_at timestamp with time zone NOT NULL,
    pipeline_run_id text NOT NULL
);


--
-- Name: raw_shift; Type: TABLE; Schema: raw; Owner: -
--

CREATE TABLE raw.raw_shift (
    id integer NOT NULL,
    nama character varying(200),
    status boolean,
    departemen_id integer,
    created_at timestamp without time zone,
    created_by integer,
    event_id integer,
    is_flexible integer,
    extracted_at timestamp with time zone NOT NULL,
    pipeline_run_id text NOT NULL
);


--
-- Name: raw_tipe_ijin; Type: TABLE; Schema: raw; Owner: -
--

CREATE TABLE raw.raw_tipe_ijin (
    id integer NOT NULL,
    nama character varying(200),
    tipe character varying(10),
    extracted_at timestamp with time zone NOT NULL,
    pipeline_run_id text NOT NULL
);


--
-- Name: raw_user; Type: TABLE; Schema: raw; Owner: -
--

CREATE TABLE raw.raw_user (
    id integer NOT NULL,
    pegawai_id integer,
    extracted_at timestamp with time zone NOT NULL,
    pipeline_run_id text NOT NULL
);


--
-- Name: cur_attendance_regular_daily cur_attendance_regular_daily_pkey; Type: CONSTRAINT; Schema: curated; Owner: -
--

ALTER TABLE ONLY curated.cur_attendance_regular_daily
    ADD CONSTRAINT cur_attendance_regular_daily_pkey PRIMARY KEY (pegawai_id, tanggal);


--
-- Name: cur_employee_workday cur_employee_workday_pkey; Type: CONSTRAINT; Schema: curated; Owner: -
--

ALTER TABLE ONLY curated.cur_employee_workday
    ADD CONSTRAINT cur_employee_workday_pkey PRIMARY KEY (pegawai_id, tanggal);


--
-- Name: cur_event_attendance cur_event_attendance_pkey; Type: CONSTRAINT; Schema: curated; Owner: -
--

ALTER TABLE ONLY curated.cur_event_attendance
    ADD CONSTRAINT cur_event_attendance_pkey PRIMARY KEY (checkinout_id_sumber);


--
-- Name: cur_leave_daily cur_leave_daily_pkey; Type: CONSTRAINT; Schema: curated; Owner: -
--

ALTER TABLE ONLY curated.cur_leave_daily
    ADD CONSTRAINT cur_leave_daily_pkey PRIMARY KEY (perizinan_id_sumber, pegawai_id, tanggal_izin);


--
-- Name: cur_nonregular_event_daily cur_nonregular_event_daily_pkey; Type: CONSTRAINT; Schema: curated; Owner: -
--

ALTER TABLE ONLY curated.cur_nonregular_event_daily
    ADD CONSTRAINT cur_nonregular_event_daily_pkey PRIMARY KEY (pegawai_id, tanggal_kerja, jadwal_id_sumber);


--
-- Name: cur_regular_event_daily cur_regular_event_daily_pkey; Type: CONSTRAINT; Schema: curated; Owner: -
--

ALTER TABLE ONLY curated.cur_regular_event_daily
    ADD CONSTRAINT cur_regular_event_daily_pkey PRIMARY KEY (pegawai_id, tanggal_kerja);


--
-- Name: ref_calendar ref_calendar_pkey; Type: CONSTRAINT; Schema: curated; Owner: -
--

ALTER TABLE ONLY curated.ref_calendar
    ADD CONSTRAINT ref_calendar_pkey PRIMARY KEY (tanggal);


--
-- Name: raw_jenis_ijin raw_jenis_ijin_pkey; Type: CONSTRAINT; Schema: raw; Owner: -
--

ALTER TABLE ONLY raw.raw_jenis_ijin
    ADD CONSTRAINT raw_jenis_ijin_pkey PRIMARY KEY (id);


--
-- Name: raw_departemen raw_m_departemen_pkey; Type: CONSTRAINT; Schema: raw; Owner: -
--

ALTER TABLE ONLY raw.raw_departemen
    ADD CONSTRAINT raw_m_departemen_pkey PRIMARY KEY (id);


--
-- Name: raw_hari_libur raw_m_hari_libur_pkey; Type: CONSTRAINT; Schema: raw; Owner: -
--

ALTER TABLE ONLY raw.raw_hari_libur
    ADD CONSTRAINT raw_m_hari_libur_pkey PRIMARY KEY (id);


--
-- Name: raw_jadwal raw_m_jadwal_pkey; Type: CONSTRAINT; Schema: raw; Owner: -
--

ALTER TABLE ONLY raw.raw_jadwal
    ADD CONSTRAINT raw_m_jadwal_pkey PRIMARY KEY (id);


--
-- Name: raw_pegawai raw_m_pegawai_pkey; Type: CONSTRAINT; Schema: raw; Owner: -
--

ALTER TABLE ONLY raw.raw_pegawai
    ADD CONSTRAINT raw_m_pegawai_pkey PRIMARY KEY (id);


--
-- Name: raw_shift raw_m_shift_pkey; Type: CONSTRAINT; Schema: raw; Owner: -
--

ALTER TABLE ONLY raw.raw_shift
    ADD CONSTRAINT raw_m_shift_pkey PRIMARY KEY (id);


--
-- Name: raw_checkinout raw_t_checkinout_pkey; Type: CONSTRAINT; Schema: raw; Owner: -
--

ALTER TABLE ONLY raw.raw_checkinout
    ADD CONSTRAINT raw_t_checkinout_pkey PRIMARY KEY (id);


--
-- Name: raw_libur_shift raw_t_libur_shift_pkey; Type: CONSTRAINT; Schema: raw; Owner: -
--

ALTER TABLE ONLY raw.raw_libur_shift
    ADD CONSTRAINT raw_t_libur_shift_pkey PRIMARY KEY (id);


--
-- Name: raw_perizinan raw_t_perizinan_pkey; Type: CONSTRAINT; Schema: raw; Owner: -
--

ALTER TABLE ONLY raw.raw_perizinan
    ADD CONSTRAINT raw_t_perizinan_pkey PRIMARY KEY (id);


--
-- Name: raw_tipe_ijin raw_tipe_ijin_pkey; Type: CONSTRAINT; Schema: raw; Owner: -
--

ALTER TABLE ONLY raw.raw_tipe_ijin
    ADD CONSTRAINT raw_tipe_ijin_pkey PRIMARY KEY (id);


--
-- Name: raw_user raw_user_pkey; Type: CONSTRAINT; Schema: raw; Owner: -
--

ALTER TABLE ONLY raw.raw_user
    ADD CONSTRAINT raw_user_pkey PRIMARY KEY (id);


--
-- Name: raw_checkinout_created_at_brin; Type: INDEX; Schema: raw; Owner: -
--

CREATE INDEX raw_checkinout_created_at_brin ON raw.raw_checkinout USING brin (created_at) WITH (pages_per_range='128');


--
-- PostgreSQL database dump complete
--

\unrestrict TTJUPNDLqctXicFdRpfyKtJBxmnDyKxUXhKUxupI9Q2LWxkMtovZCYs54A69DjD

