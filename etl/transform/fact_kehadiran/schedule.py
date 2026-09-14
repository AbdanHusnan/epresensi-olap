def build_schedule_index(schedule_rows):
    """
    Membentuk index jadwal berdasarkan:

        departemen_id + hari

    Satu kombinasi departemen + hari hanya boleh
    memiliki satu jadwal yang valid.
    """

    schedule_index = {}

    for schedule in schedule_rows:
        key = (
            schedule["departemen_id"],
            schedule["hari"],
        )

        if key in schedule_index:
            existing = schedule_index[key]

            raise ValueError(
                "Ambiguous schedule ditemukan: "
                f"departemen_id={schedule['departemen_id']}, "
                f"hari={schedule['hari']}, "
                f"jadwal_id={existing['jadwal_id']} dan "
                f"{schedule['jadwal_id']}"
            )

        schedule_index[key] = schedule

    return schedule_index


def resolve_schedule(
    employee_day_rows,
    schedule_rows,
):
    """
    Resolve jadwal untuk setiap employee-day.

    Matching berdasarkan:
        employee_day.departemen_id
        +
        employee_day.nama_hari

    terhadap:
        dim_jadwal_kerja.departemen_id
        +
        dim_jadwal_kerja.hari
    """

    schedule_index = build_schedule_index(
        schedule_rows
    )

    result = []

    for employee_day in employee_day_rows:
        row = employee_day.copy()

        key = (
            row["departemen_id"],
            row["nama_hari"],
        )

        schedule = schedule_index.get(key)

        if schedule is None:
            result.append(row)
            continue

        row["jadwal_id"] = schedule["jadwal_id"]
        row["has_schedule"] = True

        row["jam_masuk_jadwal"] = schedule[
            "jam_masuk"
        ]

        row["jam_keluar_jadwal"] = schedule[
            "jam_keluar"
        ]

        row["jam_masuk_awal"] = schedule[
            "jam_masuk_awal"
        ]

        row["jam_keluar_akhir"] = schedule[
            "jam_keluar_akhir"
        ]

        row["is_flexible"] = schedule[
            "is_flexible"
        ]

        result.append(row)

    return result
