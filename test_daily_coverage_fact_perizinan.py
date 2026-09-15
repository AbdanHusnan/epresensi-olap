from etl.connectors.oltp import get_oltp_connection
from etl.extract.fact_perizinan.extract_perizinan import extract_perizinan
from etl.transform.fact_perizinan.normalize import normalize_perizinan_rows
from etl.transform.fact_perizinan.approval import apply_approval_rules
from etl.transform.fact_perizinan.daily_coverage import (
    build_daily_leave_coverage,
)


def main():
    conn = get_oltp_connection()

    try:
        source_rows = extract_perizinan(conn)

        rows = normalize_perizinan_rows(source_rows)

        rows = apply_approval_rules(rows)

        coverage_rows = build_daily_leave_coverage(rows)

        approved = sum(
            row["is_izin_valid"]
            for row in rows
        )

        multi_day = sum(
            row["is_izin_valid"]
            and row["tgl_izin_sampai"] > row["tgl_izin_mulai"]
            for row in rows
        )

        print(f"Total pengajuan      : {len(rows)}")
        print(f"Approved             : {approved}")
        print(f"Approved multi-day   : {multi_day}")
        print(f"Daily coverage rows  : {len(coverage_rows)}")

        print("\nSample coverage:")

        for row in coverage_rows[:10]:
            print(row)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
