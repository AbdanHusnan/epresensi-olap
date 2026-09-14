from connectors.olap import get_olap_connection


def test_write_olap():
    try:
        with get_olap_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS connector_test (
                        id SERIAL PRIMARY KEY,
                        message TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                cur.execute("""
                    INSERT INTO connector_test (message)
                    VALUES (%s)
                    RETURNING id, message, created_at;
                """, ("ETL connector test",))

                result = cur.fetchone()

                print("OLAP WRITE TEST : OK")
                print(f"ID              : {result[0]}")
                print(f"Message         : {result[1]}")
                print(f"Created At      : {result[2]}")

                cur.execute("""
                    DELETE FROM connector_test
                    WHERE id = %s;
                """, (result[0],))

                cur.execute("""
                    DROP TABLE connector_test;
                """)

            conn.commit()

        print("Cleanup         : OK")

    except Exception as error:
        print("OLAP WRITE TEST : FAILED")
        print(error)


if __name__ == "__main__":
    test_write_olap()
