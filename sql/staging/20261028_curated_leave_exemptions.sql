-- Schema upgrade body. Install together with the ETL in one transaction.
-- Existing leave outputs require an explicit replay plan; never silently label
-- previously processed leave as unexcused. Current staging and E2E have no leave.
SELECT pg_advisory_xact_lock(hashtext('curated_population_v2_apply'));
DO $$
BEGIN
 IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='curated'
            AND table_name='cur_leave_daily' AND column_name='tipe_ijin_sumber') THEN
   RETURN;
 END IF;
 IF EXISTS (SELECT 1 FROM curated.cur_leave_daily)
 OR EXISTS (SELECT 1 FROM curated.cur_attendance_daily WHERE has_valid_leave) THEN
   RAISE EXCEPTION 'Existing leave results need an explicit replay before this schema upgrade';
 END IF;
 ALTER TABLE curated.cur_leave_daily
   ADD COLUMN tipe_ijin_sumber integer,
   ADD COLUMN setengah_hari_jenis_sumber boolean,
   ADD COLUMN excuses_checkin boolean GENERATED ALWAYS AS
     (is_valid_leave AND COALESCE(tipe_ijin_sumber IN (1,2),false)) STORED,
   ADD COLUMN excuses_checkout boolean GENERATED ALWAYS AS
     (is_valid_leave AND COALESCE(tipe_ijin_sumber IN (1,3),false)) STORED,
   ADD CONSTRAINT leave_valid_transaction_type CHECK
     (NOT is_valid_leave OR (tipe_ijin_sumber IS NOT NULL AND tipe_ijin_sumber IN (1,2,3)));
 ALTER TABLE curated.cur_attendance_daily
   ADD COLUMN has_excused_checkin boolean NOT NULL DEFAULT false,
   ADD COLUMN has_excused_checkout boolean NOT NULL DEFAULT false;
 -- PostgreSQL 16 requires replacing generated columns to change expressions.
 -- No CASCADE: an unexpected downstream dependency must abort the transaction.
 ALTER TABLE curated.cur_attendance_daily DROP COLUMN no_checkin_days;
 ALTER TABLE curated.cur_attendance_daily DROP COLUMN no_checkout_days;
 ALTER TABLE curated.cur_attendance_daily
   ADD COLUMN no_checkin_days integer GENERATED ALWAYS AS
     (CASE WHEN is_employee_active AND NOT has_excused_checkin AND checkin_event_count=0 THEN 1 ELSE 0 END) STORED,
   ADD COLUMN no_checkout_days integer GENERATED ALWAYS AS
     (CASE WHEN is_employee_active AND NOT has_excused_checkout AND checkout_event_count=0 THEN 1 ELSE 0 END) STORED,
   ADD COLUMN required_checkin_days integer GENERATED ALWAYS AS
     (CASE WHEN is_employee_active AND NOT has_excused_checkin THEN 1 ELSE 0 END) STORED,
   ADD COLUMN required_checkout_days integer GENERATED ALWAYS AS
     (CASE WHEN is_employee_active AND NOT has_excused_checkout THEN 1 ELSE 0 END) STORED,
   ADD COLUMN excused_checkin_days integer GENERATED ALWAYS AS
     (CASE WHEN is_employee_active AND has_excused_checkin THEN 1 ELSE 0 END) STORED,
   ADD COLUMN excused_checkout_days integer GENERATED ALWAYS AS
     (CASE WHEN is_employee_active AND has_excused_checkout THEN 1 ELSE 0 END) STORED,
   ADD COLUMN required_checkin_present_days integer GENERATED ALWAYS AS
     (CASE WHEN is_employee_active AND NOT has_excused_checkin AND checkin_event_count>0 THEN 1 ELSE 0 END) STORED,
   ADD COLUMN required_checkout_present_days integer GENERATED ALWAYS AS
     (CASE WHEN is_employee_active AND NOT has_excused_checkout AND checkout_event_count>0 THEN 1 ELSE 0 END) STORED,
   ADD CONSTRAINT daily_excused_requires_leave CHECK
     (NOT (has_excused_checkin OR has_excused_checkout) OR has_valid_leave),
   ADD CONSTRAINT daily_full_leave_excuses_both CHECK
     (NOT has_full_day_leave OR (has_excused_checkin AND has_excused_checkout));
END $$;
COMMENT ON COLUMN curated.cur_leave_daily.tipe_ijin_sumber IS
 't_perizinan.tipe_ijin: 1 full, 2 excused check-in, 3 excused check-out. Distinct from m_tipe_ijin category ID.';
COMMENT ON COLUMN curated.cur_leave_daily.setengah_hari_jenis_sumber IS
 'Original master flag for audit only; transaction tipe_ijin determines actual coverage.';
COMMENT ON TABLE curated.cur_attendance_daily IS
 'Active population, independent event evidence, approved valid leave exemptions by transaction tipe_ijin. Missing required check-in/out excludes excused sides. Provisional, not roster compliance.';
