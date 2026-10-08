DO $$ BEGIN
 IF current_database() <> 'epresensi_analytics_hop_dev' THEN
  RAISE EXCEPTION 'Wrong database for Hop calendar';
 END IF;
END $$;
ALTER TABLE public.dim_calendar
 ALTER COLUMN keterangan_libur TYPE text,
 ADD COLUMN IF NOT EXISTS hari_iso smallint CHECK (hari_iso BETWEEN 1 AND 7),
 ADD COLUMN IF NOT EXISTS tahun_iso smallint,
 ADD COLUMN IF NOT EXISTS is_hari_kerja_normal boolean,
 ADD COLUMN IF NOT EXISTS libur_id_sumber text,
 ADD COLUMN IF NOT EXISTS libur_source_created_at_terakhir timestamp,
 ADD COLUMN IF NOT EXISTS waktu_proses timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP;
CREATE OR REPLACE TRIGGER stamp_dim_calendar BEFORE UPDATE ON public.dim_calendar
FOR EACH ROW EXECUTE FUNCTION public.stamp_hop_dimension();
COMMENT ON COLUMN public.dim_calendar.libur_id_sumber IS 'Ordered source holiday IDs serialized as comma-separated text for Hop JDBC interoperability; NULL when no source holiday.';
COMMENT ON COLUMN public.dim_calendar.is_hari_libur IS 'True iff a holiday date exists in the source. False does not certify completeness of the official holiday calendar.';
COMMENT ON COLUMN public.dim_calendar.is_hari_kerja_normal IS 'Monday-Friday only; does not establish employee-specific attendance obligation.';
