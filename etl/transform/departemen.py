import hashlib


def transform_departemen(rows):
    result = []

    for row in rows:
        source_hash = hashlib.md5(
            f"{row['id']}|{row['kode']}|{row['nama_departemen']}".encode()
        ).hexdigest()

        result.append(
            {
                "departemen_id": row["id"],
                "kode_departemen": row["kode"],
                "nama_departemen": row["nama_departemen"],
                "source_hash": source_hash,
            }
        )

    return result
