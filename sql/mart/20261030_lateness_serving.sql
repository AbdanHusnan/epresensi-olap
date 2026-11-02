-- One row per employee/date. Aggregate selected periods with distinct employee
-- IDs for a people-based rate; do not add daily counts across multiple days.
CREATE OR REPLACE VIEW serving.v_lateness_employee_daily AS
SELECT f.tanggal, f.pegawai_id_sumber, f.departemen_id_sumber,
       COALESCE(d.nama, 'Department ' || f.departemen_id_sumber::text, 'UNKNOWN') AS nama_departemen,
       f.is_employee_active, f.lateness_status, f.lateness_event_id,
       f.lateness_schedule_id, f.lateness_reason, f.is_date_final,
       f.perlu_review,
       NOT COALESCE(s.is_closed AND s.population_complete AND s.curated_delivery_complete, false)
         OR NOT f.is_date_final OR f.perlu_review AS is_provisional,
       f.pegawai_key, f.has_excused_checkin, f.checkin_event_count
FROM mart_kehadiran.fact_kehadiran_daily f
JOIN mart_kehadiran.dim_departemen d USING (departemen_key)
LEFT JOIN serving.attendance_date_state s USING (tanggal);
