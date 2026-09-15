from datetime import timedelta


def expand_daily_leave_coverage(row):
    """
    Expand satu pengajuan izin valid menjadi coverage harian.

    Penting:
    - Tidak mengubah grain fact_perizinan.
    - Hanya izin valid/approved yang menghasilkan coverage.
    - Semua tanggal dalam range dihasilkan secara inclusive.
    """

    if not row.get("is_izin_valid", False):
        return []

    start_date = row["tgl_izin_mulai"]
    end_date = row["tgl_izin_sampai"]

    coverage = []

    current_date = start_date

    while current_date <= end_date:
        coverage.append({
            "source_perizinan_id": row["source_perizinan_id"],
            "pegawai_id": row["pegawai_id"],
            "jenis_ijin": row.get("jenis_ijin"),
            "tanggal": current_date,
        })

        current_date += timedelta(days=1)

    return coverage


def build_daily_leave_coverage(rows):
    """
    Membentuk seluruh daily leave coverage dari kumpulan pengajuan izin.
    """

    result = []

    for row in rows:
        result.extend(
            expand_daily_leave_coverage(row)
        )

    return result
