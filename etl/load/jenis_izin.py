def load_jenis_izin(conn, rows):
    inserted = 0
    updated = 0

    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO dim_jenis_izin (
                    jenis_izin_id,
                    tipe_izin_id,
                    kode_jenis_izin,
                    nama_jenis_izin,
                    nama_tipe_izin,
                    source_updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (jenis_izin_id)
                DO UPDATE SET
                    tipe_izin_id = EXCLUDED.tipe_izin_id,
                    kode_jenis_izin = EXCLUDED.kode_jenis_izin,
                    nama_jenis_izin = EXCLUDED.nama_jenis_izin,
                    nama_tipe_izin = EXCLUDED.nama_tipe_izin,
                    source_updated_at = EXCLUDED.source_updated_at,
                    etl_loaded_at = CURRENT_TIMESTAMP
                WHERE ROW(
                    dim_jenis_izin.tipe_izin_id,
                    dim_jenis_izin.kode_jenis_izin,
                    dim_jenis_izin.nama_jenis_izin,
                    dim_jenis_izin.nama_tipe_izin,
                    dim_jenis_izin.source_updated_at
                )
                IS DISTINCT FROM ROW(
                    EXCLUDED.tipe_izin_id,
                    EXCLUDED.kode_jenis_izin,
                    EXCLUDED.nama_jenis_izin,
                    EXCLUDED.nama_tipe_izin,
                    EXCLUDED.source_updated_at
                )
                RETURNING (xmax = 0) AS inserted
                """,
                (
                    row["jenis_izin_id"],
                    row["tipe_izin_id"],
                    row["kode_jenis_izin"],
                    row["nama_jenis_izin"],
                    row["nama_tipe_izin"],
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
