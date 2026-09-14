def aggregate_attendance(attendance_rows):
    """
    Mengagregasi raw t_checkinout menjadi attendance harian.

    Grain hasil:
        1 pegawai x 1 tanggal

    Catatan:
    - filtering work_code = 1 dilakukan di extract layer
    - tanggal attendance menggunakan DATE(created_at)
    - checktype tidak digunakan
    - kolom izin t_checkinout tidak digunakan
    """

    grouped = {}

    for event in attendance_rows:
        pegawai_id = event["pegawai_id"]
        created_at = event["created_at"]

        if pegawai_id is None:
            raise ValueError(
                "Attendance event memiliki pegawai_id NULL"
            )

        if created_at is None:
            raise ValueError(
                "Attendance event memiliki created_at NULL"
            )

        tanggal = created_at.date()

        key = (
            pegawai_id,
            tanggal,
        )

        if key not in grouped:
            grouped[key] = []

        grouped[key].append(event)

    result = []

    for (pegawai_id, tanggal), events in grouped.items():

        # Pastikan urutan event konsisten.
        events = sorted(
            events,
            key=lambda row: (
                row["created_at"],
                row["id"],
            ),
        )

        jumlah_event = len(events)

        waktu_masuk = events[0]["created_at"]

        waktu_pulang = (
            events[-1]["created_at"]
            if jumlah_event >= 2
            else None
        )

        has_masuk = jumlah_event >= 1
        has_pulang = jumlah_event >= 2

        is_complete_attendance = (
            jumlah_event >= 2
        )

        is_wfh = any(
            event["is_wfh"] == 1
            or event["is_wfh"] is True
            for event in events
        )

        is_wfo = any(
            event["is_wfh"] == 0
            or event["is_wfh"] is False
            for event in events
        )

        updated_values = [
            event["updated_at"]
            for event in events
            if event["updated_at"] is not None
        ]

        source_updated_at = (
            max(updated_values)
            if updated_values
            else None
        )

        result.append(
            {
                "pegawai_id": pegawai_id,
                "tanggal": tanggal,

                "waktu_masuk": waktu_masuk,
                "waktu_pulang": waktu_pulang,

                "has_masuk": has_masuk,
                "has_pulang": has_pulang,

                "is_wfh": is_wfh,
                "is_wfo": is_wfo,

                "is_complete_attendance":
                    is_complete_attendance,

                "jumlah_event": jumlah_event,

                "source_updated_at":
                    source_updated_at,
            }
        )

    result.sort(
        key=lambda row: (
            row["pegawai_id"],
            row["tanggal"],
        )
    )

    return result
