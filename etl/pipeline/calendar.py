from datetime import date

from etl.connectors.oltp import get_oltp_connection
from etl.connectors.olap import get_olap_connection

from etl.extract.calendar import extract_hari_libur
from etl.transform.calendar import transform_calendar
from etl.load.calendar import load_calendar

from etl.control.run_log import (
    start_run,
    finish_run_success,
    finish_run_failed,
)


def run_calendar_pipeline():
    pipeline_name = "calendar"

    oltp_conn = get_oltp_connection()
    olap_conn = get_olap_connection()

    run_id = None

    try:
        run_id = start_run(olap_conn, pipeline_name)
        olap_conn.commit()

        holiday_rows = extract_hari_libur(oltp_conn)

        transformed_rows = transform_calendar(
            holiday_rows,
            start_date=date(2020, 1, 1),
            end_date=date(2035, 12, 31),
        )

        inserted, updated = load_calendar(
            olap_conn,
            transformed_rows,
        )

        finish_run_success(
            olap_conn,
            run_id,
            rows_extracted=len(holiday_rows),
            rows_inserted=inserted,
            rows_updated=updated,
        )

        olap_conn.commit()

        print(
            f"Pipeline calendar SUCCESS | "
            f"Holiday rows extracted: {len(holiday_rows)} | "
            f"Calendar rows: {len(transformed_rows)} | "
            f"Inserted: {inserted} | "
            f"Updated: {updated}"
        )

    except Exception as e:
        olap_conn.rollback()

        if run_id is not None:
            finish_run_failed(
                olap_conn,
                run_id,
                str(e),
            )
            olap_conn.commit()

        print(f"Pipeline calendar FAILED: {e}")
        raise

    finally:
        oltp_conn.close()
        olap_conn.close()


if __name__ == "__main__":
    run_calendar_pipeline()
