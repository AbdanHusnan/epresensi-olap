-- Pure event-level classifications; these functions do not modify attendance data.
-- Daily shift selection and leave exemptions must be applied separately.
-- A window that wraps midnight is UNKNOWN until date/session assignment is proven.
CREATE OR REPLACE FUNCTION etl_control.classify_checkin_window(
  p_event_time time, p_early time, p_start time
) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
 SELECT CASE
   WHEN p_event_time IS NULL OR p_early IS NULL OR p_start IS NULL THEN 'UNKNOWN'
   WHEN p_early > p_start THEN 'UNKNOWN'
   WHEN p_event_time > p_start THEN 'LATE'
   ELSE 'ON_TIME'
 END
$$;

-- This only describes the observed checkout against its recorded window; it
-- does not declare an early checkout to be misconduct or create a new KPI.
CREATE OR REPLACE FUNCTION etl_control.classify_checkout_window(
  p_event_time time, p_end time, p_last time
) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
 SELECT CASE
   WHEN p_event_time IS NULL OR p_end IS NULL OR p_last IS NULL THEN 'UNKNOWN'
   WHEN p_end > p_last THEN 'UNKNOWN'
   WHEN p_event_time < p_end THEN 'BEFORE_WINDOW'
   WHEN p_event_time > p_last THEN 'AFTER_WINDOW'
   ELSE 'IN_WINDOW'
 END
$$;
