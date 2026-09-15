def extract_pegawai_reference(conn):
    """
    Mengambil pegawai dan departemen dari analytical dimension.

    Output:
        {
            pegawai_id: departemen_id
        }
    """

    query = """
        SELECT
            pegawai_id,
            departemen_id
        FROM dim_pegawai
    """

    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    return {
        pegawai_id: departemen_id
        for pegawai_id, departemen_id in rows
    }


def extract_jenis_izin_reference(conn):
    """
    Mengambil seluruh jenis izin dari analytical dimension.

    Output:
        set jenis_izin_id
    """

    query = """
        SELECT jenis_izin_id
        FROM dim_jenis_izin
    """

    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    return {
        row[0]
        for row in rows
    }
