from connectors.oltp import get_oltp_connection
from connectors.olap import get_olap_connection


def test_connection(name, connection_func):
    try:
        with connection_func() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        current_database(),
                        current_user,
                        version();
                """)

                database, user, version = cur.fetchone()

                print(f"{name} CONNECTION : OK")
                print(f"Database          : {database}")
                print(f"User              : {user}")
                print(f"PostgreSQL        : {version.split(',')[0]}")

    except Exception as error:
        print(f"{name} CONNECTION : FAILED")
        print(error)


if __name__ == "__main__":
    print("\n=== TEST OLTP ===")
    test_connection("OLTP", get_oltp_connection)

    print("\n=== TEST OLAP ===")
    test_connection("OLAP", get_olap_connection)
