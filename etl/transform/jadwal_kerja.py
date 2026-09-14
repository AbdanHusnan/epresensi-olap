HARI_MAP = {
    # Senin
    "senin": "Senin",
    "monday": "Senin",
    "mon": "Senin",

    # Selasa
    "selasa": "Selasa",
    "tuesday": "Selasa",
    "tue": "Selasa",
    "tues": "Selasa",

    # Rabu
    "rabu": "Rabu",
    "wednesday": "Rabu",
    "wed": "Rabu",

    # Kamis
    "kamis": "Kamis",
    "thursday": "Kamis",
    "thu": "Kamis",
    "thur": "Kamis",
    "thurs": "Kamis",

    # Jumat
    "jumat": "Jumat",
    "jum'at": "Jumat",
    "friday": "Jumat",
    "fri": "Jumat",

    # Sabtu
    "sabtu": "Sabtu",
    "saturday": "Sabtu",
    "sat": "Sabtu",

    # Minggu
    "minggu": "Minggu",
    "sunday": "Minggu",
    "sun": "Minggu",
}


def normalize_hari(value):
    if value is None:
        raise ValueError(
            "Nilai hari pada m_jadwal tidak boleh NULL"
        )

    normalized_key = str(value).strip().lower()

    normalized_value = HARI_MAP.get(normalized_key)

    if normalized_value is None:
        raise ValueError(
            f"Format hari tidak dikenali: {value!r}"
        )

    return normalized_value


def transform_jadwal_kerja(
    jadwal_rows,
    shift_rows,
):
    shift_map = {
        row["id"]: row
        for row in shift_rows
    }

    result = []

    for row in jadwal_rows:
        shift = shift_map.get(row["jenis"])

        if shift is None:
            raise ValueError(
                f"Shift ID {row['jenis']} "
                f"untuk jadwal ID {row['id']} tidak ditemukan"
            )

        source_updated_at_candidates = [
            row["created_at"],
            shift["created_at"],
        ]

        valid_timestamps = [
            value
            for value in source_updated_at_candidates
            if value is not None
        ]

        source_updated_at = (
            max(valid_timestamps)
            if valid_timestamps
            else None
        )

        result.append(
            {
                "jadwal_id": row["id"],
                "shift_id": row["jenis"],
                "departemen_id": shift["departemen_id"],
                "nama_shift": shift["nama"],

                # Canonical weekday untuk analytical layer
                "hari": normalize_hari(row["hari"]),

                "jam_masuk": row["jam_masuk"],
                "jam_keluar": row["jam_keluar"],
                "jam_masuk_awal": row["jam_masuk_awal"],
                "jam_keluar_akhir": row["jam_keluar_akhir"],

                "is_flexible": (
                    bool(shift["is_flexible"])
                    if shift["is_flexible"] is not None
                    else None
                ),

                "source_updated_at": source_updated_at,
            }
        )

    return result
