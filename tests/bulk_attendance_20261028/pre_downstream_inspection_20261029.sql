\set ON_ERROR_STOP on
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
WITH
oracle(s,ci,co,ei,eo) AS (VALUES
 (0,0,0,0,0),(1,1,1,0,0),(2,1,0,0,0),(3,0,1,0,0),
 (4,0,0,0,0),(5,0,1,1,0),(6,1,0,0,1),(7,0,0,0,1),
 (8,0,0,0,1),(9,1,1,1,1),(10,2,2,0,0),(11,0,0,1,1)),
d AS (SELECT * FROM curated.cur_attendance_daily),
p AS (SELECT * FROM curated.cur_employee_population_daily),
bydep AS (SELECT tanggal,departemen_id,count(*) employees FROM d GROUP BY 1,2),
e AS (SELECT pegawai_id,tanggal,
 count(*) FILTER(WHERE checktype=1) ci,count(*) FILTER(WHERE checktype=2) co,
 min(waktu_event) FILTER(WHERE checktype=1) first_in,
 max(waktu_event) FILTER(WHERE checktype=2) last_out
 FROM curated.cur_event_attendance WHERE tanggal IS NOT NULL GROUP BY 1,2),
l AS (SELECT pegawai_id,tanggal_izin AS tanggal,
 bool_or(is_valid_leave) valid,bool_or(excuses_checkin) ei,bool_or(excuses_checkout) eo
 FROM curated.cur_leave_daily GROUP BY 1,2),
scenario AS (SELECT c.scenario,count(*) employees,sum(d.active_employee_days) active,
 sum(d.checkin_days) checkin,sum(d.checkout_days) checkout,
 sum(d.no_checkin_days) no_checkin,sum(d.no_checkout_days) no_checkout,sum(d.leave_days) leave_days
 FROM test_bulk.cohort c JOIN d ON d.pegawai_id=c.emp GROUP BY c.scenario)
SELECT jsonb_pretty(jsonb_build_object(
 'database',current_database(),'checked_at',current_timestamp,'read_only',current_setting('transaction_read_only'),
 'counts',jsonb_build_object('cohort',(SELECT count(*) FROM test_bulk.cohort),'population',(SELECT count(*) FROM p),
 'events',(SELECT count(*) FROM curated.cur_event_attendance),'event_daily',(SELECT count(*) FROM curated.cur_attendance_event_daily),
 'leave_rows',(SELECT count(*) FROM curated.cur_leave_daily),'daily',(SELECT count(*) FROM d)),
 'coverage',(SELECT jsonb_build_object('date_min',min(tanggal),'date_max',max(tanggal),'dates',count(DISTINCT tanggal),
 'employees',count(DISTINCT pegawai_id),'departments',count(DISTINCT departemen_id),
 'unknown_department_rows',count(*) FILTER(WHERE departemen_id IS NULL),
 'active',count(*) FILTER(WHERE is_employee_active IS TRUE),'inactive',count(*) FILTER(WHERE is_employee_active IS FALSE),
 'unknown_status',count(*) FILTER(WHERE is_employee_active IS NULL),
 'review_rows',count(*) FILTER(WHERE perlu_review),'final_rows',count(*) FILTER(WHERE is_date_final)) FROM d),
 'department_distribution',(SELECT jsonb_build_object('partitions',count(*),'min_employees',min(employees),
 'max_employees',max(employees),'partitions_with_multiple_employees',count(*) FILTER(WHERE employees>1)) FROM bydep),
 'population_basis',(SELECT jsonb_agg(to_jsonb(x)) FROM (SELECT population_basis,count(*) rows FROM p GROUP BY 1) x),
 'totals',(SELECT jsonb_build_object('active',sum(active_employee_days),'checkin',sum(checkin_days),'checkout',sum(checkout_days),
 'no_checkin',sum(no_checkin_days),'no_checkout',sum(no_checkout_days),'leave_days',sum(leave_days),
 'required_checkin',sum(required_checkin_days),'required_checkout',sum(required_checkout_days),
 'excused_checkin',sum(excused_checkin_days),'excused_checkout',sum(excused_checkout_days),
 'required_checkin_present',sum(required_checkin_present_days),'required_checkout_present',sum(required_checkout_present_days)) FROM d),
 'scenarios',(SELECT jsonb_agg(to_jsonb(s) ORDER BY scenario) FROM scenario s),
 'checks',jsonb_build_object(
 'duplicate_daily_keys',(SELECT count(*) FROM (SELECT pegawai_id,tanggal FROM d GROUP BY 1,2 HAVING count(*)>1) x),
 'missing_cohort_daily',(SELECT count(*) FROM test_bulk.cohort c CROSS JOIN test_bulk.config cfg LEFT JOIN d ON d.pegawai_id=c.emp AND d.tanggal=cfg.test_date WHERE d.pegawai_id IS NULL),
 'extra_daily_outside_cohort',(SELECT count(*) FROM d WHERE NOT EXISTS(SELECT 1 FROM test_bulk.cohort c WHERE c.emp=d.pegawai_id)),
 'population_mismatch',(SELECT count(*) FROM d FULL JOIN p USING(pegawai_id,tanggal)
 WHERE d.pegawai_id IS NULL OR p.pegawai_id IS NULL OR d.departemen_id IS DISTINCT FROM p.departemen_id OR d.is_employee_active IS DISTINCT FROM p.is_employee_active),
 'scenario_oracle_mismatch',(SELECT count(*) FROM test_bulk.cohort c JOIN oracle o ON o.s=c.scenario
 JOIN d ON d.pegawai_id=c.emp WHERE
 (d.checkin_event_count,d.checkout_event_count,d.active_employee_days,d.checkin_days,d.checkout_days,
 d.excused_checkin_days,d.excused_checkout_days,d.required_checkin_days,d.required_checkout_days,
 d.required_checkin_present_days,d.required_checkout_present_days,d.no_checkin_days,d.no_checkout_days,d.leave_days)
 IS DISTINCT FROM
 (o.ci,o.co,1,(o.ci>0)::int,(o.co>0)::int,o.ei,o.eo,1-o.ei,1-o.eo,
 (o.ci>0)::int*(1-o.ei),(o.co>0)::int*(1-o.eo),(o.ci=0)::int*(1-o.ei),(o.co=0)::int*(1-o.eo),(o.ei>0 OR o.eo>0)::int)),
 'kpi_identity_mismatch',(SELECT count(*) FROM d WHERE active_employee_days<>required_checkin_days+excused_checkin_days
 OR active_employee_days<>required_checkout_days+excused_checkout_days
 OR required_checkin_days<>required_checkin_present_days+no_checkin_days
 OR required_checkout_days<>required_checkout_present_days+no_checkout_days),
 'event_detail_mismatch',(SELECT count(*) FROM d FULL JOIN e USING(pegawai_id,tanggal)
 WHERE d.pegawai_id IS NULL OR (d.checkin_event_count,d.checkout_event_count,d.first_checkin_at,d.last_checkout_at)
 IS DISTINCT FROM (COALESCE(e.ci,0),COALESCE(e.co,0),e.first_in,e.last_out)),
 'leave_detail_mismatch',(SELECT count(*) FROM d FULL JOIN l USING(pegawai_id,tanggal)
 WHERE d.pegawai_id IS NULL OR (d.has_valid_leave,d.has_excused_checkin,d.has_excused_checkout)
 IS DISTINCT FROM (COALESCE(l.valid,false),COALESCE(l.ei,false),COALESCE(l.eo,false))),
 'event_review',(SELECT count(*) FROM curated.cur_event_attendance WHERE perlu_review),
 'event_unresolved',(SELECT count(*) FROM curated.cur_event_attendance WHERE tanggal IS NULL),
 'leave_review',(SELECT count(*) FROM curated.cur_leave_daily WHERE perlu_review),
 'pending_curated_batches',(SELECT count(*) FROM etl_control.curated_batch WHERE status<>'APPLIED')),
 'batches',(SELECT jsonb_agg(jsonb_build_object('batch_id',batch_id,'status',status) ORDER BY created_at) FROM etl_control.curated_batch),
 'daily_hash',(SELECT md5(string_agg(to_jsonb(d)::text,'|' ORDER BY pegawai_id,tanggal)) FROM d)
));
COMMIT;
