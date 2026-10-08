-- Additive migration, only for epresensi_analytics_hop_dev.
DO $$ BEGIN
 IF current_database() <> 'epresensi_analytics_hop_dev' THEN
  RAISE EXCEPTION 'Wrong database for Hop dev migration';
 END IF;
END $$;
ALTER TABLE public.dim_departemen ALTER COLUMN departemen_id_sumber DROP EXPRESSION IF EXISTS;
ALTER TABLE public.dim_pegawai ALTER COLUMN pegawai_id_sumber DROP EXPRESSION IF EXISTS;
ALTER TABLE public.dim_departemen
 ALTER COLUMN nama_departemen DROP NOT NULL,
 ALTER COLUMN departemen_id_sumber SET NOT NULL,
 ADD COLUMN IF NOT EXISTS kode_lengkap text,
 ADD COLUMN IF NOT EXISTS parent_id_sumber integer,
 ADD COLUMN IF NOT EXISTS opd_induk_id_sumber integer,
 ADD COLUMN IF NOT EXISTS unit_kerja_induk_id_sumber integer,
 ADD COLUMN IF NOT EXISTS waktu_proses timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE public.dim_pegawai
 ALTER COLUMN pegawai_id_sumber SET NOT NULL,
 ADD COLUMN IF NOT EXISTS jenis_kelamin_kode integer,
 ADD COLUMN IF NOT EXISTS jabatan text,
 ADD COLUMN IF NOT EXISTS pangkat text,
 ADD COLUMN IF NOT EXISTS jenis_jabatan text,
 ADD COLUMN IF NOT EXISTS eselon text,
 ADD COLUMN IF NOT EXISTS kelas_jabatan text,
 ADD COLUMN IF NOT EXISTS unit_kerja_induk_id_sumber integer,
 ADD COLUMN IF NOT EXISTS source_created_at timestamp;
CREATE OR REPLACE FUNCTION public.stamp_hop_dimension()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 NEW.waktu_proses := CURRENT_TIMESTAMP;
 NEW.etl_loaded_at := CURRENT_TIMESTAMP;
 RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER stamp_dim_departemen BEFORE UPDATE ON public.dim_departemen
FOR EACH ROW EXECUTE FUNCTION public.stamp_hop_dimension();
CREATE OR REPLACE TRIGGER stamp_dim_pegawai BEFORE UPDATE ON public.dim_pegawai
FOR EACH ROW EXECUTE FUNCTION public.stamp_hop_dimension();
COMMENT ON TABLE public.dim_pegawai IS 'Hop current snapshot: one row per source ID, updates preserve surrogate key; no SCD2 or automatic deletion.';
COMMENT ON COLUMN public.dim_pegawai.status_aktif IS 'Unmapped NULL: source status is a category, not a proven historical active flag.';
