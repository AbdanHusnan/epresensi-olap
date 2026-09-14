from datetime import datetime

def apply_expected_workday_rule(employee_day_rows):
    """
    Menentukan apakah employee-day merupakan
    expected workday.

    Rule:

        has_schedule
        AND NOT is_hari_libur
        AND NOT is_libur_shift

    is_weekend tidak digunakan sebagai rule absolut.
    """

    result = []

    for employee_day in employee_day_rows:
        row = employee_day.copy()

        row["is_expected_workday"] = (
            row["has_schedule"]
            and not row["is_hari_libur"]
            and not row["is_libur_shift"]
        )

        result.append(row)

    return result

def apply_attendance_status_rule(rows):
    """
    Menentukan status kehadiran tahap pertama.

    Rule sementara sebelum integrasi perizinan:

    1. jumlah_event > 0
       -> HADIR

    2. jumlah_event = 0
       dan is_expected_workday = False
       -> NON_WORKING_DAY

    3. jumlah_event = 0
       dan is_expected_workday = True
       -> NULL

    Kondisi ketiga belum boleh disebut TIDAK_ABSEN
    karena masih mungkin memiliki izin valid.
    """

    result = []

    for source_row in rows:
        row = source_row.copy()

        jumlah_event = row["jumlah_event"]
        is_expected_workday = row[
            "is_expected_workday"
        ]

        # Placeholder sampai t_perizinan dikonfigurasi.
        row["has_valid_leave"] = False
        row["perizinan_id"] = None

        if jumlah_event > 0:
            row["status_kehadiran"] = "HADIR"

        elif not is_expected_workday:
            row["status_kehadiran"] = (
                "NON_WORKING_DAY"
            )

        else:
            row["status_kehadiran"] = None

        result.append(row)

    return result

def apply_time_compliance_rule(rows):
    """
    Menghitung keterlambatan dan pulang awal.

    Scope tahap saat ini:
    - hanya shift default / same-day
    - shift lintas hari belum ditangani
    - shift flexible tidak diberi penalti otomatis
    """

    result = []

    for source_row in rows:
        row = source_row.copy()

        row["is_terlambat"] = False
        row["menit_terlambat"] = None

        row["is_pulang_awal"] = False
        row["menit_pulang_awal"] = None

        # Tidak ada jadwal -> tidak ada evaluasi waktu
        if not row["has_schedule"]:
            result.append(row)
            continue

        # Flexible shift belum dievaluasi
        if row["is_flexible"] is True:
            result.append(row)
            continue

        tanggal = row["tanggal"]

        # -----------------------------------------
        # Keterlambatan
        # -----------------------------------------

        if (
            row["has_masuk"]
            and row["waktu_masuk"] is not None
            and row["jam_masuk_jadwal"] is not None
        ):
            scheduled_start = datetime.combine(
                tanggal,
                row["jam_masuk_jadwal"],
            )

            actual_start = row["waktu_masuk"]

            if actual_start > scheduled_start:
                delta = actual_start - scheduled_start

                row["is_terlambat"] = True
                row["menit_terlambat"] = int(
                    delta.total_seconds() // 60
                )
            else:
                row["menit_terlambat"] = 0

        # -----------------------------------------
        # Pulang awal
        # -----------------------------------------

        if (
            row["has_pulang"]
            and row["waktu_pulang"] is not None
            and row["jam_keluar_jadwal"] is not None
        ):
            scheduled_end = datetime.combine(
                tanggal,
                row["jam_keluar_jadwal"],
            )

            actual_end = row["waktu_pulang"]

            if actual_end < scheduled_end:
                delta = scheduled_end - actual_end

                row["is_pulang_awal"] = True
                row["menit_pulang_awal"] = int(
                    delta.total_seconds() // 60
                )
            else:
                row["menit_pulang_awal"] = 0

        result.append(row)

    return result
