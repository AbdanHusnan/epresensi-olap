#!/usr/bin/env python3
"""Refresh display names for the source-derived mart dimensions.

The current test mart contains only one reporting date. This imports just source
IDs and display names from its raw snapshot, then updates the dimension version
effective on that date. No attendance facts, aggregates, or source records change.
"""

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
STAGING = "staging_bkd_mart_bulk_20261029"
MART = "mart_bkd_bulk_20261029"
DATE = "2026-10-30"


def run(args, input_text=None):
    completed = subprocess.run(args, input=input_text, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr[-3000:])
    return completed.stdout


def psql(container, database, query):
    return run([
        "docker", "exec", "-i", container, "sh", "-c",
        'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"',
        "psql", database,
    ], query).strip()


def mart(query):
    return psql("epresensi-mart-postgres", MART, query)


def fingerprint():
    query = """
    SELECT json_build_object(
      'facts', md5(string_agg(md5(to_jsonb(f)::text || f.xmin::text), ''
        ORDER BY f.pegawai_id_sumber, f.tanggal)),
      'aggregates', md5(string_agg(md5(to_jsonb(a)::text || a.xmin::text), ''
        ORDER BY a.tanggal, a.departemen_key)),
      'kpi', (SELECT json_agg(x ORDER BY x.tanggal)
        FROM (SELECT tanggal, SUM(active_employee_days) AS active,
                     SUM(checkin_days) AS checkin, SUM(checkout_days) AS checkout,
                     SUM(no_checkin_days) AS missing_checkin,
                     SUM(no_checkout_days) AS missing_checkout,
                     SUM(leave_days) AS leave
              FROM serving.v_kehadiran_departemen_harian GROUP BY tanggal) x)
    )
    FROM mart_kehadiran.fact_kehadiran_daily f
    CROSS JOIN (SELECT * FROM serving.agg_kehadiran_departemen_harian) a
    """
    # Avoid a fact × aggregate cross join while retaining deterministic hashes.
    query = """
    SELECT json_build_object(
      'facts', (SELECT md5(string_agg(md5(to_jsonb(f)::text || f.xmin::text), ''
        ORDER BY f.pegawai_id_sumber, f.tanggal)) FROM mart_kehadiran.fact_kehadiran_daily f),
      'aggregates', (SELECT md5(string_agg(md5(to_jsonb(a)::text || a.xmin::text), ''
        ORDER BY a.tanggal, a.departemen_key)) FROM serving.agg_kehadiran_departemen_harian a),
      'kpi', (SELECT json_agg(x ORDER BY x.tanggal)
        FROM (SELECT tanggal, SUM(active_employee_days) AS active,
                     SUM(checkin_days) AS checkin, SUM(checkout_days) AS checkout,
                     SUM(no_checkin_days) AS missing_checkin,
                     SUM(no_checkout_days) AS missing_checkout,
                     SUM(leave_days) AS leave
              FROM serving.v_kehadiran_departemen_harian GROUP BY tanggal) x)
    )
    """
    return json.loads(mart(query))


def load_names(source_query, table, id_column, dimension_table, dimension_id):
    """Copy names through a short-lived mart staging table without local files."""
    mart(f"CREATE SCHEMA IF NOT EXISTS test_source; DROP TABLE IF EXISTS test_source.{table}; "
         f"CREATE TABLE test_source.{table}({id_column} integer PRIMARY KEY, nama text);")
    source = subprocess.Popen([
        "docker", "exec", "epresensi-staging-postgres", "sh", "-c",
        'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "$2"',
        "psql", STAGING, "COPY (" + source_query + ") TO STDOUT WITH (FORMAT csv)",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    destination = subprocess.Popen([
        "docker", "exec", "-i", "epresensi-mart-postgres", "sh", "-c",
        'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "$2"',
        "psql", MART, f"COPY test_source.{table}({id_column},nama) FROM STDIN WITH (FORMAT csv)",
    ], stdin=source.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    source.stdout.close()
    destination_stdout, destination_stderr = destination.communicate()
    source_stderr = source.stderr.read()
    source_rc = source.wait()
    if source_rc:
        raise RuntimeError(source_stderr[-3000:])
    if destination.returncode:
        raise RuntimeError(destination_stderr[-3000:])
    result = mart(f"""
    BEGIN;
    WITH changed AS (
      UPDATE {dimension_table} d
         SET nama=s.nama
        FROM test_source.{table} s
       WHERE d.{dimension_id}=s.{id_column}
         AND DATE '{DATE}' >= d.valid_from
         AND (d.valid_to IS NULL OR DATE '{DATE}' < d.valid_to)
         AND d.nama IS DISTINCT FROM s.nama
       RETURNING 1
    )
    SELECT json_build_object('loaded',(SELECT count(*) FROM test_source.{table}),
      'changed',(SELECT count(*) FROM changed));
    DROP TABLE test_source.{table};
    COMMIT;
    """)
    return json.loads(result)


def main():
    before = fingerprint()
    employees = load_names(
        "SELECT id,nama FROM raw.raw_pegawai ORDER BY id",
        "dimension_employee_names_load_20261030", "pegawai_id_sumber",
        "mart_kehadiran.dim_pegawai", "pegawai_id_sumber",
    )
    departments = load_names(
        "SELECT id,nama_departemen FROM raw.raw_departemen ORDER BY id",
        "dimension_department_names_load_20261030", "departemen_id_sumber",
        "mart_kehadiran.dim_departemen", "departemen_id_sumber",
    )

    after = fingerprint()
    if before != after:
        raise AssertionError("Name refresh changed facts, aggregates, or KPI totals")
    coverage = json.loads(mart("""
    SELECT json_build_object(
      'employee_dimensions', (SELECT count(*) FROM mart_kehadiran.dim_pegawai
        WHERE pegawai_key>0),
      'named_employee_dimensions', (SELECT count(*) FROM mart_kehadiran.dim_pegawai
        WHERE pegawai_key>0 AND nama IS NOT NULL),
      'department_dimensions', (SELECT count(*) FROM mart_kehadiran.dim_departemen
        WHERE departemen_key>0),
      'named_department_dimensions', (SELECT count(*) FROM mart_kehadiran.dim_departemen
        WHERE departemen_key>0 AND nama IS NOT NULL),
      'facts_with_employee_name', (SELECT count(*) FROM mart_kehadiran.fact_kehadiran_daily f
        JOIN mart_kehadiran.dim_pegawai p USING(pegawai_key) WHERE p.nama IS NOT NULL),
      'aggregates_with_department_name', (SELECT count(*)
        FROM serving.v_kehadiran_departemen_harian WHERE nama_departemen IS NOT NULL)
    )
    """))
    expected = {
        "employee_dimensions": coverage["employee_dimensions"],
        "named_employee_dimensions": coverage["employee_dimensions"],
        "department_dimensions": coverage["department_dimensions"],
        "named_department_dimensions": coverage["department_dimensions"],
        "facts_with_employee_name": 72259,
        "aggregates_with_department_name": 3829,
    }
    if coverage != expected:
        raise AssertionError({"coverage": coverage, "expected": expected})
    result = {
        "passed": True,
        "effective_date": DATE,
        "employee_import": employees,
        "department_import": departments,
        "coverage": coverage,
        "facts_and_kpis_unchanged": True,
    }
    (OUT / "dimension_name_refresh.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
