def validate_employee_day_grain(rows):
    """
    Memastikan grain employee-day tetap:
        1 pegawai x 1 tanggal
    """

    seen = set()

    for row in rows:
        key = (
            row["pegawai_id"],
            row["tanggal"],
        )

        if key in seen:
            raise ValueError(
                "Duplicate employee-day ditemukan: "
                f"pegawai_id={row['pegawai_id']}, "
                f"tanggal={row['tanggal']}"
            )

        seen.add(key)

    return True


def build_employee_days(
    pegawai_rows,
    calendar_rows,
):
    """
    Membentuk candidate employee-day.

    Grain:
        1 pegawai x 1 tanggal

    Belum melakukan:
    - schedule resolution
    - libur shift resolution
    - attendance resolution
    - status kehadiran
    """

    result = []

    for pegawai in pegawai_rows:
        for calendar in calendar_rows:
            result.append(
                {
                    "pegawai_id": pegawai["pegawai_id"],
                    "departemen_id": pegawai["departemen_id"],

                    "tanggal": calendar["tanggal"],
                    "nama_hari": calendar["nama_hari"],

                    "is_weekend": calendar["is_weekend"],
                    "is_hari_libur": calendar["is_hari_libur"],
                    "keterangan_libur": calendar[
                        "keterangan_libur"
                    ],

                    # Schedule belum di-resolve
                    "jadwal_id": None,
                    "has_schedule": False,

                    "jam_masuk_jadwal": None,
                    "jam_keluar_jadwal": None,
                    "jam_masuk_awal": None,
                    "jam_keluar_akhir": None,
                    "is_flexible": None,

                    # Akan di-resolve kemudian
                    "is_libur_shift": False,

                    # Baru dihitung setelah schedule,
                    # holiday, dan libur shift selesai
                    "is_expected_workday": False,
                }
            )

    validate_employee_day_grain(result)

    return result
