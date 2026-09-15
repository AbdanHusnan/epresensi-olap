def build_fact_perizinan_row(row):
    """
    Membentuk satu row final fact_perizinan.

    Grain:
        1 row = 1 pengajuan izin
    """

    tanggal_mulai = row["tgl_izin_mulai"]
    tanggal_selesai = row["tgl_izin_sampai"]

    jumlah_hari = (
        tanggal_selesai - tanggal_mulai
    ).days + 1

    return {
        "perizinan_id":
            row["source_perizinan_id"],

        "pegawai_id":
            row["pegawai_id"],

        "departemen_id":
            row["departemen_id"],

        "jenis_izin_id":
            row["jenis_izin_id"],

        "tanggal_pengajuan":
            row.get("source_created_at"),

        "tanggal_mulai":
            tanggal_mulai,

        "tanggal_selesai":
            tanggal_selesai,

        "jumlah_hari":
            jumlah_hari,

        "status_pengajuan":
            row["status_perizinan"],

        "is_approved":
            row.get("approval") is True,

        "is_valid_leave":
            row["is_izin_valid"],

        "alasan":
            row.get("alasan"),

        "source_updated_at":
            row.get("source_updated_at"),
    }


def build_fact_perizinan_rows(rows):
    """
    Membentuk seluruh row final fact_perizinan.
    """

    return [
        build_fact_perizinan_row(row)
        for row in rows
    ]
