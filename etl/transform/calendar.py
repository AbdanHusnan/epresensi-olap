from datetime import date, timedelta


NAMA_BULAN = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}


NAMA_HARI = {
    0: "Senin",
    1: "Selasa",
    2: "Rabu",
    3: "Kamis",
    4: "Jumat",
    5: "Sabtu",
    6: "Minggu",
}


def transform_calendar(
    holiday_rows,
    start_date,
    end_date,
):
    holiday_map = {
        row["tanggal"]: row["keterangan"]
        for row in holiday_rows
    }

    result = []

    current_date = start_date

    while current_date <= end_date:
        holiday_description = holiday_map.get(current_date)

        iso_calendar = current_date.isocalendar()

        result.append(
            {
                "tanggal": current_date,
                "tahun": current_date.year,
                "bulan": current_date.month,
                "nama_bulan": NAMA_BULAN[current_date.month],
                "hari": current_date.day,
                "nama_hari": NAMA_HARI[current_date.weekday()],
                "minggu_ke": iso_calendar.week,
                "kuartal": ((current_date.month - 1) // 3) + 1,
                "is_weekend": current_date.weekday() >= 5,
                "is_hari_libur": holiday_description is not None,
                "keterangan_libur": holiday_description,
            }
        )

        current_date += timedelta(days=1)

    return result
