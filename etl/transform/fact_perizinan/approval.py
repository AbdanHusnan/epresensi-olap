def apply_approval_rule(row):
    """
    Menentukan status administratif pengajuan izin.

    Rule:
        approval = True  -> APPROVED
        approval = False -> REJECTED
        approval = None  -> PENDING

    is_izin_valid hanya True untuk APPROVED.

    Fungsi ini TIDAK menentukan status kehadiran.
    """

    approval = row.get("approval")

    if approval is True:
        status_perizinan = "APPROVED"
        is_izin_valid = True

    elif approval is False:
        status_perizinan = "REJECTED"
        is_izin_valid = False

    else:
        status_perizinan = "PENDING"
        is_izin_valid = False

    return {
        **row,
        "status_perizinan": status_perizinan,
        "is_izin_valid": is_izin_valid,
    }


def apply_approval_rules(rows):
    """
    Apply approval rule untuk seluruh pengajuan.
    """

    return [
        apply_approval_rule(row)
        for row in rows
    ]
