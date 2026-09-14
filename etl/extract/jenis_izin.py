def extract_jenis_izin(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM m_jenis_ijin
            ORDER BY id
            """
        )

        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    return [
        dict(zip(columns, row))
        for row in rows
    ]


def extract_tipe_izin(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM m_tipe_ijin
            ORDER BY id
            """
        )

        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    return [
        dict(zip(columns, row))
        for row in rows
    ]
