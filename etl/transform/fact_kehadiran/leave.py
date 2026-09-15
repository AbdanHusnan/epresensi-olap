def build_daily_leave_index(daily_leave_rows):
    """
    Membentuk index daily leave coverage berdasarkan:

        pegawai_id + tanggal

    Input berasal dari:
        fact_perizinan.daily_coverage

    Daily coverage hanya berisi izin valid/approved.

    Value index:
        source_perizinan_id

    Untuk big-case saat ini, satu employee-day
    hanya boleh memiliki satu valid leave.
    """

    leave_index = {}

    for leave in daily_leave_rows:
        pegawai_id = leave.get("pegawai_id")
        tanggal = leave.get("tanggal")
        perizinan_id = leave.get(
            "source_perizinan_id"
        )

        if pegawai_id is None:
            raise ValueError(
                "Daily leave coverage memiliki "
                "pegawai_id NULL"
            )

        if tanggal is None:
            raise ValueError(
                "Daily leave coverage memiliki "
                "tanggal NULL"
            )

        if perizinan_id is None:
            raise ValueError(
                "Daily leave coverage memiliki "
                "source_perizinan_id NULL"
            )

        key = (
            pegawai_id,
            tanggal,
        )

        if key in leave_index:
            raise ValueError(
                "Multiple valid leave ditemukan "
                "pada employee-day yang sama: "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal}, "
                f"perizinan_id_existing="
                f"{leave_index[key]}, "
                f"perizinan_id_new={perizinan_id}"
            )

        leave_index[key] = perizinan_id

    return leave_index


def attach_daily_leave_coverage(
    rows,
    daily_leave_rows,
):
    """
    Menggabungkan working fact_kehadiran
    dengan daily valid leave coverage.

    Join key:

        pegawai_id + tanggal

    Output tambahan:

        has_valid_leave
        perizinan_id

    Grain fact_kehadiran tetap:

        1 pegawai x 1 tanggal
    """

    leave_index = build_daily_leave_index(
        daily_leave_rows
    )

    result = []

    for source_row in rows:
        row = source_row.copy()

        key = (
            row["pegawai_id"],
            row["tanggal"],
        )

        perizinan_id = leave_index.get(key)

        if perizinan_id is None:
            row["has_valid_leave"] = False
            row["perizinan_id"] = None

        else:
            row["has_valid_leave"] = True
            row["perizinan_id"] = perizinan_id

        result.append(row)

    return result
