from etl.connectors.oltp import get_oltp_connection
from etl.extract.fact_perizinan.extract_perizinan import extract_perizinan
from etl.transform.fact_perizinan.normalize import normalize_perizinan_rows
from etl.transform.fact_perizinan.approval import apply_approval_rules


def main():
    conn = get_oltp_connection()

    try:
        source_rows = extract_perizinan(conn)

        rows = normalize_perizinan_rows(source_rows)

        rows = apply_approval_rules(rows)

        approved = sum(
            row["status_perizinan"] == "APPROVED"
            for row in rows
        )

        rejected = sum(
            row["status_perizinan"] == "REJECTED"
            for row in rows
        )

        pending = sum(
            row["status_perizinan"] == "PENDING"
            for row in rows
        )

        valid_leave = sum(
            row["is_izin_valid"]
            for row in rows
        )

        print(f"Total       : {len(rows)}")
        print(f"Approved    : {approved}")
        print(f"Rejected    : {rejected}")
        print(f"Pending     : {pending}")
        print(f"Valid leave : {valid_leave}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
