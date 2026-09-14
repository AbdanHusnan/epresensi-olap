from dataclasses import dataclass


@dataclass(frozen=True)
class FactKehadiranConfig:
    """
    Konfigurasi eksekusi pipeline fact_kehadiran.

    Tahap saat ini:
    - belum melakukan initial load
    - belum mengaktifkan write ke OLAP
    - belum mengintegrasikan perizinan
    """

    work_code: int = 1

    # Selama konfigurasi awal, pipeline hanya boleh dry-run.
    dry_run: bool = True

    # Safety switch.
    # Harus tetap False sampai kita memang siap melakukan load.
    enable_write: bool = False

    # t_perizinan belum termasuk scope tahap ini.
    enable_perizinan: bool = False


def get_default_config():
    return FactKehadiranConfig()


def validate_config(config):
    if config.work_code != 1:
        raise ValueError(
            "fact_kehadiran saat ini hanya dikonfigurasi "
            "untuk work_code = 1"
        )

    if config.enable_write and config.dry_run:
        raise ValueError(
            "Konfigurasi tidak valid: "
            "enable_write=True tetapi dry_run=True"
        )

    if config.enable_perizinan:
        raise ValueError(
            "Integrasi perizinan belum diaktifkan "
            "pada tahap konfigurasi fact_kehadiran saat ini"
        )

    return True
