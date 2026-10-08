DO $$ BEGIN IF current_database()<>'epresensi_analytics_hop_dev' THEN RAISE EXCEPTION 'Wrong target'; END IF; END $$;
ALTER TABLE public.fact_kehadiran
 ALTER COLUMN is_expected_workday DROP NOT NULL,
 ALTER COLUMN is_terlambat DROP NOT NULL,
 ALTER COLUMN is_pulang_awal DROP NOT NULL,
 ALTER COLUMN is_wfh DROP NOT NULL,
 ALTER COLUMN is_wfo DROP NOT NULL,
 ADD COLUMN IF NOT EXISTS pegawai_key bigint REFERENCES public.dim_pegawai(pegawai_key),
 ADD COLUMN IF NOT EXISTS departemen_key bigint REFERENCES public.dim_departemen(departemen_key),
 ADD COLUMN IF NOT EXISTS shift_key bigint REFERENCES public.dim_shift(shift_key),
 ADD COLUMN IF NOT EXISTS jadwal_id_sumber integer,
 ADD COLUMN IF NOT EXISTS izin_id_sumber text,
 ADD COLUMN IF NOT EXISTS jadwal_mulai timestamp,
 ADD COLUMN IF NOT EXISTS jadwal_selesai timestamp,
 ADD COLUMN IF NOT EXISTS mode_kerja text,
 ADD COLUMN IF NOT EXISTS durasi_terlambat numeric,
 ADD COLUMN IF NOT EXISTS status_usulan text,
 ADD COLUMN IF NOT EXISTS perlu_review boolean NOT NULL DEFAULT true,
 ADD COLUMN IF NOT EXISTS alasan_review text[] NOT NULL DEFAULT ARRAY['BELUM_DIPROSES'],
 ADD COLUMN IF NOT EXISTS is_kpi_final boolean NOT NULL DEFAULT false,
 ADD COLUMN IF NOT EXISTS source_event_min_id integer,
 ADD COLUMN IF NOT EXISTS source_event_max_id integer,
 ADD COLUMN IF NOT EXISTS waktu_proses timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 ADD COLUMN IF NOT EXISTS rule_version text;
CREATE INDEX IF NOT EXISTS fact_kehadiran_tanggal_idx ON public.fact_kehadiran(tanggal);
CREATE OR REPLACE TRIGGER stamp_fact_kehadiran BEFORE UPDATE ON public.fact_kehadiran
FOR EACH ROW EXECUTE FUNCTION public.stamp_hop_dimension();
COMMENT ON COLUMN public.fact_kehadiran.jadwal_id IS 'Legacy reference, unpopulated by Hop. Use jadwal_id_sumber and shift_key for combined dim_shift.';
COMMENT ON COLUMN public.fact_kehadiran.perizinan_id IS 'Legacy reference, unpopulated by Hop. izin_id_sumber preserves source request IDs without a separate fact_perizinan load.';
COMMENT ON COLUMN public.fact_kehadiran.is_kpi_final IS 'False for unresolved business rules or missing evidence; consume analytics.hop_fact_kehadiran_final only after backfill completes.';
CREATE OR REPLACE VIEW analytics.hop_fact_kehadiran_review AS SELECT * FROM public.fact_kehadiran WHERE perlu_review;
CREATE OR REPLACE VIEW analytics.hop_fact_kehadiran_final AS
 SELECT f.* FROM public.fact_kehadiran f
 WHERE f.is_kpi_final AND NOT f.perlu_review
 AND EXISTS(SELECT 1 FROM hop_etl.fact_checkpoint c WHERE c.singleton AND c.phase='done');

CREATE OR REPLACE VIEW analytics.hop_missing_employee_days_review AS
 SELECT p.pegawai_id,p.pegawai_key,c.tanggal,
 ARRAY['POPULASI_DAN_KEWAJIBAN_HISTORIS_BELUM_TERVERIFIKASI']::text[] AS alasan_review,
 false AS is_kpi_final
 FROM hop_etl.employee_snapshot p CROSS JOIN hop_etl.calendar_snapshot c
 CROSS JOIN hop_etl.fact_checkpoint cp
 WHERE cp.phase='done' AND c.tanggal BETWEEN cp.first_date AND cp.last_date
 AND NOT EXISTS(SELECT 1 FROM public.fact_kehadiran f WHERE f.pegawai_id=p.pegawai_id AND f.tanggal=c.tanggal);

CREATE OR REPLACE VIEW analytics.hop_event_rejects AS SELECT * FROM hop_etl.event_rejects;
