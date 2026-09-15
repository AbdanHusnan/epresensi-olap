from etl.connectors.oltp import get_oltp_connection
from etl.extract.fact_perizinan.extract_perizinan import extract_perizinan
from etl.transform.fact_perizinan.normalize import normalize_perizinan_rows


def main():
    conn = get_oltp_connection()

    try:
        rows = extract_perizinan(conn)

        normalized_rows = normalize_perizinan_rows(rows)

        print(f"Source rows     : {len(rows)}")
        print(f"Normalized rows : {len(normalized_rows)}")

        for row in normalized_rows[:5]:
            print(row)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
