VALID_STATUSES = {
    "APPROVED",
    "REJECTED",
    "PENDING",
}


def validate_fact_perizinan_row(row):
    """
    Validasi satu final row fact_perizinan.

    Tidak mengubah data.
    Hanya memastikan hasil transform konsisten.
    """

    perizinan_id = row.get("perizinan_id")
    pegawai_id = row.get("pegawai_id")

    tanggal_mulai = row.get("tanggal_mulai")
    tanggal_selesai = row.get("tanggal_selesai")

    jumlah_hari = row.get("jumlah_hari")

    status = row.get("status_pengajuan")
    is_approved = row.get("is_approved")
    is_valid_leave = row.get("is_valid_leave")

    # Mandatory key
    if perizinan_id is None:
        raise ValueError(
            "perizinan_id tidak boleh NULL"
        )

    if pegawai_id is None:
        raise ValueError(
            f"pegawai_id NULL: perizinan_id={perizinan_id}"
        )

    # Dimension hasil resolver
    if row.get("departemen_id") is None:
        raise ValueError(
            "departemen_id belum ter-resolve: "
            f"perizinan_id={perizinan_id}"
        )

    if row.get("jenis_izin_id") is None:
        raise ValueError(
            "jenis_izin_id belum ter-resolve: "
            f"perizinan_id={perizinan_id}"
        )

    # Date range
    if tanggal_mulai is None:
        raise ValueError(
            f"tanggal_mulai NULL: perizinan_id={perizinan_id}"
        )

    if tanggal_selesai is None:
        raise ValueError(
            f"tanggal_selesai NULL: perizinan_id={perizinan_id}"
        )

    if tanggal_selesai < tanggal_mulai:
        raise ValueError(
            "Invalid date range: "
            f"perizinan_id={perizinan_id}, "
            f"tanggal_mulai={tanggal_mulai}, "
            f"tanggal_selesai={tanggal_selesai}"
        )

    # jumlah_hari harus inclusive
    expected_jumlah_hari = (
        tanggal_selesai - tanggal_mulai
    ).days + 1

    if jumlah_hari != expected_jumlah_hari:
        raise ValueError(
            "jumlah_hari tidak konsisten: "
            f"perizinan_id={perizinan_id}, "
            f"actual={jumlah_hari}, "
            f"expected={expected_jumlah_hari}"
        )

    if jumlah_hari < 1:
        raise ValueError(
            "jumlah_hari harus >= 1: "
            f"perizinan_id={perizinan_id}"
        )

    # Status
    if status not in VALID_STATUSES:
        raise ValueError(
            "status_pengajuan tidak dikenal: "
            f"perizinan_id={perizinan_id}, "
            f"status={status}"
        )

    # Approval consistency
    if status == "APPROVED":
        if is_approved is not True:
            raise ValueError(
                "APPROVED tetapi is_approved bukan True: "
                f"perizinan_id={perizinan_id}"
            )

        if is_valid_leave is not True:
            raise ValueError(
                "APPROVED tetapi is_valid_leave bukan True: "
                f"perizinan_id={perizinan_id}"
            )

    elif status in {"REJECTED", "PENDING"}:
        if is_approved is not False:
            raise ValueError(
                f"{status} tetapi is_approved bukan False: "
                f"perizinan_id={perizinan_id}"
            )

        if is_valid_leave is not False:
            raise ValueError(
                f"{status} tetapi is_valid_leave bukan False: "
                f"perizinan_id={perizinan_id}"
            )

    return True


def validate_fact_perizinan_grain(rows):
    """
    Memastikan grain:
        1 perizinan_id = 1 row fact
    """

    seen = set()

    for row in rows:
        perizinan_id = row["perizinan_id"]

        if perizinan_id in seen:
            raise ValueError(
                "Duplicate fact_perizinan ditemukan: "
                f"perizinan_id={perizinan_id}"
            )

        seen.add(perizinan_id)

    return True


def validate_fact_perizinan_rows(rows):
    """
    Menjalankan seluruh final validation.
    """

    validate_fact_perizinan_grain(rows)

    for row in rows:
        validate_fact_perizinan_row(row)

    return True
