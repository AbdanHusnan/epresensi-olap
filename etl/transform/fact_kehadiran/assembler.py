def build_attendance_index(attendance_rows):
    """
    Membentuk index attendance harian berdasarkan:

        pegawai_id + tanggal

    Grain attendance_daily harus unik.
    """

    attendance_index = {}

    for attendance in attendance_rows:
        key = (
            attendance["pegawai_id"],
            attendance["tanggal"],
        )

        if key in attendance_index:
            raise ValueError(
                "Duplicate attendance_daily ditemukan: "
                f"pegawai_id={attendance['pegawai_id']}, "
                f"tanggal={attendance['tanggal']}"
            )

        attendance_index[key] = attendance

    return attendance_index


def validate_attendance_coverage(
    employee_day_rows,
    attendance_rows,
):
    """
    Memastikan seluruh attendance yang diproses
    mempunyai pasangan employee-day.

    Jika tidak ada pasangan berarti kemungkinan:
    - pegawai belum tersedia di dim_pegawai
    - tanggal tidak tersedia pada periode dim_calendar
    - periode extract tidak konsisten
    """

    employee_day_keys = {
        (
            row["pegawai_id"],
            row["tanggal"],
        )
        for row in employee_day_rows
    }

    for attendance in attendance_rows:
        key = (
            attendance["pegawai_id"],
            attendance["tanggal"],
        )

        if key not in employee_day_keys:
            raise ValueError(
                "Attendance tidak memiliki employee-day: "
                f"pegawai_id={attendance['pegawai_id']}, "
                f"tanggal={attendance['tanggal']}"
            )

    return True


def assemble_fact_rows(
    employee_day_rows,
    attendance_rows,
):
    """
    Menggabungkan expected employee-day
    dengan actual attendance.

    Konsep:

        employee_day
            LEFT JOIN
        attendance_daily

    Employee-day tanpa attendance tetap menghasilkan
    satu candidate fact row.
    """

    validate_attendance_coverage(
        employee_day_rows,
        attendance_rows,
    )

    attendance_index = build_attendance_index(
        attendance_rows
    )

    result = []

    for employee_day in employee_day_rows:
        row = employee_day.copy()

        key = (
            row["pegawai_id"],
            row["tanggal"],
        )

        attendance = attendance_index.get(key)

        if attendance is None:
            row.update(
                {
                    "waktu_masuk": None,
                    "waktu_pulang": None,

                    "has_masuk": False,
                    "has_pulang": False,

                    "is_wfh": False,
                    "is_wfo": False,

                    "is_complete_attendance": False,
                    "jumlah_event": 0,

                    "source_updated_at": None,
                }
            )

        else:
            row.update(
                {
                    "waktu_masuk":
                        attendance["waktu_masuk"],

                    "waktu_pulang":
                        attendance["waktu_pulang"],

                    "has_masuk":
                        attendance["has_masuk"],

                    "has_pulang":
                        attendance["has_pulang"],

                    "is_wfh":
                        attendance["is_wfh"],

                    "is_wfo":
                        attendance["is_wfo"],

                    "is_complete_attendance":
                        attendance[
                            "is_complete_attendance"
                        ],

                    "jumlah_event":
                        attendance["jumlah_event"],

                    "source_updated_at":
                        attendance[
                            "source_updated_at"
                        ],
                }
            )

        result.append(row)

    return result

def project_fact_kehadiran_rows(rows):
    """
    Mengubah working rows menjadi struktur final
    yang sesuai dengan kolom fact_kehadiran.

    Field internal transform seperti:
    - nama_hari
    - is_weekend
    - is_hari_libur
    - has_schedule
    - jam_masuk_jadwal
    - jam_keluar_jadwal
    - jam_masuk_awal
    - jam_keluar_akhir
    - is_flexible

    tidak diteruskan ke tabel fact.
    """

    result = []

    for row in rows:
        result.append(
            {
                "pegawai_id":
                    row["pegawai_id"],

                "tanggal":
                    row["tanggal"],

                "departemen_id":
                    row["departemen_id"],

                "jadwal_id":
                    row["jadwal_id"],

                "is_expected_workday":
                    row["is_expected_workday"],

                "is_libur_shift":
                    row["is_libur_shift"],

                "waktu_masuk":
                    row["waktu_masuk"],

                "waktu_pulang":
                    row["waktu_pulang"],

                "has_masuk":
                    row["has_masuk"],

                "has_pulang":
                    row["has_pulang"],

                "has_valid_leave":
                    row["has_valid_leave"],

                "perizinan_id":
                    row["perizinan_id"],

                "status_kehadiran":
                    row["status_kehadiran"],

                "is_wfh":
                    row["is_wfh"],

                "is_wfo":
                    row["is_wfo"],

                "is_terlambat":
                    row["is_terlambat"],

                "menit_terlambat":
                    row["menit_terlambat"],

                "is_pulang_awal":
                    row["is_pulang_awal"],

                "menit_pulang_awal":
                    row["menit_pulang_awal"],

                "is_complete_attendance":
                    row["is_complete_attendance"],

                "jumlah_event":
                    row["jumlah_event"],

                "source_updated_at":
                    row["source_updated_at"],
            }
        )

    return result

def validate_final_fact_rows(rows):
    """
    Validasi minimum sebelum candidate fact
    diperbolehkan masuk ke load layer.
    """

    seen = set()

    for row in rows:
        pegawai_id = row["pegawai_id"]
        tanggal = row["tanggal"]

        if pegawai_id is None:
            raise ValueError(
                "Final fact memiliki pegawai_id NULL"
            )

        if tanggal is None:
            raise ValueError(
                "Final fact memiliki tanggal NULL"
            )

        key = (
            pegawai_id,
            tanggal,
        )

        if key in seen:
            raise ValueError(
                "Duplicate final fact grain: "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal}"
            )

        seen.add(key)

    return True
