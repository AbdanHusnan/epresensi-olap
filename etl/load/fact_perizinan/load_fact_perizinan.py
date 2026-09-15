def load_fact_perizinan(conn, rows):
    """
    Load / upsert fact_perizinan ke OLAP.

    Grain:
        1 row = 1 pengajuan izin

    Conflict key:
        perizinan_id
    """

    if not rows:
        return 0

    query = """
        INSERT INTO fact_perizinan (
            perizinan_id,
            pegawai_id,
            departemen_id,
            jenis_izin_id,
            tanggal_pengajuan,
            tanggal_mulai,
            tanggal_selesai,
            jumlah_hari,
            status_pengajuan,
            is_approved,
            is_valid_leave,
            alasan,
            source_updated_at
        )
        VALUES (
            %(perizinan_id)s,
            %(pegawai_id)s,
            %(departemen_id)s,
            %(jenis_izin_id)s,
            %(tanggal_pengajuan)s,
            %(tanggal_mulai)s,
            %(tanggal_selesai)s,
            %(jumlah_hari)s,
            %(status_pengajuan)s,
            %(is_approved)s,
            %(is_valid_leave)s,
            %(alasan)s,
            %(source_updated_at)s
        )

        ON CONFLICT (perizinan_id)
        DO UPDATE SET
            pegawai_id =
                EXCLUDED.pegawai_id,

            departemen_id =
                EXCLUDED.departemen_id,

            jenis_izin_id =
                EXCLUDED.jenis_izin_id,

            tanggal_pengajuan =
                EXCLUDED.tanggal_pengajuan,

            tanggal_mulai =
                EXCLUDED.tanggal_mulai,

            tanggal_selesai =
                EXCLUDED.tanggal_selesai,

            jumlah_hari =
                EXCLUDED.jumlah_hari,

            status_pengajuan =
                EXCLUDED.status_pengajuan,

            is_approved =
                EXCLUDED.is_approved,

            is_valid_leave =
                EXCLUDED.is_valid_leave,

            alasan =
                EXCLUDED.alasan,

            source_updated_at =
                EXCLUDED.source_updated_at,

            etl_loaded_at =
                CURRENT_TIMESTAMP
    """

    with conn.cursor() as cur:
        cur.executemany(
            query,
            rows,
        )

    return len(rows)
