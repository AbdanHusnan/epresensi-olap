"""Keep generated validation and audit reports outside maintained documentation."""
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / 'logs' / 'reports'


def report_path(name: str) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    return REPORTS / name
