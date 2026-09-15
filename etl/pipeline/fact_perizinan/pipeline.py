from etl.connectors.oltp import get_oltp_connection
from etl.connectors.olap import get_olap_connection

from etl.extract.fact_perizinan.extract_perizinan import (
    extract_perizinan,
)

from etl.extract.fact_perizinan.extract_reference import (
    extract_pegawai_reference,
    extract_jenis_izin_reference,
)

from etl.transform.fact_perizinan.normalize import (
    normalize_perizinan_rows,
)

from etl.transform.fact_perizinan.approval import (
    apply_approval_rules,
)

from etl.transform.fact_perizinan.dimensions import (
    resolve_perizinan_dimensions_rows,
)

from etl.transform.fact_perizinan.build_fact import (
    build_fact_perizinan_rows,
)

from etl.transform.fact_perizinan.final_validation import (
    validate_fact_perizinan_rows,
)

from etl.transform.fact_perizinan.daily_coverage import (
    build_daily_leave_coverage,
)

from etl.load.fact_perizinan.load_fact_perizinan import (
    load_fact_perizinan,
)


def prepare_fact_perizinan(
    oltp_conn,
    olap_conn,
):
    """
    Extract + transform + validate fact_perizinan.

    Tidak menulis ke database OLAP.
    """

    source_rows = extract_perizinan(
        oltp_conn
    )

    rows = normalize_perizinan_rows(
        source_rows
    )

    rows = apply_approval_rules(
        rows
    )

    pegawai_reference = (
        extract_pegawai_reference(
            olap_conn
        )
    )

    jenis_izin_reference = (
        extract_jenis_izin_reference(
            olap_conn
        )
    )

    rows = resolve_perizinan_dimensions_rows(
        rows,
        pegawai_reference,
        jenis_izin_reference,
    )

    # Daily coverage dibuat dari row transform
    # sebelum row dibentuk menjadi physical fact.
    daily_coverage = build_daily_leave_coverage(
        rows
    )

    fact_rows = build_fact_perizinan_rows(
        rows
    )

    validate_fact_perizinan_rows(
        fact_rows
    )

    return fact_rows, daily_coverage


def run_fact_perizinan_pipeline(
    dry_run=True,
):
    """
    Pipeline utama fact_perizinan.

    dry_run=True:
        extract + transform + validation saja.

    dry_run=False:
        melakukan UPSERT ke fact_perizinan.
    """

    oltp_conn = get_oltp_connection()
    olap_conn = get_olap_connection()

    try:
        fact_rows, daily_coverage = (
            prepare_fact_perizinan(
                oltp_conn,
                olap_conn,
            )
        )

        result = {
            "fact_rows": len(fact_rows),
            "daily_coverage_rows":
                len(daily_coverage),
            "loaded_rows": 0,
            "dry_run": dry_run,
        }

        if dry_run:
            return result

        loaded_rows = load_fact_perizinan(
            olap_conn,
            fact_rows,
        )

        olap_conn.commit()

        result["loaded_rows"] = loaded_rows

        return result

    except Exception:
        olap_conn.rollback()
        raise

    finally:
        oltp_conn.close()
        olap_conn.close()
