def normalize_perizinan(row):
    """
    Normalisasi satu pengajuan izin.

    Grain:
        1 row = 1 pengajuan izin

    Fungsi ini belum melakukan:
    - dimension lookup
    - expansion multi-day
    - klasifikasi attendance
    """

    perizinan_id = row.get("id")
    pegawai_id = row.get("pegawai_id")

    tgl_mulai = row.get("tgl_ijin")
    tgl_selesai = row.get("tgl_ijin_sampai")

    approval = row.get("approval")

    # tgl_ijin wajib ada
    if tgl_mulai is None:
        raise ValueError(
            f"tgl_ijin NULL untuk perizinan_id={perizinan_id}"
        )

    # Jika tanggal akhir kosong, anggap izin satu hari
    if tgl_selesai is None:
        tgl_selesai = tgl_mulai

    # Jangan diam-diam membalik tanggal invalid
    if tgl_selesai < tgl_mulai:
        raise ValueError(
            "Invalid date range: "
            f"perizinan_id={perizinan_id}, "
            f"tgl_ijin={tgl_mulai}, "
            f"tgl_ijin_sampai={tgl_selesai}"
        )

    return {
        "source_perizinan_id": perizinan_id,
        "pegawai_id": pegawai_id,

        "tipe_ijin": row.get("tipe_ijin"),
        "jenis_ijin": row.get("jenis_ijin"),
        "alasan": row.get("alasan"),

        "approval": approval,
        "approval_at": row.get("approval_at"),

        "tgl_izin_mulai": tgl_mulai,
        "tgl_izin_sampai": tgl_selesai,

        "source_created_at": row.get("created_at"),
        "source_updated_at": row.get("updated_at"),
    }


def normalize_perizinan_rows(rows):
    """
    Normalisasi sekumpulan pengajuan izin.
    """

    return [
        normalize_perizinan(row)
        for row in rows
    ]