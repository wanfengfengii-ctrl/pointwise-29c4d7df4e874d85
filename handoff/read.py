from dataclasses import dataclass
import sqlite3

from handoff.bindings import ShiftBinding, StoredBinding, get_shift_binding
from handoff.reports import load_report
from intake.validation import require_identifier
from quality.assessment import Anomaly, WindowAssessment
from quality.summary import WindowSummary


@dataclass(frozen=True, slots=True)
class ShiftReport:
    binding: ShiftBinding
    assessment: WindowAssessment

    @property
    def anomalies(self) -> tuple[Anomaly, ...]:
        return self.assessment.anomalies

    @property
    def summary(self) -> WindowSummary:
        return self.assessment.summary


def read_bound_report(db: sqlite3.Connection, stored: StoredBinding) -> ShiftReport:
    return ShiftReport(stored.binding, load_report(db, stored.report_id))


def read_shift(db: sqlite3.Connection, shift_id: str) -> ShiftReport:
    try:
        require_identifier(shift_id, 'shift_id')
    except ValueError:
        raise KeyError(shift_id) from None
    stored = get_shift_binding(db, shift_id)
    if stored is None:
        raise KeyError(shift_id)
    return read_bound_report(db, stored)
