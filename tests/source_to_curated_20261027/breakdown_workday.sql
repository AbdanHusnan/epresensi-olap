-- Review view only; never assigns a parent's shift to an employee automatically.
CREATE OR REPLACE VIEW test_control.workday_missing_regular_breakdown AS
WITH RECURSIVE shift_stats AS (
 SELECT s.departemen_id,count(*) AS total_shift,
 count(*) FILTER(WHERE s.status) AS active_shift,
 count(*) FILTER(WHERE s.nama ~* '(regular|reguler)') AS regular_shift,
 count(*) FILTER(WHERE s.status AND s.nama ~* '(regular|reguler)' AND EXISTS(
 SELECT 1 FROM raw.raw_jadwal j WHERE j.jenis=s.id AND j.hari='Tue')) AS active_regular_tuesday,
 string_agg(DISTINCT s.nama, ' | ' ORDER BY s.nama) FILTER(WHERE s.status) AS active_shift_names,
 string_agg(DISTINCT s.nama, ' | ' ORDER BY s.nama) FILTER(WHERE NOT s.status) AS inactive_shift_names
 FROM raw.raw_shift s GROUP BY s.departemen_id
), population AS (
 SELECT departemen_id,count(*) AS active_employees
 FROM curated.cur_employee_workday
 WHERE tanggal='2026-10-27' AND is_employee_active AND NOT has_regular_schedule
 GROUP BY departemen_id
), ancestry AS (
 SELECT p.departemen_id AS origin,d.parent AS ancestor_id,1 AS depth,ARRAY[d.id] AS path
 FROM population p JOIN raw.raw_departemen d ON d.id=p.departemen_id
 WHERE d.parent IS NOT NULL
 UNION ALL
 SELECT a.origin,d.parent,a.depth+1,a.path||d.id FROM ancestry a
 JOIN raw.raw_departemen d ON d.id=a.ancestor_id
 WHERE d.parent IS NOT NULL AND NOT d.id=ANY(a.path) AND a.depth<30
), nearest_regular AS (
 SELECT DISTINCT ON(a.origin) a.origin,a.ancestor_id,a.depth
 FROM ancestry a JOIN shift_stats s ON s.departemen_id=a.ancestor_id
 WHERE s.active_regular_tuesday>0 AND NOT a.ancestor_id=ANY(a.path)
 ORDER BY a.origin,a.depth,a.ancestor_id
)
SELECT p.departemen_id,d.nama_departemen,p.active_employees,
 CASE WHEN p.departemen_id IS NULL THEN 'DEPARTEMEN_KOSONG'
 WHEN d.id IS NULL THEN 'DEPARTEMEN_TIDAK_DITEMUKAN'
 WHEN coalesce(s.total_shift,0)=0 THEN 'TANPA_SHIFT'
 WHEN coalesce(s.regular_shift,0)=0 THEN 'TANPA_NAMA_REGULER'
 ELSE 'REGULER_TANPA_JADWAL_AKTIF_SELASA' END AS reason,
 coalesce(s.total_shift,0) AS total_shift,coalesce(s.active_shift,0) AS active_shift,
 s.active_shift_names,s.inactive_shift_names,
 d.parent,parent.nama_departemen AS parent_name,
 coalesce(ps.active_regular_tuesday,0) AS parent_regular_tuesday_count,
 n.ancestor_id AS nearest_regular_ancestor_id,nd.nama_departemen AS nearest_regular_ancestor_name,
 n.depth AS ancestor_depth,d.opd_parent,d.unit_kerja_induk
FROM population p
LEFT JOIN raw.raw_departemen d ON d.id=p.departemen_id
LEFT JOIN shift_stats s ON s.departemen_id=p.departemen_id
LEFT JOIN raw.raw_departemen parent ON parent.id=d.parent
LEFT JOIN shift_stats ps ON ps.departemen_id=d.parent
LEFT JOIN nearest_regular n ON n.origin=p.departemen_id
LEFT JOIN raw.raw_departemen nd ON nd.id=n.ancestor_id;
