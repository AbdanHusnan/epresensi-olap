from etl.connectors.oltp import get_oltp_connection
from etl.connectors.olap import get_olap_connection

from etl.extract.jadwal_kerja import (
    extract_shift,
    extract_jadwal,
)
from etl.transform.jadwal_kerja import transform_jadwal_kerja
from etl.load.jadwal_kerja import load_jadwal_kerja

from etl.control.run_log import (
    start_run,
    finish_run_success,
    finish_run_failed,
)


def run_jadwal_kerja_pipeline():
    pipeline_name = "jadwal_kerja"

    oltp_conn = get_oltp_connection()
    olap_conn = get_olap_connection()

    run_id = None

    try:
        run_id = start_run(olap_conn, pipeline_name)
        olap_conn.commit()

        shift_rows = extract_shift(oltp_conn)
        jadwal_rows = extract_jadwal(oltp_conn)

        transformed_rows = transform_jadwal_kerja(
            jadwal_rows,
            shift_rows,
        )

        inserted, updated = load_jadwal_kerja(
            olap_conn,
            transformed_rows,
        )

        finish_run_success(
            olap_conn,
            run_id,
            rows_extracted=len(jadwal_rows),
            rows_inserted=inserted,
            rows_updated=updated,
        )

        olap_conn.commit()

        print(
            f"Pipeline jadwal_kerja SUCCESS | "
            f"Extracted: {len(jadwal_rows)} | "
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

        print(f"Pipeline jadwal_kerja FAILED: {e}")
        raise

    finally:
        oltp_conn.close()
        olap_conn.close()


if __name__ == "__main__":
    run_jadwal_kerja_pipeline()
