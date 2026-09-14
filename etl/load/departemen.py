def load_departemen(conn, rows):
    inserted = 0
    updated = 0

    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO dim_departemen (
                    departemen_id,
                    kode_departemen,
                    nama_departemen,
                    source_hash
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (departemen_id)
                DO UPDATE SET
                    kode_departemen = EXCLUDED.kode_departemen,
                    nama_departemen = EXCLUDED.nama_departemen,
                    source_hash = EXCLUDED.source_hash
                WHERE dim_departemen.source_hash IS DISTINCT FROM EXCLUDED.source_hash
                RETURNING (xmax = 0) AS inserted
                """,
                (
                    row["departemen_id"],
                    row["kode_departemen"],
                    row["nama_departemen"],
                    row["source_hash"],
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
