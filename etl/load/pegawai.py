def load_pegawai(conn, rows):
    inserted = 0
    updated = 0

    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO dim_pegawai (
                    pegawai_id,
                    departemen_id,
                    nip,
                    nama_pegawai,
                    status_aktif,
                    source_updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (pegawai_id)
                DO UPDATE SET
                    departemen_id = EXCLUDED.departemen_id,
                    nip = EXCLUDED.nip,
                    nama_pegawai = EXCLUDED.nama_pegawai,
                    status_aktif = EXCLUDED.status_aktif,
                    source_updated_at = EXCLUDED.source_updated_at,
                    etl_loaded_at = CURRENT_TIMESTAMP
                WHERE ROW(
                    dim_pegawai.departemen_id,
                    dim_pegawai.nip,
                    dim_pegawai.nama_pegawai,
                    dim_pegawai.status_aktif,
                    dim_pegawai.source_updated_at
                )
                IS DISTINCT FROM ROW(
                    EXCLUDED.departemen_id,
                    EXCLUDED.nip,
                    EXCLUDED.nama_pegawai,
                    EXCLUDED.status_aktif,
                    EXCLUDED.source_updated_at
                )
                RETURNING (xmax = 0) AS inserted
                """,
                (
                    row["pegawai_id"],
                    row["departemen_id"],
                    row["nip"],
                    row["nama_pegawai"],
                    row["status_aktif"],
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
