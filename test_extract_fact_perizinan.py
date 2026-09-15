from etl.connectors.oltp import get_oltp_connection
from etl.extract.fact_perizinan.extract_perizinan import extract_perizinan


def main():
    conn = get_oltp_connection()

    try:
        rows = extract_perizinan(conn)

        print(f"Extracted rows: {len(rows)}")

        for row in rows[:5]:
            print(row)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
