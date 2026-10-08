DO $$ BEGIN
 IF current_database() <> 'epresensi_analytics_hop_dev' THEN
  RAISE EXCEPTION 'Wrong database for Hop dim_shift';
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS public.dim_shift (
 shift_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 jadwal_id_sumber integer NOT NULL UNIQUE,
 shift_id_sumber integer NOT NULL,
 nama_shift text NOT NULL,
 departemen_id_sumber integer,
 departemen_key bigint REFERENCES public.dim_departemen(departemen_key),
 is_aktif_saat_ini boolean,
 is_reguler boolean NOT NULL,
 is_flexible_kode_sumber integer CHECK (is_flexible_kode_sumber IN (0,1)),
 is_flexible boolean,
 event_id_sumber integer,
 shift_source_created_at timestamp,
 jadwal_source_created_at timestamp,
 hari_sumber text NOT NULL,
 hari text NOT NULL,
 hari_iso integer NOT NULL CHECK (hari_iso BETWEEN 1 AND 7),
 jam_masuk time NOT NULL,
 jam_keluar time NOT NULL,
 jam_masuk_awal time NOT NULL,
 jam_keluar_akhir time NOT NULL,
 flexible_time_sumber time,
 indikasi_lintas_tengah_malam boolean NOT NULL,
 is_jam_sama boolean NOT NULL,
 waktu_proses timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 etl_loaded_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS dim_shift_source_day_idx ON public.dim_shift(shift_id_sumber,hari_iso);
CREATE INDEX IF NOT EXISTS dim_shift_department_day_idx ON public.dim_shift(departemen_key,hari_iso);
CREATE OR REPLACE TRIGGER stamp_dim_shift BEFORE UPDATE ON public.dim_shift
FOR EACH ROW EXECUTE FUNCTION public.stamp_hop_dimension();
COMMENT ON TABLE public.dim_shift IS 'Combined m_jadwal + m_shift current snapshot; one row per m_jadwal.id. Not historical validity. Shifts without schedules are reported separately.';
COMMENT ON COLUMN public.dim_shift.shift_id_sumber IS 'Parent shift ID; repeats across weekday schedules. Not the upsert key.';
COMMENT ON COLUMN public.dim_shift.indikasi_lintas_tengah_malam IS 'Diagnostic only; does not decide work-date attribution.';
