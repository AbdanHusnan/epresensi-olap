from etl.connectors.oltp import get_oltp_connection
from etl.connectors.olap import get_olap_connection

from etl.extract.departemen import extract_departemen
from etl.transform.departemen import transform_departemen
from etl.load.departemen import load_departemen

from etl.control.run_log import (
    start_run,
    finish_run_success,
    finish_run_failed,
)


def run_departemen_pipeline():
    pipeline_name = "departemen"

    oltp_conn = get_oltp_connection()
    olap_conn = get_olap_connection()

    run_id = None

    try:
        run_id = start_run(olap_conn, pipeline_name)
        olap_conn.commit()

        extracted_rows = extract_departemen(oltp_conn)

        transformed_rows = transform_departemen(extracted_rows)

        inserted, updated = load_departemen(
            olap_conn,
            transformed_rows,
        )

        finish_run_success(
            olap_conn,
            run_id,
            rows_extracted=len(extracted_rows),
            rows_inserted=inserted,
            rows_updated=updated,
        )

        olap_conn.commit()

        print(
            f"Pipeline departemen SUCCESS | "
            f"Extracted: {len(extracted_rows)} | "
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

        print(f"Pipeline departemen FAILED: {e}")
        raise

    finally:
        oltp_conn.close()
        olap_conn.close()


if __name__ == "__main__":
    run_departemen_pipeline()
