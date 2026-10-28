--
-- PostgreSQL database dump
--

\restrict jDkJ5k1vkVwIU7LHb4gGWohXLf2Xf1GTXftJyjHvayOAfiYomrjtacQsTG9oyXt

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
-- PostgreSQL database dump complete
--

\unrestrict jDkJ5k1vkVwIU7LHb4gGWohXLf2Xf1GTXftJyjHvayOAfiYomrjtacQsTG9oyXt

