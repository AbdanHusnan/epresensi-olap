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


def main():
    oltp_conn = get_oltp_connection()
    olap_conn = get_olap_connection()

    try:
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

        fact_rows = build_fact_perizinan_rows(
            rows
        )

        validate_fact_perizinan_rows(
            fact_rows
        )

        approved = sum(
            row["status_pengajuan"] == "APPROVED"
            for row in fact_rows
        )

        rejected = sum(
            row["status_pengajuan"] == "REJECTED"
            for row in fact_rows
        )

        pending = sum(
            row["status_pengajuan"] == "PENDING"
            for row in fact_rows
        )

        multi_day = sum(
            row["jumlah_hari"] > 1
            for row in fact_rows
        )

        print("FINAL VALIDATION PASSED")
        print(
            f"Source rows   : {len(source_rows)}"
        )
        print(
            f"Fact rows     : {len(fact_rows)}"
        )
        print(
            f"Approved      : {approved}"
        )
        print(
            f"Rejected      : {rejected}"
        )
        print(
            f"Pending       : {pending}"
        )
        print(
            f"Multi-day     : {multi_day}"
        )

    finally:
        oltp_conn.close()
        olap_conn.close()


if __name__ == "__main__":
    main()
