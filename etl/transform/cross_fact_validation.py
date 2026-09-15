def validate_perizinan_reference_integrity(
    kehadiran_rows,
    perizinan_rows,
):
    """
    Memastikan setiap perizinan_id non-NULL pada
    fact_kehadiran memiliki parent pada fact_perizinan.

    Relasi:
        fact_kehadiran.perizinan_id
            ->
        fact_perizinan.perizinan_id

    Catatan:
    - perizinan_id NULL pada fact_kehadiran adalah valid.
    - Satu perizinan_id boleh direferensikan oleh
      lebih dari satu employee-day.
    """

    valid_perizinan_ids = {
        row["perizinan_id"]
        for row in perizinan_rows
        if row.get("perizinan_id") is not None
    }

    for row in kehadiran_rows:
        perizinan_id = row.get("perizinan_id")

        if perizinan_id is None:
            continue

        if perizinan_id not in valid_perizinan_ids:
            raise ValueError(
                "Orphan perizinan reference ditemukan: "
                f"pegawai_id={row.get('pegawai_id')}, "
                f"tanggal={row.get('tanggal')}, "
                f"perizinan_id={perizinan_id}"
            )

    return True


def validate_fact_perizinan_dimension_references(
    perizinan_rows,
    pegawai_rows,
    departemen_rows,
    jenis_izin_rows,
):
    """
    Validasi referential integrity final fact_perizinan.

    Required references:
        pegawai_id    -> dim_pegawai
        departemen_id -> dim_departemen
        jenis_izin_id -> dim_jenis_izin
    """

    valid_pegawai_ids = {
        row["pegawai_id"]
        for row in pegawai_rows
    }

    valid_departemen_ids = {
        row["departemen_id"]
        for row in departemen_rows
    }

    valid_jenis_izin_ids = {
        row["jenis_izin_id"]
        for row in jenis_izin_rows
    }

    for row in perizinan_rows:
        perizinan_id = row.get("perizinan_id")

        pegawai_id = row.get("pegawai_id")
        departemen_id = row.get("departemen_id")
        jenis_izin_id = row.get("jenis_izin_id")

        if (
            pegawai_id is None
            or pegawai_id not in valid_pegawai_ids
        ):
            raise ValueError(
                "Invalid fact_perizinan pegawai_id: "
                f"perizinan_id={perizinan_id}, "
                f"pegawai_id={pegawai_id}"
            )

        if (
            departemen_id is None
            or departemen_id not in valid_departemen_ids
        ):
            raise ValueError(
                "Invalid fact_perizinan departemen_id: "
                f"perizinan_id={perizinan_id}, "
                f"departemen_id={departemen_id}"
            )

        if (
            jenis_izin_id is None
            or jenis_izin_id not in valid_jenis_izin_ids
        ):
            raise ValueError(
                "Invalid fact_perizinan jenis_izin_id: "
                f"perizinan_id={perizinan_id}, "
                f"jenis_izin_id={jenis_izin_id}"
            )

    return True


def validate_fact_kehadiran_dimension_references(
    kehadiran_rows,
    pegawai_rows,
    departemen_rows,
    jadwal_rows,
):
    """
    Validasi referential integrity final fact_kehadiran.

    Required references:
        pegawai_id    -> dim_pegawai
        departemen_id -> dim_departemen

    Optional reference:
        jadwal_id -> dim_jadwal_kerja

    jadwal_id NULL adalah legal karena employee-day
    tanpa schedule tetap dipertahankan.
    """

    valid_pegawai_ids = {
        row["pegawai_id"]
        for row in pegawai_rows
    }

    valid_departemen_ids = {
        row["departemen_id"]
        for row in departemen_rows
    }

    valid_jadwal_ids = {
        row["jadwal_id"]
        for row in jadwal_rows
    }

    for row in kehadiran_rows:
        pegawai_id = row.get("pegawai_id")
        tanggal = row.get("tanggal")
        departemen_id = row.get("departemen_id")
        jadwal_id = row.get("jadwal_id")

        if (
            pegawai_id is None
            or pegawai_id not in valid_pegawai_ids
        ):
            raise ValueError(
                "Invalid fact_kehadiran pegawai_id: "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal}"
            )

        if (
            departemen_id is None
            or departemen_id not in valid_departemen_ids
        ):
            raise ValueError(
                "Invalid fact_kehadiran departemen_id: "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal}, "
                f"departemen_id={departemen_id}"
            )

        # jadwal_id memang nullable.
        if (
            jadwal_id is not None
            and jadwal_id not in valid_jadwal_ids
        ):
            raise ValueError(
                "Invalid fact_kehadiran jadwal_id: "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal}, "
                f"jadwal_id={jadwal_id}"
            )

    return True


def validate_approved_leave_matching(
    perizinan_rows,
    kehadiran_rows,
):
    """
    Cross-fact validation untuk approved single-day leave.

    Rule yang divalidasi:

        fact_perizinan:
            is_approved = True
            is_valid_leave = True
            tanggal_mulai = tanggal_selesai

        DAN fact_kehadiran:
            is_expected_workday = True
            jumlah_event = 0

        MAKA:
            has_valid_leave = True
            perizinan_id harus sama
            status_kehadiran = IZIN

    Catatan:
    - Attendance actual mempunyai precedence lebih tinggi,
      sehingga jumlah_event > 0 tidak diperiksa di rule ini.
    - Non-working day juga bukan scope rule ini.
    - Diasumsikan kedua fact berasal dari validation period
      yang sama.
    """

    kehadiran_index = {
        (
            row["pegawai_id"],
            row["tanggal"],
        ): row
        for row in kehadiran_rows
    }

    for leave in perizinan_rows:

        # Hanya approved valid leave.
        if not leave.get("is_approved", False):
            continue

        if not leave.get("is_valid_leave", False):
            continue

        tanggal_mulai = leave.get("tanggal_mulai")
        tanggal_selesai = leave.get("tanggal_selesai")

        # Step 7.5 hanya single-day.
        if tanggal_mulai != tanggal_selesai:
            continue

        pegawai_id = leave.get("pegawai_id")
        perizinan_id = leave.get("perizinan_id")

        key = (
            pegawai_id,
            tanggal_mulai,
        )

        kehadiran = kehadiran_index.get(key)

        if kehadiran is None:
            raise ValueError(
                "Approved leave tidak memiliki "
                "matching employee-day: "
                f"perizinan_id={perizinan_id}, "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal_mulai}"
            )

        # Rule IZIN hanya berlaku pada expected workday.
        if not kehadiran.get(
            "is_expected_workday",
            False,
        ):
            continue

        jumlah_event = kehadiran.get("jumlah_event")

        if jumlah_event is None:
            raise ValueError(
                "jumlah_event NULL pada matching employee-day: "
                f"perizinan_id={perizinan_id}, "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal_mulai}"
            )

        # Actual attendance menang atas leave.
        if jumlah_event > 0:
            continue

        if not kehadiran.get(
            "has_valid_leave",
            False,
        ):
            raise ValueError(
                "Approved leave tidak ter-attach "
                "ke fact_kehadiran: "
                f"perizinan_id={perizinan_id}, "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal_mulai}"
            )

        if (
            kehadiran.get("perizinan_id")
            != perizinan_id
        ):
            raise ValueError(
                "Approved leave memiliki "
                "perizinan_id mismatch: "
                f"expected={perizinan_id}, "
                f"actual="
                f"{kehadiran.get('perizinan_id')}, "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal_mulai}"
            )

        if (
            kehadiran.get("status_kehadiran")
            != "IZIN"
        ):
            raise ValueError(
                "Approved leave menghasilkan "
                "status_kehadiran tidak valid: "
                f"perizinan_id={perizinan_id}, "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal_mulai}, "
                f"status="
                f"{kehadiran.get('status_kehadiran')}"
            )

    return True


def validate_rejected_pending_protection(
    perizinan_rows,
    kehadiran_rows,
):
    """
    Memastikan REJECTED/PENDING tidak memengaruhi
    fact_kehadiran sebagai valid leave.

    Rule:
    1. perizinan_id REJECTED/PENDING tidak boleh
       direferensikan oleh fact_kehadiran.
    2. Jika pada employee-day tersebut tidak ada
       approved valid leave lain, maka:
           has_valid_leave tidak boleh True
           status_kehadiran tidak boleh IZIN

    Step 7.6 difokuskan pada single-day leave.
    Multi-day direkonsiliasi pada Step 7.7.
    """

    kehadiran_index = {
        (
            row["pegawai_id"],
            row["tanggal"],
        ): row
        for row in kehadiran_rows
    }

    valid_leave_keys = {
        (
            row["pegawai_id"],
            row["tanggal_mulai"],
        )
        for row in perizinan_rows
        if (
            row.get("is_approved") is True
            and row.get("is_valid_leave") is True
            and row.get("tanggal_mulai")
                == row.get("tanggal_selesai")
        )
    }

    for leave in perizinan_rows:
        status = leave.get("status_pengajuan")

        if status not in {"REJECTED", "PENDING"}:
            continue

        if leave.get("is_valid_leave") is not False:
            raise ValueError(
                "Rejected/Pending memiliki "
                "is_valid_leave tidak valid: "
                f"perizinan_id="
                f"{leave.get('perizinan_id')}"
            )

        tanggal_mulai = leave.get("tanggal_mulai")
        tanggal_selesai = leave.get("tanggal_selesai")

        # Multi-day bukan scope Step 7.6.
        if tanggal_mulai != tanggal_selesai:
            continue

        pegawai_id = leave.get("pegawai_id")
        perizinan_id = leave.get("perizinan_id")

        key = (
            pegawai_id,
            tanggal_mulai,
        )

        kehadiran = kehadiran_index.get(key)

        # Tidak ada employee-day dalam validation period.
        if kehadiran is None:
            continue

        # ID rejected/pending sama sekali tidak boleh attached.
        if (
            kehadiran.get("perizinan_id")
            == perizinan_id
        ):
            raise ValueError(
                "Rejected/Pending leave ter-attach "
                "ke fact_kehadiran: "
                f"status={status}, "
                f"perizinan_id={perizinan_id}, "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal_mulai}"
            )

        # Jika ada approved leave lain pada hari yang sama,
        # IZIN masih mungkin sah.
        if key in valid_leave_keys:
            continue

        if kehadiran.get(
            "has_valid_leave",
            False,
        ):
            raise ValueError(
                "Rejected/Pending menghasilkan "
                "has_valid_leave=True: "
                f"status={status}, "
                f"perizinan_id={perizinan_id}, "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal_mulai}"
            )

        if (
            kehadiran.get("status_kehadiran")
            == "IZIN"
        ):
            raise ValueError(
                "Rejected/Pending menghasilkan IZIN: "
                f"status={status}, "
                f"perizinan_id={perizinan_id}, "
                f"pegawai_id={pegawai_id}, "
                f"tanggal={tanggal_mulai}"
            )

    return True


def validate_multiday_leave_reconciliation(
    perizinan_rows,
    kehadiran_rows,
):
    """
    Cross-fact reconciliation untuk approved multi-day leave.

    Untuk setiap approved valid leave dengan range > 1 hari:

    - setiap tanggal dalam range inclusive harus memiliki
      matching fact_kehadiran
    - has_valid_leave harus True
    - perizinan_id harus sama

    Status akhir mengikuti precedence business rule:

    1. jumlah_event > 0
       -> HADIR

    2. jumlah_event == 0 dan bukan expected workday
       -> NON_WORKING_DAY

    3. jumlah_event == 0 dan expected workday
       -> IZIN
    """

    from datetime import timedelta

    kehadiran_index = {
        (
            row["pegawai_id"],
            row["tanggal"],
        ): row
        for row in kehadiran_rows
    }

    for leave in perizinan_rows:

        if leave.get("is_approved") is not True:
            continue

        if leave.get("is_valid_leave") is not True:
            continue

        tanggal_mulai = leave.get("tanggal_mulai")
        tanggal_selesai = leave.get("tanggal_selesai")

        # Step 7.7 khusus multi-day.
        if tanggal_mulai == tanggal_selesai:
            continue

        pegawai_id = leave.get("pegawai_id")
        perizinan_id = leave.get("perizinan_id")

        current_date = tanggal_mulai

        while current_date <= tanggal_selesai:

            key = (
                pegawai_id,
                current_date,
            )

            kehadiran = kehadiran_index.get(key)

            if kehadiran is None:
                raise ValueError(
                    "Multi-day leave kehilangan employee-day: "
                    f"perizinan_id={perizinan_id}, "
                    f"pegawai_id={pegawai_id}, "
                    f"tanggal={current_date}"
                )

            if not kehadiran.get(
                "has_valid_leave",
                False,
            ):
                raise ValueError(
                    "Multi-day leave tidak ter-attach: "
                    f"perizinan_id={perizinan_id}, "
                    f"pegawai_id={pegawai_id}, "
                    f"tanggal={current_date}"
                )

            if (
                kehadiran.get("perizinan_id")
                != perizinan_id
            ):
                raise ValueError(
                    "Multi-day leave perizinan_id mismatch: "
                    f"expected={perizinan_id}, "
                    f"actual="
                    f"{kehadiran.get('perizinan_id')}, "
                    f"pegawai_id={pegawai_id}, "
                    f"tanggal={current_date}"
                )

            jumlah_event = kehadiran.get("jumlah_event")

            if jumlah_event is None:
                raise ValueError(
                    "jumlah_event NULL pada multi-day leave: "
                    f"perizinan_id={perizinan_id}, "
                    f"pegawai_id={pegawai_id}, "
                    f"tanggal={current_date}"
                )

            is_expected_workday = kehadiran.get(
                "is_expected_workday",
                False,
            )

            status = kehadiran.get(
                "status_kehadiran"
            )

            # Actual attendance selalu menang.
            if jumlah_event > 0:
                expected_status = "HADIR"

            # Non-working day menang atas leave.
            elif not is_expected_workday:
                expected_status = "NON_WORKING_DAY"

            # Expected workday + no attendance + valid leave.
            else:
                expected_status = "IZIN"

            if status != expected_status:
                raise ValueError(
                    "Multi-day leave status tidak konsisten: "
                    f"perizinan_id={perizinan_id}, "
                    f"pegawai_id={pegawai_id}, "
                    f"tanggal={current_date}, "
                    f"actual={status}, "
                    f"expected={expected_status}"
                )

            current_date += timedelta(days=1)

    return True


def validate_fact_perizinan_count_reconciliation(
    source_rows,
    fact_rows,
):
    """
    Memastikan pipeline fact_perizinan tidak kehilangan
    atau menambah pengajuan izin.

    Grain:
        1 source pengajuan
        ->
        1 fact_perizinan

    Pipeline fact_perizinan tidak melakukan filtering.
    Invalid data harus menghasilkan failure, bukan
    silent row drop.
    """

    source_count = len(source_rows)
    fact_count = len(fact_rows)

    if source_count != fact_count:
        raise ValueError(
            "fact_perizinan count mismatch: "
            f"source_count={source_count}, "
            f"fact_count={fact_count}"
        )

    return True


def validate_fact_kehadiran_count_reconciliation(
    employee_day_rows,
    fact_rows,
):
    """
    Memastikan seluruh candidate employee-day tetap
    menghasilkan tepat satu final fact_kehadiran.

    Population reconciliation:
        employee_day
        ->
        fact_kehadiran

    Bukan:
        t_checkinout
        ->
        fact_kehadiran

    karena t_checkinout memiliki grain event.
    """

    employee_day_count = len(employee_day_rows)
    fact_count = len(fact_rows)

    if employee_day_count != fact_count:
        raise ValueError(
            "fact_kehadiran count mismatch: "
            f"employee_day_count={employee_day_count}, "
            f"fact_count={fact_count}"
        )

    return True


def validate_fact_kehadiran_key_reconciliation(
    employee_day_rows,
    fact_rows,
):
    """
    Memastikan population employee-day bukan hanya
    memiliki jumlah sama, tetapi key yang sama.

    Grain key:
        pegawai_id + tanggal
    """

    employee_day_keys = {
        (
            row["pegawai_id"],
            row["tanggal"],
        )
        for row in employee_day_rows
    }

    fact_keys = {
        (
            row["pegawai_id"],
            row["tanggal"],
        )
        for row in fact_rows
    }

    missing_keys = (
        employee_day_keys - fact_keys
    )

    unexpected_keys = (
        fact_keys - employee_day_keys
    )

    if missing_keys or unexpected_keys:
        raise ValueError(
            "fact_kehadiran key reconciliation gagal: "
            f"missing_keys={sorted(missing_keys)}, "
            f"unexpected_keys={sorted(unexpected_keys)}"
        )

    return True
