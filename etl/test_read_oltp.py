from connectors.oltp import get_oltp_connection


def test_read_oltp():
    try:
        with get_oltp_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    ORDER BY table_name;
                """)

                tables = cur.fetchall()

                print("OLTP READ TEST : OK")
                print(f"Total tables   : {len(tables)}")
                print("\nSample tables:")

                for row in tables[:10]:
                    print(f"- {row[0]}")

    except Exception as error:
        print("OLTP READ TEST : FAILED")
        print(error)


if __name__ == "__main__":
    test_read_oltp()
