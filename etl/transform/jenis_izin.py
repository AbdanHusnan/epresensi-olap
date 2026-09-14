def transform_jenis_izin(
    jenis_rows,
    tipe_rows,
):
    tipe_map = {
        row["id"]: row
        for row in tipe_rows
    }

    result = []

    for row in jenis_rows:
        tipe = tipe_map.get(row["tipe_id"])

        result.append(
            {
                "jenis_izin_id": row["id"],
                "tipe_izin_id": row["tipe_id"],
                "kode_jenis_izin": row["kode"],
                "nama_jenis_izin": row["nama"],
                "nama_tipe_izin": (
                    tipe["nama"]
                    if tipe is not None
                    else None
                ),
                "source_updated_at": row["created_at"],
            }
        )

    return result
