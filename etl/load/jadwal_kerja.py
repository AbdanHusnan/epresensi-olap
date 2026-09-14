def load_jadwal_kerja(conn, rows):
    inserted = 0
    updated = 0

    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO dim_jadwal_kerja (
                    jadwal_id,
                    shift_id,
                    departemen_id,
                    nama_shift,
                    hari,
                    jam_masuk,
                    jam_keluar,
                    jam_masuk_awal,
                    jam_keluar_akhir,
                    is_flexible,
                    source_updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (jadwal_id)
                DO UPDATE SET
                    shift_id = EXCLUDED.shift_id,
                    departemen_id = EXCLUDED.departemen_id,
                    nama_shift = EXCLUDED.nama_shift,
                    hari = EXCLUDED.hari,
                    jam_masuk = EXCLUDED.jam_masuk,
                    jam_keluar = EXCLUDED.jam_keluar,
                    jam_masuk_awal = EXCLUDED.jam_masuk_awal,
                    jam_keluar_akhir = EXCLUDED.jam_keluar_akhir,
                    is_flexible = EXCLUDED.is_flexible,
                    source_updated_at = EXCLUDED.source_updated_at,
                    etl_loaded_at = CURRENT_TIMESTAMP
                WHERE ROW(
                    dim_jadwal_kerja.shift_id,
                    dim_jadwal_kerja.departemen_id,
                    dim_jadwal_kerja.nama_shift,
                    dim_jadwal_kerja.hari,
                    dim_jadwal_kerja.jam_masuk,
                    dim_jadwal_kerja.jam_keluar,
                    dim_jadwal_kerja.jam_masuk_awal,
                    dim_jadwal_kerja.jam_keluar_akhir,
                    dim_jadwal_kerja.is_flexible,
                    dim_jadwal_kerja.source_updated_at
                )
                IS DISTINCT FROM ROW(
                    EXCLUDED.shift_id,
                    EXCLUDED.departemen_id,
                    EXCLUDED.nama_shift,
                    EXCLUDED.hari,
                    EXCLUDED.jam_masuk,
                    EXCLUDED.jam_keluar,
                    EXCLUDED.jam_masuk_awal,
                    EXCLUDED.jam_keluar_akhir,
                    EXCLUDED.is_flexible,
                    EXCLUDED.source_updated_at
                )
                RETURNING (xmax = 0) AS inserted
                """,
                (
                    row["jadwal_id"],
                    row["shift_id"],
                    row["departemen_id"],
                    row["nama_shift"],
                    row["hari"],
                    row["jam_masuk"],
                    row["jam_keluar"],
                    row["jam_masuk_awal"],
                    row["jam_keluar_akhir"],
                    row["is_flexible"],
                    row["source_updated_at"],
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
