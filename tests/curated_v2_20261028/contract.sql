-- Synthetic contract checks only; caller must wrap in a rolled-back transaction.
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM curated.cur_attendance_daily WHERE pegawai_id<0)
 THEN RAISE EXCEPTION 'Negative fixture identifiers already exist'; END IF;
END $$;
INSERT INTO curated.cur_event_attendance
(checkinout_id_sumber,pegawai_id,tanggal_event,waktu_event,checktype,
 shift_id_sumber,jadwal_id_sumber,tanggal,date_assignment_status,
 date_assignment_reason,date_assignment_policy,source_snapshot_at)
VALUES
(-1,-100,'2026-10-28','2026-10-28 07:00',1,1,11,'2026-10-28','PROVISIONAL','synthetic same-day','TEST_ONLY',now()),
(-2,-100,'2026-10-28','2026-10-28 14:05',2,1,11,'2026-10-28','PROVISIONAL','synthetic same-day','TEST_ONLY',now()),
(-3,-100,'2026-10-28','2026-10-28 14:00',1,2,22,'2026-10-28','PROVISIONAL','synthetic same-day','TEST_ONLY',now()),
(-4,-100,'2026-10-28','2026-10-28 21:00',2,2,22,'2026-10-28','PROVISIONAL','synthetic same-day','TEST_ONLY',now());
INSERT INTO curated.cur_attendance_event_daily
(pegawai_id,tanggal,checkin_event_count,checkout_event_count,first_checkin_at,
 last_checkout_at,schedule_count,shift_count,date_assignment_policy,source_snapshot_at)
SELECT pegawai_id,tanggal,count(*) FILTER (WHERE checktype=1),
 count(*) FILTER (WHERE checktype=2),min(waktu_event) FILTER (WHERE checktype=1),
 max(waktu_event) FILTER (WHERE checktype=2),count(DISTINCT jadwal_id_sumber),
 count(DISTINCT shift_id_sumber),'TEST_ONLY',now()
FROM curated.cur_event_attendance WHERE pegawai_id=-100 GROUP BY pegawai_id,tanggal;

INSERT INTO curated.cur_attendance_daily
(pegawai_id,tanggal,is_employee_active,population_basis,checkin_event_count,
 checkout_event_count,first_checkin_at,last_checkout_at,has_valid_leave,
 date_assignment_policy,source_snapshot_at)
SELECT id,'2026-10-28',active,'EXTRACTION_SNAPSHOT',ci,co,
 CASE WHEN ci>0 THEN timestamp '2026-10-28 07:00' END,
 CASE WHEN co>0 THEN timestamp '2026-10-28 21:00' END,izin,'TEST_ONLY',now()
FROM (VALUES
 (-1,true,0,0,false),(-2,true,1,0,false),(-3,true,0,1,false),
 (-4,true,2,2,false),(-5,true,0,0,true),(-6,true,1,1,true),
 (-7,false,1,1,true),(-8,NULL::boolean,0,0,false)
) v(id,active,ci,co,izin);

DO $$
BEGIN
 IF (SELECT count(*) FROM curated.cur_attendance_event_daily WHERE pegawai_id=-100)<>1
 OR NOT EXISTS (SELECT 1 FROM curated.cur_attendance_event_daily
   WHERE pegawai_id=-100 AND has_masuk AND has_pulang
     AND first_checkin_at='2026-10-28 07:00' AND last_checkout_at='2026-10-28 21:00'
     AND shift_count=2 AND checkin_event_count=2 AND checkout_event_count=2)
 THEN RAISE EXCEPTION 'Multi-shift aggregation failed'; END IF;
 IF EXISTS (
   SELECT 1 FROM (VALUES
    (-1,1,0,1,0,1,0),(-2,1,1,0,0,1,0),(-3,1,0,1,1,0,0),
    (-4,1,1,0,1,0,0),(-5,1,0,1,0,1,1),(-6,1,1,0,1,0,1),
    (-7,0,0,0,0,0,0),(-8,0,0,0,0,0,0)
   ) e(id,a,ci,nci,co,nco,l)
   LEFT JOIN curated.cur_attendance_daily d ON d.pegawai_id=e.id AND d.tanggal='2026-10-28'
   WHERE ROW(d.active_employee_days,d.checkin_days,d.no_checkin_days,
             d.checkout_days,d.no_checkout_days,d.leave_days)
     IS DISTINCT FROM ROW(e.a,e.ci,e.nci,e.co,e.nco,e.l)
 ) THEN RAISE EXCEPTION 'Population/leave/event truth table failed'; END IF;
 IF EXISTS (SELECT 1 FROM curated.cur_attendance_daily WHERE pegawai_id<0
   AND (active_employee_days<>checkin_days+no_checkin_days
     OR active_employee_days<>checkout_days+no_checkout_days))
 THEN RAISE EXCEPTION 'Complement identities failed'; END IF;
 BEGIN
  INSERT INTO curated.cur_attendance_event_daily
  (pegawai_id,tanggal,checkin_event_count,checkout_event_count,first_checkin_at,
   last_checkout_at,schedule_count,shift_count,date_assignment_policy,source_snapshot_at)
  SELECT pegawai_id,tanggal,checkin_event_count,checkout_event_count,first_checkin_at,
   last_checkout_at,schedule_count,shift_count,date_assignment_policy,source_snapshot_at
  FROM curated.cur_attendance_event_daily WHERE pegawai_id=-100;
  RAISE EXCEPTION 'Duplicate grain accepted';
 EXCEPTION WHEN unique_violation THEN NULL;
 END;
 BEGIN
  INSERT INTO curated.cur_event_attendance
  (checkinout_id_sumber,tanggal,date_assignment_reason,source_snapshot_at)
  VALUES (-9,'2026-10-28','unresolved must have no assigned date',now());
  RAISE EXCEPTION 'Unresolved event received date';
 EXCEPTION WHEN check_violation THEN NULL;
 END;
END $$;
SELECT 'PASS: two shifts, eight KPI cases, complements, unique grain, unresolved date guard' AS result;
