def build_libur_shift_index(libur_shift_rows):
    """
    Membentuk index libur shift berdasarkan:

        pegawai_id + tanggal

    Duplicate source untuk pegawai + tanggal yang sama
    dianggap satu kondisi libur shift.

    departemen_id tidak digunakan sebagai rule.
    """

    libur_shift_index = set()

    for row in libur_shift_rows:
        pegawai_id = row["pegawai_id"]
        tanggal = row["tanggal"]

        if pegawai_id is None:
            raise ValueError(
                "t_libur_shift memiliki pegawai_id NULL"
            )

        if tanggal is None:
            raise ValueError(
                "t_libur_shift memiliki tanggal NULL"
            )

        key = (
            pegawai_id,
            tanggal,
        )

        libur_shift_index.add(key)

    return libur_shift_index


def resolve_libur_shift(
    employee_day_rows,
    libur_shift_rows,
):
    """
    Menentukan apakah employee-day termasuk
    libur shift individual pegawai.

    Matching hanya berdasarkan:

        pegawai_id + tanggal
    """

    libur_shift_index = build_libur_shift_index(
        libur_shift_rows
    )

    result = []

    for employee_day in employee_day_rows:
        row = employee_day.copy()

        key = (
            row["pegawai_id"],
            row["tanggal"],
        )

        row["is_libur_shift"] = (
            key in libur_shift_index
        )

        result.append(row)

    return result
