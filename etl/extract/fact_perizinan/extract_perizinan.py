def extract_perizinan(conn):
    """
    Extract data pengajuan izin dari OLTP.

    Grain source:
        1 row = 1 pengajuan izin
    """

    query = """
        SELECT
            id,
            pegawai_id,
            tipe_ijin,
            jenis_ijin,
            alasan,
            approval,
            approval_at,
            tgl_ijin,
            tgl_ijin_sampai,
            created_at,
            updated_at
        FROM t_perizinan
        ORDER BY id
    """

    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

        columns = [
            desc.name
            for desc in cur.description
        ]

    return [
        dict(zip(columns, row))
        for row in rows
    ]