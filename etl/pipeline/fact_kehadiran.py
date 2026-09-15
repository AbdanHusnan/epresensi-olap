from etl.connectors.oltp import get_oltp_connection
from etl.connectors.olap import get_olap_connection

from etl.config.fact_kehadiran import (
    get_default_config,
    validate_config,
)

from etl.extract.fact_kehadiran import (
    extract_pegawai,
    extract_calendar,
    extract_schedule,
    extract_libur_shift,
    extract_attendance,
)

from etl.transform.fact_kehadiran.employee_day import (
    build_employee_days,
)

from etl.transform.fact_kehadiran.schedule import (
    resolve_schedule,
)

from etl.transform.fact_kehadiran.libur_shift import (
    resolve_libur_shift,
)

from etl.transform.fact_kehadiran.attendance import (
    aggregate_attendance,
)

from etl.transform.fact_kehadiran.rules import (
    apply_expected_workday_rule,
    apply_attendance_status_rule,
    apply_time_compliance_rule,
)

from etl.transform.fact_kehadiran.assembler import (
    assemble_fact_rows,
    project_fact_kehadiran_rows,
    validate_final_fact_rows,
)

from etl.load.fact_kehadiran import (
    load_fact_kehadiran,
)

from etl.control.run_log import (
    start_run,
    finish_run_success,
    finish_run_failed,
)

from etl.pipeline.fact_perizinan.pipeline import (
    prepare_fact_perizinan,
)

from etl.transform.fact_kehadiran.leave import (
    attach_daily_leave_coverage,
)

def run_fact_kehadiran_pipeline(
    start_date,
    end_date,
    config=None,
):
    if config is None:
        config = get_default_config()

    validate_config(config)

    if start_date > end_date:
        raise ValueError(
            "start_date tidak boleh lebih besar "
            "dari end_date"
        )

    oltp_conn = get_oltp_connection()
    olap_conn = get_olap_connection()

    run_id = None

    try:
        # ==========================================
        # EXTRACT
        # ==========================================

        pegawai_rows = extract_pegawai(
            olap_conn
        )

        calendar_rows = extract_calendar(
            olap_conn,
            start_date,
            end_date,
        )

        schedule_rows = extract_schedule(
            olap_conn
        )

        libur_shift_rows = extract_libur_shift(
            oltp_conn,
            start_date,
            end_date,
        )

        attendance_raw_rows = extract_attendance(
            oltp_conn,
            start_date,
            end_date,
            work_code=config.work_code,
        )

        # ==========================================
        # VALID DAILY LEAVE COVERAGE
        # ==========================================

        _, daily_leave_rows = prepare_fact_perizinan(
            oltp_conn,
            olap_conn,
        )

        daily_leave_rows = [
            row
            for row in daily_leave_rows
            if start_date <= row["tanggal"] <= end_date
        ]

        # ==========================================
        # EXPECTED EMPLOYEE-DAY
        # ==========================================

        employee_day_rows = build_employee_days(
            pegawai_rows,
            calendar_rows,
        )

        employee_day_rows = resolve_schedule(
            employee_day_rows,
            schedule_rows,
        )

        employee_day_rows = resolve_libur_shift(
            employee_day_rows,
            libur_shift_rows,
        )

        employee_day_rows = (
            apply_expected_workday_rule(
                employee_day_rows
            )
        )

        # ==========================================
        # ACTUAL ATTENDANCE
        # ==========================================

        attendance_daily_rows = (
            aggregate_attendance(
                attendance_raw_rows
            )
        )

        # ==========================================
        # EXPECTED + ACTUAL
        # ==========================================

        fact_rows = assemble_fact_rows(
            employee_day_rows,
            attendance_daily_rows,
        )
        
        # ==========================================
        # VALID LEAVE INTEGRATION
        # ==========================================

        fact_rows = attach_daily_leave_coverage(
            fact_rows,
            daily_leave_rows,
        )
        
        # ==========================================
        # BUSINESS RULE
        # ==========================================

        fact_rows = apply_attendance_status_rule(
            fact_rows
        )

        fact_rows = apply_time_compliance_rule(
            fact_rows
        )

        # ==========================================
        # FINAL PROJECTION
        # ==========================================

        fact_rows = project_fact_kehadiran_rows(
            fact_rows
        )

        validate_final_fact_rows(
            fact_rows
        )

        # ==========================================
        # DRY RUN
        # ==========================================

        if config.dry_run or not config.enable_write:
            print(
                "=== FACT KEHADIRAN DRY RUN ==="
            )

            print(
                f"Periode             : "
                f"{start_date} s.d. {end_date}"
            )

            print(
                f"Pegawai             : "
                f"{len(pegawai_rows)}"
            )

            print(
                f"Calendar days       : "
                f"{len(calendar_rows)}"
            )

            print(
                f"Schedules           : "
                f"{len(schedule_rows)}"
            )

            print(
                f"Libur shift source  : "
                f"{len(libur_shift_rows)}"
            )

            print(
                f"Attendance events   : "
                f"{len(attendance_raw_rows)}"
            )

            print(
                f"Attendance daily    : "
                f"{len(attendance_daily_rows)}"
            )

            print(
                f"Final fact rows     : "
                f"{len(fact_rows)}"
            )

            print()
            print(
                "DRY RUN SUCCESS - "
                "tidak ada data yang ditulis ke OLAP."
            )

            return fact_rows

        # ==========================================
        # WRITE MODE
        # ==========================================

        run_id = start_run(
            olap_conn,
            "fact_kehadiran",
        )

        olap_conn.commit()

        inserted, updated = load_fact_kehadiran(
            olap_conn,
            fact_rows,
        )

        finish_run_success(
            olap_conn,
            run_id,
            rows_extracted=len(
                attendance_raw_rows
            ),
            rows_inserted=inserted,
            rows_updated=updated,
        )

        olap_conn.commit()

        print(
            "Pipeline fact_kehadiran SUCCESS | "
            f"Fact rows: {len(fact_rows)} | "
            f"Inserted: {inserted} | "
            f"Updated: {updated}"
        )

        return fact_rows

    except Exception as e:
        olap_conn.rollback()

        if run_id is not None:
            finish_run_failed(
                olap_conn,
                run_id,
                str(e),
            )

            olap_conn.commit()

        print(
            f"Pipeline fact_kehadiran FAILED: {e}"
        )

        raise

    finally:
        oltp_conn.close()
        olap_conn.close()
