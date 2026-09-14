def transform_pegawai(rows):
    result = []

    for row in rows:
        source_updated_at = (
            row["updated_at"]
            if row["updated_at"] is not None
            else row["created_at"]
        )

        result.append(
            {
                "pegawai_id": row["id"],
                "departemen_id": row["departemen"],
                "nip": row["nip"],
                "nama_pegawai": row["nama"],

                # Belum ada source field yang terbukti
                # merepresentasikan aktif/nonaktif pegawai.
                "status_aktif": None,

                "source_updated_at": source_updated_at,
            }
        )

    return result
