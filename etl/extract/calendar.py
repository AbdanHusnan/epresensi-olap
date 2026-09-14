def extract_hari_libur(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                tanggal,
                STRING_AGG(
                    DISTINCT keterangan,
                    '; '
                    ORDER BY keterangan
                ) AS keterangan
            FROM m_hari_libur
            GROUP BY tanggal
            ORDER BY tanggal
            """
        )

        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    return [
        dict(zip(columns, row))
        for row in rows
    ]
