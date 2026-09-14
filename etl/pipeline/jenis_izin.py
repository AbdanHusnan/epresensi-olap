from etl.connectors.oltp import get_oltp_connection
from etl.connectors.olap import get_olap_connection

from etl.extract.jenis_izin import (
    extract_jenis_izin,
    extract_tipe_izin,
)
from etl.transform.jenis_izin import transform_jenis_izin
from etl.load.jenis_izin import load_jenis_izin

from etl.control.run_log import (
    start_run,
    finish_run_success,
    finish_run_failed,
)


def run_jenis_izin_pipeline():
    pipeline_name = "jenis_izin"

    oltp_conn = get_oltp_connection()
    olap_conn = get_olap_connection()

    run_id = None

    try:
        run_id = start_run(olap_conn, pipeline_name)
        olap_conn.commit()

        jenis_rows = extract_jenis_izin(oltp_conn)
        tipe_rows = extract_tipe_izin(oltp_conn)

        transformed_rows = transform_jenis_izin(
            jenis_rows,
            tipe_rows,
        )

        inserted, updated = load_jenis_izin(
            olap_conn,
            transformed_rows,
        )

        finish_run_success(
            olap_conn,
            run_id,
            rows_extracted=len(jenis_rows),
            rows_inserted=inserted,
            rows_updated=updated,
        )

        olap_conn.commit()

        print(
            f"Pipeline jenis_izin SUCCESS | "
            f"Extracted: {len(jenis_rows)} | "
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

        print(f"Pipeline jenis_izin FAILED: {e}")
        raise

    finally:
        oltp_conn.close()
        olap_conn.close()


if __name__ == "__main__":
    run_jenis_izin_pipeline()
