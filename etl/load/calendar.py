def load_calendar(conn, rows):
    inserted = 0
    updated = 0

    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO dim_calendar (
                    tanggal,
                    tahun,
                    bulan,
                    nama_bulan,
                    hari,
                    nama_hari,
                    minggu_ke,
                    kuartal,
                    is_weekend,
                    is_hari_libur,
                    keterangan_libur
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (tanggal)
                DO UPDATE SET
                    tahun = EXCLUDED.tahun,
                    bulan = EXCLUDED.bulan,
                    nama_bulan = EXCLUDED.nama_bulan,
                    hari = EXCLUDED.hari,
                    nama_hari = EXCLUDED.nama_hari,
                    minggu_ke = EXCLUDED.minggu_ke,
                    kuartal = EXCLUDED.kuartal,
                    is_weekend = EXCLUDED.is_weekend,
                    is_hari_libur = EXCLUDED.is_hari_libur,
                    keterangan_libur = EXCLUDED.keterangan_libur,
                    etl_loaded_at = CURRENT_TIMESTAMP
                WHERE ROW(
                    dim_calendar.tahun,
                    dim_calendar.bulan,
                    dim_calendar.nama_bulan,
                    dim_calendar.hari,
                    dim_calendar.nama_hari,
                    dim_calendar.minggu_ke,
                    dim_calendar.kuartal,
                    dim_calendar.is_weekend,
                    dim_calendar.is_hari_libur,
                    dim_calendar.keterangan_libur
                )
                IS DISTINCT FROM ROW(
                    EXCLUDED.tahun,
                    EXCLUDED.bulan,
                    EXCLUDED.nama_bulan,
                    EXCLUDED.hari,
                    EXCLUDED.nama_hari,
                    EXCLUDED.minggu_ke,
                    EXCLUDED.kuartal,
                    EXCLUDED.is_weekend,
                    EXCLUDED.is_hari_libur,
                    EXCLUDED.keterangan_libur
                )
                RETURNING (xmax = 0) AS inserted
                """,
                (
                    row["tanggal"],
                    row["tahun"],
                    row["bulan"],
                    row["nama_bulan"],
                    row["hari"],
                    row["nama_hari"],
                    row["minggu_ke"],
                    row["kuartal"],
                    row["is_weekend"],
                    row["is_hari_libur"],
                    row["keterangan_libur"],
                ),
            )

            result = cur.fetchone()

            if result is None:
                continue

            if result[0]:
                inserted += 1
            else:
                updated += 1

    return inserted, updated
