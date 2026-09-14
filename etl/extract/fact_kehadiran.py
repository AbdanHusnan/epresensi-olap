def extract_pegawai(olap_conn):
    """
    Mengambil pegawai dari analytical dimension.

    Sumber:
        dim_pegawai

    Belum melakukan filter status aktif karena source field
    aktif/nonaktif pegawai belum terbukti tersedia.
    """
    with olap_conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                pegawai_id,
                departemen_id,
                nip,
                nama_pegawai
            FROM dim_pegawai
            ORDER BY pegawai_id
            """
        )

        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    return [
        dict(zip(columns, row))
        for row in rows
    ]


def extract_calendar(olap_conn, start_date, end_date):
    """
    Mengambil tanggal yang akan diproses.

    Periode wajib diberikan agar pipeline fact tidak
    membaca seluruh dim_calendar tanpa batas.
    """
    with olap_conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                tanggal,
                hari,
                nama_hari,
                is_weekend,
                is_hari_libur,
                keterangan_libur
            FROM dim_calendar
            WHERE tanggal BETWEEN %s AND %s
            ORDER BY tanggal
            """,
            (
                start_date,
                end_date,
            ),
        )

        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    return [
        dict(zip(columns, row))
        for row in rows
    ]


def extract_libur_shift(oltp_conn, start_date, end_date):
    """
    Mengambil libur shift individual pegawai.

    Grain yang relevan untuk fact:
        pegawai_id + tanggal

    departemen_id tetap diambil sebagai context,
    tetapi bukan rule bahwa seluruh departemen libur.
    """
    with oltp_conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                departemen_id,
                pegawai_id,
                tanggal,
                keterangan,
                created_at,
                updated_at
            FROM t_libur_shift
            WHERE tanggal BETWEEN %s AND %s
            ORDER BY tanggal, pegawai_id, id
            """,
            (
                start_date,
                end_date,
            ),
        )

        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    return [
        dict(zip(columns, row))
        for row in rows
    ]


def extract_attendance(
    oltp_conn,
    start_date,
    end_date,
    work_code=1,
):
    """
    Mengambil raw attendance event dari t_checkinout.

    Rule tahap ini:
        work_code = 1

    checktype tidak digunakan.
    Kolom izin pada t_checkinout juga tidak digunakan.
    """
    with oltp_conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                pegawai_id,
                departemen,
                work_code,
                is_wfh,
                created_at,
                updated_at
            FROM t_checkinout
            WHERE work_code = %s
              AND created_at >= %s::date
              AND created_at < (%s::date + INTERVAL '1 day')
            ORDER BY pegawai_id, created_at, id
            """,
            (
                work_code,
                start_date,
                end_date,
            ),
        )

        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    return [
        dict(zip(columns, row))
        for row in rows
    ]

def extract_schedule(olap_conn):
    """
    Mengambil analytical work schedule.

    dim_jadwal_kerja.hari diasumsikan sudah berada
    dalam canonical format:
        Senin, Selasa, Rabu, Kamis,
        Jumat, Sabtu, Minggu.
    """
    with olap_conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                jadwal_id,
                shift_id,
                departemen_id,
                nama_shift,
                hari,
                jam_masuk,
                jam_keluar,
                jam_masuk_awal,
                jam_keluar_akhir,
                is_flexible
            FROM dim_jadwal_kerja
            ORDER BY
                departemen_id,
                hari,
                jadwal_id
            """
        )

        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    return [
        dict(zip(columns, row))
        for row in rows
    ]
