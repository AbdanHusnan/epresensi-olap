def extract_shift(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM m_shift
            ORDER BY id
            """
        )

        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    return [
        dict(zip(columns, row))
        for row in rows
    ]


def extract_jadwal(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM m_jadwal
            ORDER BY id
            """
        )

        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    return [
        dict(zip(columns, row))
        for row in rows
    ]
