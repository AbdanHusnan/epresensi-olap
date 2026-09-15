def validate_perizinan_reference(
    rows,
    pegawai_ids,
    jenis_izin_ids,
):
    """
    Validasi referensi utama fact_perizinan.

    Tidak menghapus row.
    Tidak mengubah grain.
    """

    pegawai_ids = set(pegawai_ids)
    jenis_izin_ids = set(jenis_izin_ids)

    result = []

    for row in rows:
        pegawai_id = row.get("pegawai_id")
        jenis_ijin = row.get("jenis_ijin")

        validated = {
            **row,

            "is_pegawai_valid": (
                pegawai_id is not None
                and pegawai_id in pegawai_ids
            ),

            "is_jenis_izin_valid": (
                jenis_ijin is not None
                and jenis_ijin in jenis_izin_ids
            ),
        }

        result.append(validated)

    return result