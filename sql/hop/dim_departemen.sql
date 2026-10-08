-- Separate namespace for the agreed Hop model; public tables remain in use.
CREATE SCHEMA IF NOT EXISTS hop;
CREATE TABLE IF NOT EXISTS hop.dim_departemen (
    departemen_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    departemen_id_sumber integer NOT NULL UNIQUE,
    kode_departemen varchar(40),
    nama_departemen varchar(200),
    kode_lengkap text,
    parent_id_sumber integer,
    opd_induk_id_sumber integer,
    unit_kerja_induk_id_sumber integer,
    waktu_proses timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION hop.stamp_dim_departemen()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.waktu_proses := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;
CREATE OR REPLACE TRIGGER stamp_dim_departemen
BEFORE UPDATE ON hop.dim_departemen
FOR EACH ROW EXECUTE FUNCTION hop.stamp_dim_departemen();

COMMENT ON TABLE hop.dim_departemen IS
'Current source snapshot from dbabsen_restore. No inferred historical validity or automatic deletion.';
COMMENT ON COLUMN hop.dim_departemen.waktu_proses IS
'Timestamp of insert or latest changed-row update; unchanged reruns retain this timestamp.';
COMMENT ON COLUMN hop.dim_departemen.opd_induk_id_sumber IS
'Raw source reference. Preserve orphan references for audit; not a validated foreign key.';
