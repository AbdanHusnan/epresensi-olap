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


def main():
    oltp_conn = get_oltp_connection()
    olap_conn = get_olap_connection()

    try:
        source_rows = extract_perizinan(oltp_conn)

        rows = normalize_perizinan_rows(source_rows)

        rows = apply_approval_rules(rows)

        pegawai_reference = extract_pegawai_reference(
            olap_conn
        )

        jenis_izin_reference = extract_jenis_izin_reference(
            olap_conn
        )

        rows = resolve_perizinan_dimensions_rows(
            rows,
            pegawai_reference,
            jenis_izin_reference,
        )

        print(f"Resolved rows : {len(rows)}")

        null_departemen = sum(
            row["departemen_id"] is None
            for row in rows
        )

        print(
            f"Departemen NULL : {null_departemen}"
        )

        print("\nSample:")

        for row in rows[:5]:
            print({
                "perizinan_id":
                    row["source_perizinan_id"],
                "pegawai_id":
                    row["pegawai_id"],
                "departemen_id":
                    row["departemen_id"],
                "jenis_izin_id":
                    row["jenis_izin_id"],
            })

    finally:
        oltp_conn.close()
        olap_conn.close()


if __name__ == "__main__":
    main()
