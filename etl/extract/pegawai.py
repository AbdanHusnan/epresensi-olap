def extract_pegawai(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM m_pegawai
            ORDER BY id
            """
        )

        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    return [
        dict(zip(columns, row))
        for row in rows
    ]
