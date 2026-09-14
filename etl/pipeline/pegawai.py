from etl.connectors.oltp import get_oltp_connection
from etl.connectors.olap import get_olap_connection

from etl.extract.pegawai import extract_pegawai
from etl.transform.pegawai import transform_pegawai
from etl.load.pegawai import load_pegawai

from etl.control.run_log import (
    start_run,
    finish_run_success,
    finish_run_failed,
)


def run_pegawai_pipeline():
    pipeline_name = "pegawai"

    oltp_conn = get_oltp_connection()
    olap_conn = get_olap_connection()

    run_id = None

    try:
        run_id = start_run(olap_conn, pipeline_name)
        olap_conn.commit()

        extracted_rows = extract_pegawai(oltp_conn)

        transformed_rows = transform_pegawai(
            extracted_rows
        )

        inserted, updated = load_pegawai(
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
            f"Pipeline pegawai SUCCESS | "
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

        print(f"Pipeline pegawai FAILED: {e}")
        raise

    finally:
        oltp_conn.close()
        olap_conn.close()


if __name__ == "__main__":
    run_pegawai_pipeline()
