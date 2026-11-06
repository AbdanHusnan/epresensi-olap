--
-- PostgreSQL database dump
--

\restrict EV2ToM9f72euz9Ul8Noghfo14j8Pc3dZdmPGdagGKpN44YUijdJ7qdzhFtPWw78

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
-- Name: audit; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA audit;


--
-- Name: SCHEMA audit; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA audit IS 'Out-of-table audit/history logging tables and trigger functions';


--
-- Name: test_curated_v2_20261028; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA test_curated_v2_20261028;


--
-- Name: test_e2e_20261027; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA test_e2e_20261027;


--
-- Name: test_source_dashboard_20261030; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA test_source_dashboard_20261030;


--
-- Name: topology; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA topology;


--
-- Name: SCHEMA topology; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA topology IS 'PostGIS Topology schema';


--
-- Name: hstore; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS hstore WITH SCHEMA public;


--
-- Name: EXTENSION hstore; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION hstore IS 'data type for storing sets of (key, value) pairs';


--
-- Name: audit_table(regclass); Type: FUNCTION; Schema: audit; Owner: -
--

CREATE FUNCTION audit.audit_table(target_table regclass) RETURNS void
    LANGUAGE sql
    AS $_$
SELECT audit.audit_table($1, BOOLEAN 't', BOOLEAN 't');
$_$;


--
-- Name: FUNCTION audit_table(target_table regclass); Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON FUNCTION audit.audit_table(target_table regclass) IS '
Add auditing support to the given table. Row-level changes will be logged with full client query text. No cols are ignored.
';


--
-- Name: audit_table(regclass, boolean, boolean); Type: FUNCTION; Schema: audit; Owner: -
--

CREATE FUNCTION audit.audit_table(target_table regclass, audit_rows boolean, audit_query_text boolean) RETURNS void
    LANGUAGE sql
    AS $_$
SELECT audit.audit_table($1, $2, $3, ARRAY[]::text[]);
$_$;


--
-- Name: audit_table(regclass, boolean, boolean, text[]); Type: FUNCTION; Schema: audit; Owner: -
--

CREATE FUNCTION audit.audit_table(target_table regclass, audit_rows boolean, audit_query_text boolean, ignored_cols text[]) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
  stm_targets text = 'INSERT OR UPDATE OR DELETE OR TRUNCATE';
  _q_txt text;
  _ignored_cols_snip text = '';
BEGIN
    EXECUTE 'DROP TRIGGER IF EXISTS audit_trigger_row ON ' || target_table;
    EXECUTE 'DROP TRIGGER IF EXISTS audit_trigger_stm ON ' || target_table;

    IF audit_rows THEN
        IF array_length(ignored_cols,1) > 0 THEN
            _ignored_cols_snip = ', ' || quote_literal(ignored_cols);
        END IF;
        _q_txt = 'CREATE TRIGGER audit_trigger_row AFTER INSERT OR UPDATE OR DELETE ON ' || 
                 target_table || 
                 ' FOR EACH ROW EXECUTE PROCEDURE audit.if_modified_func(' ||
                 quote_literal(audit_query_text) || _ignored_cols_snip || ');';
        RAISE NOTICE '%',_q_txt;
        EXECUTE _q_txt;
        stm_targets = 'TRUNCATE';
    ELSE
    END IF;

    _q_txt = 'CREATE TRIGGER audit_trigger_stm AFTER ' || stm_targets || ' ON ' ||
             target_table ||
             ' FOR EACH STATEMENT EXECUTE PROCEDURE audit.if_modified_func('||
             quote_literal(audit_query_text) || ');';
    RAISE NOTICE '%',_q_txt;
    EXECUTE _q_txt;

END;
$$;


--
-- Name: FUNCTION audit_table(target_table regclass, audit_rows boolean, audit_query_text boolean, ignored_cols text[]); Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON FUNCTION audit.audit_table(target_table regclass, audit_rows boolean, audit_query_text boolean, ignored_cols text[]) IS '
Add auditing support to a table.

Arguments:
   target_table:     Table name, schema qualified if not on search_path
   audit_rows:       Record each row change, or only audit at a statement level
   audit_query_text: Record the text of the client query that triggered the audit event?
   ignored_cols:     Columns to exclude from update diffs, ignore updates that change only ignored cols.
';


--
-- Name: if_modified_func(); Type: FUNCTION; Schema: audit; Owner: -
--

CREATE FUNCTION audit.if_modified_func() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE
    audit_row audit.logged_actions;
    include_values boolean;
    log_diffs boolean;
    h_old hstore;
    h_new hstore;
    excluded_cols text[] = ARRAY[]::text[];
BEGIN
    IF TG_WHEN <> 'AFTER' THEN
        RAISE EXCEPTION 'audit.if_modified_func() may only run as an AFTER trigger';
    END IF;

    audit_row = ROW(
        nextval('audit.logged_actions_event_id_seq'), -- event_id
        TG_TABLE_SCHEMA::text,                        -- schema_name
        TG_TABLE_NAME::text,                          -- table_name
        TG_RELID,                                     -- relation OID for much quicker searches
        session_user::text,                           -- session_user_name
        current_timestamp,                            -- action_tstamp_tx
        statement_timestamp(),                        -- action_tstamp_stm
        clock_timestamp(),                            -- action_tstamp_clk
        txid_current(),                               -- transaction ID
        current_setting('application_name'),          -- client application
        inet_client_addr(),                           -- client_addr
        inet_client_port(),                           -- client_port
        current_query(),                              -- top-level query or queries (if multistatement) from client
        substring(TG_OP,1,1),                         -- action
        NULL, NULL,                                   -- row_data, changed_fields
        'f'                                           -- statement_only
        );

    IF NOT TG_ARGV[0]::boolean IS DISTINCT FROM 'f'::boolean THEN
        audit_row.client_query = NULL;
    END IF;

    IF TG_ARGV[1] IS NOT NULL THEN
        excluded_cols = TG_ARGV[1]::text[];
    END IF;
    
    IF (TG_OP = 'UPDATE' AND TG_LEVEL = 'ROW') THEN
        audit_row.row_data = hstore(OLD.*) - excluded_cols;
        audit_row.changed_fields =  (hstore(NEW.*) - audit_row.row_data) - excluded_cols;
        IF audit_row.changed_fields = hstore('') THEN
            -- All changed fields are ignored. Skip this update.
            RETURN NULL;
        END IF;
    ELSIF (TG_OP = 'DELETE' AND TG_LEVEL = 'ROW') THEN
        audit_row.row_data = hstore(OLD.*) - excluded_cols;
    ELSIF (TG_OP = 'INSERT' AND TG_LEVEL = 'ROW') THEN
        audit_row.row_data = hstore(NEW.*) - excluded_cols;
    ELSIF (TG_LEVEL = 'STATEMENT' AND TG_OP IN ('INSERT','UPDATE','DELETE','TRUNCATE')) THEN
        audit_row.statement_only = 't';
    ELSE
        RAISE EXCEPTION '[audit.if_modified_func] - Trigger func added as trigger for unhandled case: %, %',TG_OP, TG_LEVEL;
        RETURN NULL;
    END IF;
    INSERT INTO audit.logged_actions VALUES (audit_row.*);
    RETURN NULL;
END;
$$;


--
-- Name: FUNCTION if_modified_func(); Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON FUNCTION audit.if_modified_func() IS '
Track changes to a table at the statement and/or row level.

Optional parameters to trigger in CREATE TRIGGER call:

param 0: boolean, whether to log the query text. Default ''t''.

param 1: text[], columns to ignore in updates. Default [].

         Updates to ignored cols are omitted from changed_fields.

         Updates with only ignored cols changed are not inserted
         into the audit log.

         Almost all the processing work is still done for updates
         that ignored. If you need to save the load, you need to use
         WHEN clause on the trigger instead.

         No warning or error is issued if ignored_cols contains columns
         that do not exist in the target table. This lets you specify
         a standard set of ignored columns.

There is no parameter to disable logging of values. Add this trigger as
a ''FOR EACH STATEMENT'' rather than ''FOR EACH ROW'' trigger if you do not
want to log row values.

Note that the user name logged is the login role for the session. The audit trigger
cannot obtain the active role because it is reset by the SECURITY DEFINER invocation
of the audit trigger its self.
';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: logged_actions; Type: TABLE; Schema: audit; Owner: -
--

CREATE TABLE audit.logged_actions (
    event_id bigint NOT NULL,
    schema_name text NOT NULL,
    table_name text NOT NULL,
    relid oid NOT NULL,
    session_user_name text,
    action_tstamp_tx timestamp with time zone NOT NULL,
    action_tstamp_stm timestamp with time zone NOT NULL,
    action_tstamp_clk timestamp with time zone NOT NULL,
    transaction_id bigint,
    application_name text,
    client_addr inet,
    client_port integer,
    client_query text,
    action text NOT NULL,
    row_data public.hstore,
    changed_fields public.hstore,
    statement_only boolean NOT NULL,
    CONSTRAINT logged_actions_action_check CHECK ((action = ANY (ARRAY['I'::text, 'D'::text, 'U'::text, 'T'::text])))
);


--
-- Name: TABLE logged_actions; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON TABLE audit.logged_actions IS 'History of auditable actions on audited tables, from audit.if_modified_func()';


--
-- Name: COLUMN logged_actions.event_id; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.event_id IS 'Unique identifier for each auditable event';


--
-- Name: COLUMN logged_actions.schema_name; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.schema_name IS 'Database schema audited table for this event is in';


--
-- Name: COLUMN logged_actions.table_name; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.table_name IS 'Non-schema-qualified table name of table event occured in';


--
-- Name: COLUMN logged_actions.relid; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.relid IS 'Table OID. Changes with drop/create. Get with ''tablename''::regclass';


--
-- Name: COLUMN logged_actions.session_user_name; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.session_user_name IS 'Login / session user whose statement caused the audited event';


--
-- Name: COLUMN logged_actions.action_tstamp_tx; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.action_tstamp_tx IS 'Transaction start timestamp for tx in which audited event occurred';


--
-- Name: COLUMN logged_actions.action_tstamp_stm; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.action_tstamp_stm IS 'Statement start timestamp for tx in which audited event occurred';


--
-- Name: COLUMN logged_actions.action_tstamp_clk; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.action_tstamp_clk IS 'Wall clock time at which audited event''s trigger call occurred';


--
-- Name: COLUMN logged_actions.transaction_id; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.transaction_id IS 'Identifier of transaction that made the change. May wrap, but unique paired with action_tstamp_tx.';


--
-- Name: COLUMN logged_actions.application_name; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.application_name IS 'Application name set when this audit event occurred. Can be changed in-session by client.';


--
-- Name: COLUMN logged_actions.client_addr; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.client_addr IS 'IP address of client that issued query. Null for unix domain socket.';


--
-- Name: COLUMN logged_actions.client_port; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.client_port IS 'Remote peer IP port address of client that issued query. Undefined for unix socket.';


--
-- Name: COLUMN logged_actions.client_query; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.client_query IS 'Top-level query that caused this auditable event. May be more than one statement.';


--
-- Name: COLUMN logged_actions.action; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.action IS 'Action type; I = insert, D = delete, U = update, T = truncate';


--
-- Name: COLUMN logged_actions.row_data; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.row_data IS 'Record value. Null for statement-level trigger. For INSERT this is the new tuple. For DELETE and UPDATE it is the old tuple.';


--
-- Name: COLUMN logged_actions.changed_fields; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.changed_fields IS 'New values of fields changed by UPDATE. Null except for row-level UPDATE events.';


--
-- Name: COLUMN logged_actions.statement_only; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON COLUMN audit.logged_actions.statement_only IS '''t'' if audit event is from an FOR EACH STATEMENT trigger, ''f'' for FOR EACH ROW';


--
-- Name: logged_actions_event_id_seq; Type: SEQUENCE; Schema: audit; Owner: -
--

CREATE SEQUENCE audit.logged_actions_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: logged_actions_event_id_seq; Type: SEQUENCE OWNED BY; Schema: audit; Owner: -
--

ALTER SEQUENCE audit.logged_actions_event_id_seq OWNED BY audit.logged_actions.event_id;


--
-- Name: tableslist; Type: VIEW; Schema: audit; Owner: -
--

CREATE VIEW audit.tableslist AS
 SELECT DISTINCT trigger_schema AS schema,
    event_object_table AS auditedtable
   FROM information_schema.triggers
  WHERE ((trigger_name)::text = ANY (ARRAY['audit_trigger_row'::text, 'audit_trigger_stm'::text]))
  ORDER BY trigger_schema, event_object_table;


--
-- Name: VIEW tableslist; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON VIEW audit.tableslist IS '
View showing all tables with auditing set up. Ordered by schema, then table.
';


--
-- Name: jabatan_pengurus_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.jabatan_pengurus_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: jenis_anggota_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.jenis_anggota_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: kecamatan_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.kecamatan_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: kecamatan; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kecamatan (
    id integer DEFAULT nextval('public.kecamatan_id_seq'::regclass) NOT NULL,
    kota_id integer,
    kode integer,
    nama character varying(100),
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: kelurahan_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.kelurahan_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: kelurahan; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kelurahan (
    id integer DEFAULT nextval('public.kelurahan_id_seq'::regclass) NOT NULL,
    kec_id integer,
    kode_kel bigint,
    nama_kel character varying(100),
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: lembaga_partai_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.lembaga_partai_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_departemen; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_departemen (
    id integer NOT NULL,
    kode character varying(40),
    nama_departemen character varying(200),
    parent integer DEFAULT 0,
    latlong character varying(200),
    created_at timestamp without time zone,
    address text,
    logo character varying(200),
    lokasi integer,
    logo_qr character varying(200),
    opd_parent integer,
    kode_lengkap text,
    "order" integer,
    is_remun integer DEFAULT 0,
    is_allow_wfh integer DEFAULT 0,
    unit_kerja_induk integer,
    is_using_wajah integer DEFAULT 0,
    upload_wajah integer,
    hari_senam character varying(10) DEFAULT 'wed'::character varying
);


--
-- Name: m_departemen_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_departemen_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_departemen_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.m_departemen_id_seq OWNED BY public.m_departemen.id;


--
-- Name: m_departemen_temp_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_departemen_temp_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_disiplin; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_disiplin (
    id integer NOT NULL,
    kode character varying(10),
    nama character varying(100),
    presentase double precision,
    keterangan character varying(200),
    hari character varying(5),
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: m_disiplin_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_disiplin_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_disiplin_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.m_disiplin_id_seq OWNED BY public.m_disiplin.id;


--
-- Name: m_disiplin_libur; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_disiplin_libur (
    id integer NOT NULL,
    departemen_id integer,
    disiplin_id integer,
    tanggal date,
    keterangan character varying(200),
    status integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by integer,
    updated_by integer
);


--
-- Name: m_disiplin_libur_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_disiplin_libur_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_disiplin_libur_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.m_disiplin_libur_id_seq OWNED BY public.m_disiplin_libur.id;


--
-- Name: m_gol_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_gol_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_gol; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_gol (
    id integer DEFAULT nextval('public.m_gol_id_seq'::regclass) NOT NULL,
    urutan integer,
    kelas_jabatan integer,
    jabatan character varying(800),
    golongan character varying(200),
    eselon character varying(200),
    tunjangan double precision,
    lembur double precision,
    pph21 double precision
);


--
-- Name: m_group_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_group_id_seq
    START WITH 2
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_group; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_group (
    id integer DEFAULT nextval('public.m_group_id_seq'::regclass) NOT NULL,
    group_name character varying(50),
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    description text
);


--
-- Name: m_hari_libur_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_hari_libur_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_hari_libur; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_hari_libur (
    id integer DEFAULT nextval('public.m_hari_libur_id_seq'::regclass) NOT NULL,
    tanggal date NOT NULL,
    keterangan character varying(200),
    created_at timestamp without time zone
);


--
-- Name: m_ip; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_ip (
    id integer NOT NULL,
    ip character varying(30),
    nama character varying(100),
    deksripsi text,
    updated_at timestamp without time zone
);


--
-- Name: m_ip_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_ip_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_ip_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.m_ip_id_seq OWNED BY public.m_ip.id;


--
-- Name: m_jadwal_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_jadwal_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_jadwal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_jadwal (
    id integer DEFAULT nextval('public.m_jadwal_id_seq'::regclass) NOT NULL,
    jenis integer NOT NULL,
    hari character varying(200) NOT NULL,
    jam_masuk time without time zone NOT NULL,
    jam_keluar time without time zone NOT NULL,
    created_at timestamp without time zone,
    jam_masuk_awal time without time zone NOT NULL,
    jam_keluar_akhir time without time zone NOT NULL,
    flexible_time time without time zone
);


--
-- Name: m_jenis_ijin; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_jenis_ijin (
    id integer NOT NULL,
    nama character varying(200) NOT NULL,
    kode character varying(50),
    setengah_hari boolean DEFAULT false,
    created_at timestamp without time zone,
    tipe_id integer,
    potongan character varying(5),
    is_aktif integer DEFAULT 1,
    label_kode character varying(100)
);


--
-- Name: m_jenis_ijin_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_jenis_ijin_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_jenis_ijin_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.m_jenis_ijin_id_seq OWNED BY public.m_jenis_ijin.id;


--
-- Name: m_kota_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_kota_id_seq
    START WITH 39
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_kota; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_kota (
    id integer DEFAULT nextval('public.m_kota_id_seq'::regclass) NOT NULL,
    id_propinsi integer NOT NULL,
    kode character varying(5),
    kota character varying(45) NOT NULL
);


--
-- Name: m_lokasi; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_lokasi (
    id integer NOT NULL,
    nama character varying(200) NOT NULL,
    latlong character varying(200) NOT NULL,
    radius integer,
    address text,
    deskripsi text,
    created_at timestamp without time zone,
    departemen_id integer,
    dept_id integer,
    dept_kode character varying,
    is_valid integer DEFAULT 1,
    created_by character varying(200),
    updated_by character varying(200),
    updated_at timestamp without time zone
);


--
-- Name: m_lokasi_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_lokasi_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_lokasi_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.m_lokasi_id_seq OWNED BY public.m_lokasi.id;


--
-- Name: m_module_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_module_id_seq
    START WITH 35
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_module; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_module (
    id integer DEFAULT nextval('public.m_module_id_seq'::regclass) NOT NULL,
    module_name character varying(50),
    url character varying(100),
    parent integer,
    row_number integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    icon character varying(100)
);


--
-- Name: m_negara_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_negara_id_seq
    START WITH 315
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_negara; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_negara (
    id integer DEFAULT nextval('public.m_negara_id_seq'::regclass) NOT NULL,
    negara character varying(45) NOT NULL
);


--
-- Name: m_pegawai; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_pegawai (
    id integer NOT NULL,
    nip character varying(200) NOT NULL,
    nama character varying(200) NOT NULL,
    departemen integer NOT NULL,
    alamat text,
    jenis_kelamin integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    email character varying(100),
    foto character varying(200),
    jabatan character varying(200),
    status integer DEFAULT 1,
    qr_code text,
    unit_kerja_induk integer,
    status_shift integer DEFAULT 5,
    pangkat character varying(100),
    jenis_jabatan character varying(250),
    eselon character varying(250),
    other_attr character varying(10),
    kelas_jabatan character varying(10),
    nip_lama character varying(200),
    jenis_tpp integer,
    attrs text,
    is_foto_approved integer DEFAULT 0
);


--
-- Name: m_pegawai_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_pegawai_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_pegawai_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.m_pegawai_id_seq OWNED BY public.m_pegawai.id;


--
-- Name: m_pengaturan_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_pengaturan_id_seq
    START WITH 2
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_pengaturan; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_pengaturan (
    id integer DEFAULT nextval('public.m_pengaturan_id_seq'::regclass) NOT NULL,
    nama_aplikasi character varying(100),
    alamat text,
    kota_id integer,
    keterangan text,
    copyright character varying(100),
    create_at timestamp without time zone,
    update_at timestamp without time zone
);


--
-- Name: m_phone; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_phone (
    id integer NOT NULL,
    agent character varying(255),
    kode character varying(100),
    merk character varying(100),
    jenis character varying(100),
    android character varying(100)
);


--
-- Name: m_phone_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_phone_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_phone_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.m_phone_id_seq OWNED BY public.m_phone.id;


--
-- Name: m_previleges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_previleges (
    id integer NOT NULL,
    previleges character varying NOT NULL
);


--
-- Name: m_previleges_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_previleges_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_previleges_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.m_previleges_id_seq OWNED BY public.m_previleges.id;


--
-- Name: m_propinsi_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_propinsi_id_seq
    START WITH 35
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_propinsi; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_propinsi (
    id integer DEFAULT nextval('public.m_propinsi_id_seq'::regclass) NOT NULL,
    id_negara integer NOT NULL,
    propinsi character varying(45) NOT NULL
);


--
-- Name: m_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_rules_id_seq
    START WITH 67
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_rules (
    id integer DEFAULT nextval('public.m_rules_id_seq'::regclass) NOT NULL,
    module_id integer,
    group_id integer,
    is_read integer,
    is_add integer,
    is_edit integer,
    is_delete integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: m_shift_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_shift_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_shift; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_shift (
    id integer DEFAULT nextval('public.m_shift_id_seq'::regclass) NOT NULL,
    nama character varying(200) NOT NULL,
    status boolean DEFAULT true,
    departemen_id integer,
    created_at timestamp without time zone,
    created_by integer,
    event_id integer,
    is_flexible integer DEFAULT 0
);


--
-- Name: m_tipe_ijin; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_tipe_ijin (
    id integer NOT NULL,
    nama character varying(200) NOT NULL,
    tipe character varying(10) DEFAULT '[1, 2, 3]'::character varying
);


--
-- Name: m_tipe_ijin_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_tipe_ijin_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_tipe_ijin_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.m_tipe_ijin_id_seq OWNED BY public.m_tipe_ijin.id;


--
-- Name: m_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.m_user_id_seq
    START WITH 2
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: m_user; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.m_user (
    id integer DEFAULT nextval('public.m_user_id_seq'::regclass) NOT NULL,
    email character varying(100) NOT NULL,
    salt character varying(100),
    password character varying(100),
    nama character varying(100) NOT NULL,
    is_login integer,
    last_login timestamp without time zone,
    deskripsi text,
    is_active boolean DEFAULT true,
    group_id integer,
    api_key character varying(400),
    imei character varying(50),
    latlong character varying(400),
    last_latlong character varying(400),
    pegawai_id integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    last_activity character varying(200),
    last_activity_at timestamp without time zone,
    fcm_web text,
    fcm_mobile text,
    unit_kerja integer,
    msg_id character varying(100),
    msg_token text,
    created_by character varying(100),
    updated_by character varying(100),
    ip character varying(50),
    versi character(50)
);


--
-- Name: mobile_service; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mobile_service (
    id integer NOT NULL,
    object character varying(200) NOT NULL,
    param text,
    deskripsi text
);


--
-- Name: mobile_service_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.mobile_service_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mobile_service_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.mobile_service_id_seq OWNED BY public.mobile_service.id;


--
-- Name: r_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.r_log (
    id integer NOT NULL,
    users character varying(200),
    created_at timestamp without time zone,
    modul character varying(200),
    isi text,
    action character varying(50),
    request text,
    agent text,
    userid character varying(11),
    result text,
    user_id integer,
    ip character varying(50),
    server character varying(50)
);


--
-- Name: r_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.r_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: r_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.r_log_id_seq OWNED BY public.r_log.id;


--
-- Name: r_log_web; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.r_log_web (
    id integer NOT NULL,
    "user" character varying,
    modul character varying,
    action integer,
    ref_id integer,
    created_at timestamp without time zone
);


--
-- Name: r_log_web_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.r_log_web_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: r_log_web_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.r_log_web_id_seq OWNED BY public.r_log_web.id;


--
-- Name: r_update_nip; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.r_update_nip (
    id integer NOT NULL,
    nip_lama character varying(100),
    nip_baru character varying(100),
    updated_at timestamp without time zone,
    nama character varying(250),
    is_eksekusi integer DEFAULT 0
);


--
-- Name: r_update_nip_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.r_update_nip_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: r_update_nip_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.r_update_nip_id_seq OWNED BY public.r_update_nip.id;


--
-- Name: segmen_anggota_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.segmen_anggota_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: t_cctv_recog; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.t_cctv_recog (
    id integer NOT NULL,
    pegawai_id integer,
    nama character varying(200),
    nip character varying(50),
    unit_kerja text,
    tipe_absen integer,
    waktu_absen timestamp without time zone,
    device character varying(200),
    evidence character varying(200),
    kecocokan integer,
    validasi boolean DEFAULT false,
    validasi_at timestamp without time zone,
    validasi_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    unit_kerja_id integer,
    tipe_ijin_id integer
);


--
-- Name: t_cctv_recog_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.t_cctv_recog_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: t_cctv_recog_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.t_cctv_recog_id_seq OWNED BY public.t_cctv_recog.id;


--
-- Name: t_checkinout_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.t_checkinout_id_seq
    START WITH 9471041
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: t_checkinout; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.t_checkinout (
    id integer DEFAULT nextval('public.t_checkinout_id_seq'::regclass) NOT NULL,
    pegawai_id integer NOT NULL,
    latlong character varying(60),
    departemen integer,
    location integer,
    jarak double precision,
    checktype integer,
    imei character varying(50),
    approval boolean DEFAULT false,
    approval_at timestamp without time zone,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    current_location text,
    ijin integer,
    keterangan text,
    file character varying(200),
    type_ijin boolean DEFAULT false,
    deskripsi text,
    timezone character varying(500),
    is_wfh smallint DEFAULT '0'::smallint,
    work_code integer NOT NULL,
    selisih_waktu time without time zone,
    jadwal_id integer,
    hari character varying(20),
    jam_masuk time without time zone,
    jam_keluar time without time zone,
    jam_masuk_awal time without time zone,
    jam_keluar_akhir time without time zone,
    flexible_time time without time zone,
    is_manual boolean DEFAULT false,
    temp_current_location text
);


--
-- Name: t_libur_shift_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.t_libur_shift_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


--
-- Name: t_libur_shift; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.t_libur_shift (
    id integer DEFAULT nextval('public.t_libur_shift_id_seq'::regclass) NOT NULL,
    departemen_id integer,
    pegawai_id integer,
    tanggal date,
    keterangan character varying(200),
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by integer
);


--
-- Name: t_log_jadwal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.t_log_jadwal (
    id integer NOT NULL,
    jenis integer NOT NULL,
    log text NOT NULL,
    created_at timestamp without time zone
);


--
-- Name: t_log_lokasipegawai; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.t_log_lokasipegawai (
    id integer NOT NULL,
    pegawai_id integer,
    tanggal date,
    jam time without time zone,
    latlong character varying(200),
    imei character varying(50),
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    departemen_id integer
);


--
-- Name: t_log_lokasipegawai_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.t_log_lokasipegawai_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: t_log_lokasipegawai_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.t_log_lokasipegawai_id_seq OWNED BY public.t_log_lokasipegawai.id;


--
-- Name: t_log_pegawai_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.t_log_pegawai_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


--
-- Name: t_log_pegawai; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.t_log_pegawai (
    id integer DEFAULT nextval('public.t_log_pegawai_id_seq'::regclass) NOT NULL,
    user_id integer NOT NULL,
    nip character varying(50) NOT NULL,
    pegawai_id integer NOT NULL,
    nama character varying(500) NOT NULL,
    satuan_kerja integer NOT NULL,
    imei character varying(50) NOT NULL,
    latlong character varying(400),
    created_at timestamp without time zone,
    agent text,
    api_key text,
    lampiran character varying(300),
    verified boolean DEFAULT false,
    reff_kode character varying(50),
    versi integer
);


--
-- Name: COLUMN t_log_pegawai.verified; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.t_log_pegawai.verified IS 'verifkasi jadi true ketika foto profile approve';


--
-- Name: t_pegawai_lokasi; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.t_pegawai_lokasi (
    id integer NOT NULL,
    pegawai integer,
    lokasi integer,
    hari text,
    tanggal_from date,
    tanggal_to date,
    deskripsi text,
    created_at timestamp without time zone,
    aktif boolean DEFAULT true,
    departemen_id integer,
    is_event integer,
    created_by character varying(200),
    updated_by character varying(200),
    updated_at timestamp without time zone,
    is_prioritas integer DEFAULT 0
);


--
-- Name: t_pegawai_lokasi_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.t_pegawai_lokasi_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: t_pegawai_lokasi_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.t_pegawai_lokasi_id_seq OWNED BY public.t_pegawai_lokasi.id;


--
-- Name: t_perizinan; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.t_perizinan (
    id integer NOT NULL,
    user_id integer NOT NULL,
    nama character varying(200) NOT NULL,
    departemen integer NOT NULL,
    tipe_ijin integer NOT NULL,
    jenis_ijin integer NOT NULL,
    alasan text NOT NULL,
    berkas character varying(200),
    catatan text,
    approval boolean DEFAULT false,
    approval_at timestamp without time zone,
    created_at timestamp without time zone,
    tgl_ijin date NOT NULL,
    tgl_ijin_sampai date,
    pegawai_id integer,
    updated_at timestamp without time zone,
    status smallint DEFAULT '1'::smallint,
    updated_user integer,
    latlong character varying(60),
    tgl_emaster date
);


--
-- Name: t_perizinan_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.t_perizinan_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: t_perizinan_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.t_perizinan_id_seq OWNED BY public.t_perizinan.id;


--
-- Name: t_posting; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.t_posting (
    id integer NOT NULL,
    departemen integer NOT NULL,
    tanggal character varying(200) NOT NULL,
    json text,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    ijin text,
    created_user integer,
    keterangan text
);


--
-- Name: t_posting_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.t_posting_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: t_posting_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.t_posting_id_seq OWNED BY public.t_posting.id;


--
-- Name: t_sales; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.t_sales (
    id integer NOT NULL,
    user_id integer NOT NULL,
    laporan text,
    latlong character varying(200),
    lokasi character varying(200),
    alamat character varying(400),
    file text,
    created_at timestamp without time zone
);


--
-- Name: t_sales_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.t_sales_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: t_sales_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.t_sales_id_seq OWNED BY public.t_sales.id;


--
-- Name: titik_kantor_desa_se-indonesia_gid_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public."titik_kantor_desa_se-indonesia_gid_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: titik_lokasi3; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.titik_lokasi3 (
    id_lokasi integer NOT NULL,
    parent_id character varying(100) NOT NULL,
    nama_lokasi character varying(150) DEFAULT '-'::character varying NOT NULL,
    deskripsi character varying(150) DEFAULT '-'::character varying NOT NULL,
    latitude character varying(150) DEFAULT '-'::character varying NOT NULL,
    longitude character varying(150) DEFAULT '-'::character varying NOT NULL,
    alamat character varying(150) DEFAULT '-'::character varying NOT NULL,
    kelurahan character varying(150) DEFAULT '-'::character varying NOT NULL,
    kecamatan character varying(150) DEFAULT '-'::character varying NOT NULL,
    kab character varying(150) DEFAULT '-'::character varying NOT NULL,
    valid integer DEFAULT 1 NOT NULL,
    dept_id integer
);


--
-- Name: tz_world_gid_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tz_world_gid_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tz_world_gid_seq1; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tz_world_gid_seq1
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: v_absen_lengkap; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_absen_lengkap AS
 SELECT date(a.created_at) AS tanggal,
    a.created_at AS waktu_absen,
    (("left"((b.nip)::text, (length((b.nip)::text) - 5)) || '*****'::text))::character varying(200) AS nip,
    b.nama,
    a.pegawai_id,
        CASE b.status
            WHEN 1 THEN 'PNS'::text
            WHEN 2 THEN 'PTT'::text
            WHEN 3 THEN 'PPPK'::text
            WHEN 4 THEN 'PPPK PW'::text
            ELSE 'Tidak Diketahui'::text
        END AS status,
        CASE b.jenis_kelamin
            WHEN 1 THEN 'L'::text
            WHEN 2 THEN 'P'::text
            ELSE '-'::text
        END AS jenis_kelamin,
    c.kode AS kode_departemen,
    c.kode_lengkap AS departemen,
        CASE a.checktype
            WHEN 1 THEN 'Masuk'::text
            WHEN 2 THEN 'Keluar'::text
            ELSE 'Lainnya'::text
        END AS jenis_absen,
    a.work_code,
    a.jadwal_id,
    a.hari,
    a.jam_masuk,
    a.jam_keluar,
    a.jam_masuk_awal,
    a.jam_keluar_akhir,
    a.flexible_time,
    a.selisih_waktu,
    a.is_wfh,
    a.is_manual,
    a.current_location,
    a.latlong,
    a.jarak,
    a.timezone,
    a.imei,
        CASE b.other_attr
            WHEN '1'::text THEN 'Android'::text
            WHEN '2'::text THEN 'iOS'::text
            ELSE '-'::text
        END AS platform
   FROM ((public.t_checkinout a
     JOIN public.m_pegawai b ON ((a.pegawai_id = b.id)))
     JOIN public.m_departemen c ON ((b.departemen = c.id)))
  WHERE ((a.created_at >= '2026-06-01'::date) AND (a.created_at < '2026-07-01'::date))
  ORDER BY a.created_at, b.nama, a.checktype;


--
-- Name: v_checkinout_pegawai; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_checkinout_pegawai AS
 SELECT b.nip,
    b.nama,
    a.id,
    a.pegawai_id,
    a.latlong,
    a.departemen,
    a.location,
    a.jarak,
    a.checktype,
    a.imei,
    a.approval,
    a.approval_at,
    a.created_at,
    a.updated_at,
    a.current_location,
    a.ijin,
    a.keterangan,
    a.file,
    a.type_ijin,
    a.deskripsi,
    a.timezone,
    a.is_wfh,
    a.work_code,
    a.selisih_waktu,
    a.jadwal_id,
    a.hari,
    a.jam_masuk,
    a.jam_keluar,
    a.jam_masuk_awal,
    a.jam_keluar_akhir,
    a.flexible_time,
    a.is_manual,
    a.temp_current_location,
    date(a.created_at) AS date,
    c.kode,
    c.kode_lengkap
   FROM ((public.t_checkinout a
     JOIN public.m_pegawai b ON ((a.pegawai_id = b.id)))
     JOIN public.m_departemen c ON ((b.departemen = c.id)))
  ORDER BY a.id;


--
-- Name: v_fake; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_fake AS
 SELECT a.created_at,
    a.user_id,
    a.laporan AS jenis,
    a.latlong,
    a.lokasi AS nip,
    a.alamat AS nama,
    d.kode,
    d.kode_lengkap,
    a.file AS api_key
   FROM (((public.t_sales a
     JOIN public.m_user b ON ((a.user_id = b.id)))
     JOIN public.m_pegawai c ON ((b.pegawai_id = c.id)))
     JOIN public.m_departemen d ON ((c.departemen = d.id)))
  ORDER BY a.id DESC;


--
-- Name: v_inout; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_inout AS
 SELECT nip,
    date,
    waktu_masuk,
    ( SELECT max(b.created_at) AS waktu_pulang
           FROM public.v_checkinout_pegawai b
          WHERE ((a.date = b.date) AND ((a.nip)::text = (b.nip)::text))) AS pulang
   FROM ( SELECT v_checkinout_pegawai.nip,
            v_checkinout_pegawai.date,
            min(v_checkinout_pegawai.created_at) AS waktu_masuk
           FROM public.v_checkinout_pegawai
          GROUP BY v_checkinout_pegawai.nip, v_checkinout_pegawai.date) a;


--
-- Name: v_jmlfoto_pegawai; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_jmlfoto_pegawai AS
 SELECT "left"((b.kode)::text, 3) AS kode,
    d.nama_departemen,
    count(*) AS jumlah_pegawai,
    count(a.foto) AS jumlah_foto,
    count(*) FILTER (WHERE (a.is_foto_approved = 1)) AS jumlah_foto_approve
   FROM ((public.m_pegawai a
     JOIN public.m_departemen b ON ((a.departemen = b.id)))
     LEFT JOIN public.m_departemen d ON (((d.kode)::text = "left"((b.kode)::text, 3))))
  WHERE ((a.status <> 5) AND (length((b.kode)::text) >= 3))
  GROUP BY ("left"((b.kode)::text, 3)), d.nama_departemen
  ORDER BY ("left"((b.kode)::text, 3));


--
-- Name: v_pegawai; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_pegawai AS
 SELECT a.nip,
    a.nama,
    b.kode,
    b.kode_lengkap,
    a.jabatan,
    c.previleges,
    a.id AS pegawai_id,
    a.eselon,
    a.kelas_jabatan
   FROM ((public.m_pegawai a
     JOIN public.m_departemen b ON ((a.departemen = b.id)))
     JOIN public.m_previleges c ON ((a.status = c.id)));


--
-- Name: v_perizinan; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_perizinan AS
 SELECT b.nip,
    a.nama,
    c.kode_lengkap,
        CASE
            WHEN (a.tipe_ijin = 1) THEN 'Ijin Penuh'::text
            WHEN (a.tipe_ijin = 2) THEN 'Ijin Tidak Absen Masuk'::text
            WHEN (a.tipe_ijin = 3) THEN 'Ijin Tidak Absen Pulang'::text
            ELSE '-'::text
        END AS tipe_ijin,
    d.nama AS jenis_ijin,
    a.tgl_ijin,
    a.alasan,
        CASE
            WHEN (a.approval = true) THEN 'Approved'::text
            ELSE '-'::text
        END AS approval
   FROM (((public.t_perizinan a
     JOIN public.m_pegawai b ON ((a.pegawai_id = b.id)))
     JOIN public.m_departemen c ON ((a.departemen = c.id)))
     JOIN public.m_jenis_ijin d ON ((a.jenis_ijin = d.id)))
  ORDER BY b.nip;


--
-- Name: v_profil_opd; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_profil_opd AS
 SELECT split_part(b.kode_lengkap, ' - '::text, 1) AS opd,
    substr((b.kode)::text, 0, 4) AS kode,
    count(split_part(b.kode_lengkap, ' - '::text, 1)) AS jml,
    count(*) FILTER (WHERE (a.jenis_kelamin = 1)) AS laki,
    count(*) FILTER (WHERE (a.jenis_kelamin = 2)) AS perempuan,
    count(*) FILTER (WHERE (a.status = 1)) AS pns,
    count(*) FILTER (WHERE (a.status = 2)) AS ptt,
    count(*) FILTER (WHERE (a.status = 3)) AS pppk,
    count(*) FILTER (WHERE (a.status = 4)) AS pppkpw,
    count(*) FILTER (WHERE ((a.other_attr)::text = '1'::text)) AS android,
    count(*) FILTER (WHERE ((a.other_attr)::text = '2'::text)) AS apple,
    count(*) FILTER (WHERE ((a.other_attr)::text = '3'::text)) AS web,
    count(*) FILTER (WHERE (a.other_attr IS NULL)) AS not_set,
    count(*) FILTER (WHERE (a.attrs ~~* '%"pendidikan":"SD"%'::text)) AS sd,
    count(*) FILTER (WHERE (a.attrs ~~* '%"pendidikan":"SLTP"%'::text)) AS sltp,
    count(*) FILTER (WHERE (a.attrs ~~* '%"pendidikan":"SLTA"%'::text)) AS slta,
    count(*) FILTER (WHERE (a.attrs ~~* '%"pendidikan":"D-III"%'::text)) AS d3,
    count(*) FILTER (WHERE (a.attrs ~~* '%"pendidikan":"S-1"%'::text)) AS s1,
    count(*) FILTER (WHERE (a.attrs ~~* '%"pendidikan":"D-IV"%'::text)) AS d4,
    count(*) FILTER (WHERE (a.attrs ~~* '%"pendidikan":"S-2"%'::text)) AS s2,
    count(*) FILTER (WHERE (a.attrs ~~* '%"pendidikan":"S-3"%'::text)) AS s3
   FROM (public.m_pegawai a
     JOIN public.m_departemen b ON ((a.departemen = b.id)))
  WHERE ((a.status <> 5) AND ("left"((b.kode)::text, 5) <> 'HAPUS'::text))
  GROUP BY (split_part(b.kode_lengkap, ' - '::text, 1)), (substr((b.kode)::text, 0, 4))
  ORDER BY (split_part(b.kode_lengkap, ' - '::text, 1));


--
-- Name: events; Type: TABLE; Schema: test_curated_v2_20261028; Owner: -
--

CREATE TABLE test_curated_v2_20261028.events (
    label text NOT NULL,
    phase integer NOT NULL,
    event_id integer NOT NULL,
    pegawai_id integer NOT NULL,
    created_by_test_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: events; Type: TABLE; Schema: test_e2e_20261027; Owner: -
--

CREATE TABLE test_e2e_20261027.events (
    checktype integer NOT NULL,
    event_id integer NOT NULL
);


--
-- Name: shift_activation_audit; Type: TABLE; Schema: test_e2e_20261027; Owner: -
--

CREATE TABLE test_e2e_20261027.shift_activation_audit (
    shift_id integer NOT NULL,
    before_row jsonb NOT NULL,
    changed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);


--
-- Name: cohort; Type: TABLE; Schema: test_source_dashboard_20261030; Owner: -
--

CREATE TABLE test_source_dashboard_20261030.cohort (
    n integer,
    emp integer NOT NULL,
    dep integer,
    uid integer,
    j1 integer,
    j2 integer
);


--
-- Name: events; Type: TABLE; Schema: test_source_dashboard_20261030; Owner: -
--

CREATE TABLE test_source_dashboard_20261030.events (
    id integer NOT NULL,
    emp integer
);


--
-- Name: leaves; Type: TABLE; Schema: test_source_dashboard_20261030; Owner: -
--

CREATE TABLE test_source_dashboard_20261030.leaves (
    id integer NOT NULL,
    emp integer
);


--
-- Name: logged_actions event_id; Type: DEFAULT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.logged_actions ALTER COLUMN event_id SET DEFAULT nextval('audit.logged_actions_event_id_seq'::regclass);


--
-- Name: m_departemen id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_departemen ALTER COLUMN id SET DEFAULT nextval('public.m_departemen_id_seq'::regclass);


--
-- Name: m_disiplin id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_disiplin ALTER COLUMN id SET DEFAULT nextval('public.m_disiplin_id_seq'::regclass);


--
-- Name: m_disiplin_libur id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_disiplin_libur ALTER COLUMN id SET DEFAULT nextval('public.m_disiplin_libur_id_seq'::regclass);


--
-- Name: m_ip id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_ip ALTER COLUMN id SET DEFAULT nextval('public.m_ip_id_seq'::regclass);


--
-- Name: m_jenis_ijin id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_jenis_ijin ALTER COLUMN id SET DEFAULT nextval('public.m_jenis_ijin_id_seq'::regclass);


--
-- Name: m_lokasi id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_lokasi ALTER COLUMN id SET DEFAULT nextval('public.m_lokasi_id_seq'::regclass);


--
-- Name: m_pegawai id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_pegawai ALTER COLUMN id SET DEFAULT nextval('public.m_pegawai_id_seq'::regclass);


--
-- Name: m_phone id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_phone ALTER COLUMN id SET DEFAULT nextval('public.m_phone_id_seq'::regclass);


--
-- Name: m_previleges id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_previleges ALTER COLUMN id SET DEFAULT nextval('public.m_previleges_id_seq'::regclass);


--
-- Name: m_tipe_ijin id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_tipe_ijin ALTER COLUMN id SET DEFAULT nextval('public.m_tipe_ijin_id_seq'::regclass);


--
-- Name: mobile_service id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mobile_service ALTER COLUMN id SET DEFAULT nextval('public.mobile_service_id_seq'::regclass);


--
-- Name: r_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.r_log ALTER COLUMN id SET DEFAULT nextval('public.r_log_id_seq'::regclass);


--
-- Name: r_log_web id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.r_log_web ALTER COLUMN id SET DEFAULT nextval('public.r_log_web_id_seq'::regclass);


--
-- Name: r_update_nip id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.r_update_nip ALTER COLUMN id SET DEFAULT nextval('public.r_update_nip_id_seq'::regclass);


--
-- Name: t_cctv_recog id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_cctv_recog ALTER COLUMN id SET DEFAULT nextval('public.t_cctv_recog_id_seq'::regclass);


--
-- Name: t_log_lokasipegawai id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_log_lokasipegawai ALTER COLUMN id SET DEFAULT nextval('public.t_log_lokasipegawai_id_seq'::regclass);


--
-- Name: t_pegawai_lokasi id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_pegawai_lokasi ALTER COLUMN id SET DEFAULT nextval('public.t_pegawai_lokasi_id_seq'::regclass);


--
-- Name: t_perizinan id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_perizinan ALTER COLUMN id SET DEFAULT nextval('public.t_perizinan_id_seq'::regclass);


--
-- Name: t_posting id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_posting ALTER COLUMN id SET DEFAULT nextval('public.t_posting_id_seq'::regclass);


--
-- Name: t_sales id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_sales ALTER COLUMN id SET DEFAULT nextval('public.t_sales_id_seq'::regclass);


--
-- Name: logged_actions logged_actions_pkey; Type: CONSTRAINT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.logged_actions
    ADD CONSTRAINT logged_actions_pkey PRIMARY KEY (event_id);


--
-- Name: m_kota idm_kota_UNIQUE; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_kota
    ADD CONSTRAINT "idm_kota_UNIQUE" PRIMARY KEY (id);


--
-- Name: m_propinsi idm_provinsi_UNIQUE; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_propinsi
    ADD CONSTRAINT "idm_provinsi_UNIQUE" PRIMARY KEY (id);


--
-- Name: kecamatan kecamatan_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kecamatan
    ADD CONSTRAINT kecamatan_id PRIMARY KEY (id);


--
-- Name: kelurahan kelurahan_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kelurahan
    ADD CONSTRAINT kelurahan_id PRIMARY KEY (id);


--
-- Name: m_departemen m_departemen_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_departemen
    ADD CONSTRAINT m_departemen_id PRIMARY KEY (id);


--
-- Name: m_departemen m_departemen_kode; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_departemen
    ADD CONSTRAINT m_departemen_kode UNIQUE (kode);


--
-- Name: m_disiplin m_disiplin_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_disiplin
    ADD CONSTRAINT m_disiplin_id PRIMARY KEY (id);


--
-- Name: m_disiplin_libur m_disiplin_libur_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_disiplin_libur
    ADD CONSTRAINT m_disiplin_libur_id PRIMARY KEY (id);


--
-- Name: m_gol m_gol_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_gol
    ADD CONSTRAINT m_gol_pkey PRIMARY KEY (id);


--
-- Name: m_group m_group_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_group
    ADD CONSTRAINT m_group_pkey PRIMARY KEY (id);


--
-- Name: m_hari_libur m_hari_libur_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_hari_libur
    ADD CONSTRAINT m_hari_libur_id PRIMARY KEY (id);


--
-- Name: m_jadwal m_jadwal_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_jadwal
    ADD CONSTRAINT m_jadwal_id PRIMARY KEY (id);


--
-- Name: m_jenis_ijin m_jenis_ijin_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_jenis_ijin
    ADD CONSTRAINT m_jenis_ijin_id PRIMARY KEY (id);


--
-- Name: m_lokasi m_lokasi_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_lokasi
    ADD CONSTRAINT m_lokasi_id PRIMARY KEY (id);


--
-- Name: m_module m_module_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_module
    ADD CONSTRAINT m_module_pkey PRIMARY KEY (id);


--
-- Name: m_negara m_negara_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_negara
    ADD CONSTRAINT m_negara_pkey PRIMARY KEY (id);


--
-- Name: m_pegawai m_pegawai_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_pegawai
    ADD CONSTRAINT m_pegawai_id PRIMARY KEY (id);


--
-- Name: m_pegawai m_pegawai_nip; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_pegawai
    ADD CONSTRAINT m_pegawai_nip UNIQUE (nip);


--
-- Name: m_pengaturan m_pengaturan_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_pengaturan
    ADD CONSTRAINT m_pengaturan_pkey PRIMARY KEY (id);


--
-- Name: m_previleges m_previleges_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_previleges
    ADD CONSTRAINT m_previleges_id PRIMARY KEY (id);


--
-- Name: m_rules m_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_rules
    ADD CONSTRAINT m_rules_pkey PRIMARY KEY (id);


--
-- Name: m_shift m_shift_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_shift
    ADD CONSTRAINT m_shift_id PRIMARY KEY (id);


--
-- Name: m_tipe_ijin m_tipe_ijin_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_tipe_ijin
    ADD CONSTRAINT m_tipe_ijin_id PRIMARY KEY (id);


--
-- Name: m_user m_user_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_user
    ADD CONSTRAINT m_user_pkey PRIMARY KEY (id);


--
-- Name: mobile_service mobile_service_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mobile_service
    ADD CONSTRAINT mobile_service_id PRIMARY KEY (id);


--
-- Name: r_log r_log_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.r_log
    ADD CONSTRAINT r_log_id PRIMARY KEY (id);


--
-- Name: r_log_web r_log_web_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.r_log_web
    ADD CONSTRAINT r_log_web_id PRIMARY KEY (id);


--
-- Name: r_update_nip r_update_nip_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.r_update_nip
    ADD CONSTRAINT r_update_nip_id PRIMARY KEY (id);


--
-- Name: t_checkinout t_checkinout_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_checkinout
    ADD CONSTRAINT t_checkinout_id PRIMARY KEY (id);


--
-- Name: t_libur_shift t_libur_shift_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_libur_shift
    ADD CONSTRAINT t_libur_shift_id PRIMARY KEY (id);


--
-- Name: t_log_lokasipegawai t_log_lokasipegawai_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_log_lokasipegawai
    ADD CONSTRAINT t_log_lokasipegawai_id PRIMARY KEY (id);


--
-- Name: t_log_pegawai t_log_pegawai_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_log_pegawai
    ADD CONSTRAINT t_log_pegawai_id PRIMARY KEY (id);


--
-- Name: t_pegawai_lokasi t_pegawai_lokasi_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_pegawai_lokasi
    ADD CONSTRAINT t_pegawai_lokasi_id PRIMARY KEY (id);


--
-- Name: t_perizinan t_perizinan_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_perizinan
    ADD CONSTRAINT t_perizinan_id PRIMARY KEY (id);


--
-- Name: t_posting t_posting_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_posting
    ADD CONSTRAINT t_posting_id PRIMARY KEY (id);


--
-- Name: t_sales t_sales_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_sales
    ADD CONSTRAINT t_sales_id PRIMARY KEY (id);


--
-- Name: events events_event_id_key; Type: CONSTRAINT; Schema: test_curated_v2_20261028; Owner: -
--

ALTER TABLE ONLY test_curated_v2_20261028.events
    ADD CONSTRAINT events_event_id_key UNIQUE (event_id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: test_curated_v2_20261028; Owner: -
--

ALTER TABLE ONLY test_curated_v2_20261028.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (label);


--
-- Name: events events_event_id_key; Type: CONSTRAINT; Schema: test_e2e_20261027; Owner: -
--

ALTER TABLE ONLY test_e2e_20261027.events
    ADD CONSTRAINT events_event_id_key UNIQUE (event_id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: test_e2e_20261027; Owner: -
--

ALTER TABLE ONLY test_e2e_20261027.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (checktype);


--
-- Name: shift_activation_audit shift_activation_audit_pkey; Type: CONSTRAINT; Schema: test_e2e_20261027; Owner: -
--

ALTER TABLE ONLY test_e2e_20261027.shift_activation_audit
    ADD CONSTRAINT shift_activation_audit_pkey PRIMARY KEY (shift_id);


--
-- Name: cohort cohort_pkey; Type: CONSTRAINT; Schema: test_source_dashboard_20261030; Owner: -
--

ALTER TABLE ONLY test_source_dashboard_20261030.cohort
    ADD CONSTRAINT cohort_pkey PRIMARY KEY (emp);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: test_source_dashboard_20261030; Owner: -
--

ALTER TABLE ONLY test_source_dashboard_20261030.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: leaves leaves_pkey; Type: CONSTRAINT; Schema: test_source_dashboard_20261030; Owner: -
--

ALTER TABLE ONLY test_source_dashboard_20261030.leaves
    ADD CONSTRAINT leaves_pkey PRIMARY KEY (id);


--
-- Name: cohort_n_idx; Type: INDEX; Schema: test_source_dashboard_20261030; Owner: -
--

CREATE UNIQUE INDEX cohort_n_idx ON test_source_dashboard_20261030.cohort USING btree (n);


--
-- Name: m_jadwal audit_trigger_row; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER audit_trigger_row AFTER INSERT OR DELETE OR UPDATE ON public.m_jadwal FOR EACH ROW EXECUTE FUNCTION audit.if_modified_func('true');


--
-- Name: m_shift audit_trigger_row; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER audit_trigger_row AFTER INSERT OR DELETE OR UPDATE ON public.m_shift FOR EACH ROW EXECUTE FUNCTION audit.if_modified_func('true');


--
-- Name: m_jadwal audit_trigger_stm; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER audit_trigger_stm AFTER TRUNCATE ON public.m_jadwal FOR EACH STATEMENT EXECUTE FUNCTION audit.if_modified_func('true');


--
-- Name: m_shift audit_trigger_stm; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER audit_trigger_stm AFTER TRUNCATE ON public.m_shift FOR EACH STATEMENT EXECUTE FUNCTION audit.if_modified_func('true');


--
-- Name: kecamatan kecamatan_kota_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kecamatan
    ADD CONSTRAINT kecamatan_kota_id_fkey FOREIGN KEY (kota_id) REFERENCES public.m_kota(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: kelurahan kelurahan_kec_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kelurahan
    ADD CONSTRAINT kelurahan_kec_id_fkey FOREIGN KEY (kec_id) REFERENCES public.kecamatan(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: m_departemen m_departemen_lokasi_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_departemen
    ADD CONSTRAINT m_departemen_lokasi_fkey FOREIGN KEY (lokasi) REFERENCES public.m_lokasi(id) ON UPDATE SET NULL ON DELETE SET NULL;


--
-- Name: m_jadwal m_jadwal_jenis_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_jadwal
    ADD CONSTRAINT m_jadwal_jenis_fkey FOREIGN KEY (jenis) REFERENCES public.m_shift(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: m_jenis_ijin m_jenis_ijin_tipe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_jenis_ijin
    ADD CONSTRAINT m_jenis_ijin_tipe_id_fkey FOREIGN KEY (tipe_id) REFERENCES public.m_tipe_ijin(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: m_kota m_kota_FK_1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_kota
    ADD CONSTRAINT "m_kota_FK_1" FOREIGN KEY (id_propinsi) REFERENCES public.m_propinsi(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: m_pegawai m_pegawai_departemen_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_pegawai
    ADD CONSTRAINT m_pegawai_departemen_fkey FOREIGN KEY (departemen) REFERENCES public.m_departemen(id) ON UPDATE RESTRICT ON DELETE RESTRICT;


--
-- Name: m_pegawai m_pegawai_status_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_pegawai
    ADD CONSTRAINT m_pegawai_status_fkey FOREIGN KEY (status) REFERENCES public.m_previleges(id) ON UPDATE RESTRICT ON DELETE RESTRICT;


--
-- Name: m_pengaturan m_pengaturan_FK_1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_pengaturan
    ADD CONSTRAINT "m_pengaturan_FK_1" FOREIGN KEY (kota_id) REFERENCES public.m_kota(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: m_propinsi m_propinsi_FK_1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_propinsi
    ADD CONSTRAINT "m_propinsi_FK_1" FOREIGN KEY (id_negara) REFERENCES public.m_negara(id) ON UPDATE RESTRICT ON DELETE RESTRICT;


--
-- Name: m_rules m_rules_FK_1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_rules
    ADD CONSTRAINT "m_rules_FK_1" FOREIGN KEY (module_id) REFERENCES public.m_module(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: m_rules m_rules_FK_2; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_rules
    ADD CONSTRAINT "m_rules_FK_2" FOREIGN KEY (group_id) REFERENCES public.m_group(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: m_shift m_shift_departemen_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_shift
    ADD CONSTRAINT m_shift_departemen_id_fkey FOREIGN KEY (departemen_id) REFERENCES public.m_departemen(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: m_user m_user_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_user
    ADD CONSTRAINT m_user_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.m_group(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: m_user m_user_pegawai_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.m_user
    ADD CONSTRAINT m_user_pegawai_id_fkey FOREIGN KEY (pegawai_id) REFERENCES public.m_pegawai(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: t_checkinout t_checkinout_pegawai_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_checkinout
    ADD CONSTRAINT t_checkinout_pegawai_id_fkey FOREIGN KEY (pegawai_id) REFERENCES public.m_pegawai(id) ON UPDATE RESTRICT ON DELETE RESTRICT;


--
-- Name: t_libur_shift t_libur_shift_pegawai_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_libur_shift
    ADD CONSTRAINT t_libur_shift_pegawai_id_fkey FOREIGN KEY (pegawai_id) REFERENCES public.m_pegawai(id) ON UPDATE SET NULL ON DELETE SET NULL;


--
-- Name: t_log_lokasipegawai t_log_lokasipegawai_pegawai_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_log_lokasipegawai
    ADD CONSTRAINT t_log_lokasipegawai_pegawai_id_fkey FOREIGN KEY (pegawai_id) REFERENCES public.m_pegawai(id);


--
-- Name: t_pegawai_lokasi t_pegawai_lokasi_lokasi_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_pegawai_lokasi
    ADD CONSTRAINT t_pegawai_lokasi_lokasi_fkey FOREIGN KEY (lokasi) REFERENCES public.m_lokasi(id) ON UPDATE SET NULL ON DELETE SET NULL;


--
-- Name: t_pegawai_lokasi t_pegawai_lokasi_pegawai_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_pegawai_lokasi
    ADD CONSTRAINT t_pegawai_lokasi_pegawai_fkey FOREIGN KEY (pegawai) REFERENCES public.m_pegawai(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: t_perizinan t_perizinan_jenis_ijin_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_perizinan
    ADD CONSTRAINT t_perizinan_jenis_ijin_fkey FOREIGN KEY (jenis_ijin) REFERENCES public.m_jenis_ijin(id) ON UPDATE SET NULL ON DELETE SET NULL;


--
-- Name: t_perizinan t_perizinan_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_perizinan
    ADD CONSTRAINT t_perizinan_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.m_user(id) ON UPDATE RESTRICT ON DELETE RESTRICT;


--
-- Name: t_sales t_sales_pegawai_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.t_sales
    ADD CONSTRAINT t_sales_pegawai_fkey FOREIGN KEY (user_id) REFERENCES public.m_user(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict EV2ToM9f72euz9Ul8Noghfo14j8Pc3dZdmPGdagGKpN44YUijdJ7qdzhFtPWw78

