def resolve_perizinan_dimensions(
    row,
    pegawai_reference,
    jenis_izin_reference,
):
    """
    Resolve analytical dimension untuk satu pengajuan izin.

    Departemen mengikuti dim_pegawai,
    bukan text departemen dari t_perizinan.
    """

    pegawai_id = row.get("pegawai_id")
    jenis_izin_id = row.get("jenis_ijin")

    if pegawai_id not in pegawai_reference:
        raise ValueError(
            "Pegawai tidak ditemukan di dim_pegawai: "
            f"pegawai_id={pegawai_id}, "
            f"perizinan_id={row.get('source_perizinan_id')}"
        )

    if jenis_izin_id not in jenis_izin_reference:
        raise ValueError(
            "Jenis izin tidak ditemukan di dim_jenis_izin: "
            f"jenis_izin_id={jenis_izin_id}, "
            f"perizinan_id={row.get('source_perizinan_id')}"
        )

    departemen_id = pegawai_reference[pegawai_id]

    return {
        **row,
        "departemen_id": departemen_id,
        "jenis_izin_id": jenis_izin_id,
    }


def resolve_perizinan_dimensions_rows(
    rows,
    pegawai_reference,
    jenis_izin_reference,
):
    """
    Resolve dimension seluruh pengajuan izin.
    """

    return [
        resolve_perizinan_dimensions(
            row,
            pegawai_reference,
            jenis_izin_reference,
        )
        for row in rows
    ]
