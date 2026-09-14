def load_fact_kehadiran(conn, rows):
    """
    Load final fact_kehadiran rows ke OLAP.

    Grain:
        pegawai_id + tanggal

    Strategy:
        INSERT
        ON CONFLICT -> UPDATE

    Commit tidak dilakukan di fungsi ini.
    Transaction dikontrol oleh pipeline.
    """

    inserted = 0
    updated = 0

    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO fact_kehadiran (
                    pegawai_id,
                    tanggal,
                    departemen_id,
                    jadwal_id,
                    is_expected_workday,
                    is_libur_shift,
                    waktu_masuk,
                    waktu_pulang,
                    has_masuk,
                    has_pulang,
                    has_valid_leave,
                    perizinan_id,
                    status_kehadiran,
                    is_wfh,
                    is_wfo,
                    is_terlambat,
                    menit_terlambat,
                    is_pulang_awal,
                    menit_pulang_awal,
                    is_complete_attendance,
                    jumlah_event,
                    source_updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )

                ON CONFLICT (
                    pegawai_id,
                    tanggal
                )

                DO UPDATE SET
                    departemen_id =
                        EXCLUDED.departemen_id,

                    jadwal_id =
                        EXCLUDED.jadwal_id,

                    is_expected_workday =
                        EXCLUDED.is_expected_workday,

                    is_libur_shift =
                        EXCLUDED.is_libur_shift,

                    waktu_masuk =
                        EXCLUDED.waktu_masuk,

                    waktu_pulang =
                        EXCLUDED.waktu_pulang,

                    has_masuk =
                        EXCLUDED.has_masuk,

                    has_pulang =
                        EXCLUDED.has_pulang,

                    has_valid_leave =
                        EXCLUDED.has_valid_leave,

                    perizinan_id =
                        EXCLUDED.perizinan_id,

                    status_kehadiran =
                        EXCLUDED.status_kehadiran,

                    is_wfh =
                        EXCLUDED.is_wfh,

                    is_wfo =
                        EXCLUDED.is_wfo,

                    is_terlambat =
                        EXCLUDED.is_terlambat,

                    menit_terlambat =
                        EXCLUDED.menit_terlambat,

                    is_pulang_awal =
                        EXCLUDED.is_pulang_awal,

                    menit_pulang_awal =
                        EXCLUDED.menit_pulang_awal,

                    is_complete_attendance =
                        EXCLUDED.is_complete_attendance,

                    jumlah_event =
                        EXCLUDED.jumlah_event,

                    source_updated_at =
                        EXCLUDED.source_updated_at,

                    etl_loaded_at =
                        CURRENT_TIMESTAMP

                WHERE ROW(
                    fact_kehadiran.departemen_id,
                    fact_kehadiran.jadwal_id,
                    fact_kehadiran.is_expected_workday,
                    fact_kehadiran.is_libur_shift,
                    fact_kehadiran.waktu_masuk,
                    fact_kehadiran.waktu_pulang,
                    fact_kehadiran.has_masuk,
                    fact_kehadiran.has_pulang,
                    fact_kehadiran.has_valid_leave,
                    fact_kehadiran.perizinan_id,
                    fact_kehadiran.status_kehadiran,
                    fact_kehadiran.is_wfh,
                    fact_kehadiran.is_wfo,
                    fact_kehadiran.is_terlambat,
                    fact_kehadiran.menit_terlambat,
                    fact_kehadiran.is_pulang_awal,
                    fact_kehadiran.menit_pulang_awal,
                    fact_kehadiran.is_complete_attendance,
                    fact_kehadiran.jumlah_event,
                    fact_kehadiran.source_updated_at
                )

                IS DISTINCT FROM ROW(
                    EXCLUDED.departemen_id,
                    EXCLUDED.jadwal_id,
                    EXCLUDED.is_expected_workday,
                    EXCLUDED.is_libur_shift,
                    EXCLUDED.waktu_masuk,
                    EXCLUDED.waktu_pulang,
                    EXCLUDED.has_masuk,
                    EXCLUDED.has_pulang,
                    EXCLUDED.has_valid_leave,
                    EXCLUDED.perizinan_id,
                    EXCLUDED.status_kehadiran,
                    EXCLUDED.is_wfh,
                    EXCLUDED.is_wfo,
                    EXCLUDED.is_terlambat,
                    EXCLUDED.menit_terlambat,
                    EXCLUDED.is_pulang_awal,
                    EXCLUDED.menit_pulang_awal,
                    EXCLUDED.is_complete_attendance,
                    EXCLUDED.jumlah_event,
                    EXCLUDED.source_updated_at
                )

                RETURNING
                    (xmax = 0) AS inserted
                """,
                (
                    row["pegawai_id"],
                    row["tanggal"],
                    row["departemen_id"],
                    row["jadwal_id"],
                    row["is_expected_workday"],
                    row["is_libur_shift"],
                    row["waktu_masuk"],
                    row["waktu_pulang"],
                    row["has_masuk"],
                    row["has_pulang"],
                    row["has_valid_leave"],
                    row["perizinan_id"],
                    row["status_kehadiran"],
                    row["is_wfh"],
                    row["is_wfo"],
                    row["is_terlambat"],
                    row["menit_terlambat"],
                    row["is_pulang_awal"],
                    row["menit_pulang_awal"],
                    row["is_complete_attendance"],
                    row["jumlah_event"],
                    row["source_updated_at"],
                ),
            )

            result = cur.fetchone()

            # Tidak ada perubahan pada existing row.
            if result is None:
                continue

            if result[0]:
                inserted += 1
            else:
                updated += 1

    return inserted, updated
