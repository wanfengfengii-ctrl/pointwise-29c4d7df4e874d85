import sqlite3

from archive.revisions import get_revision
from archive.transactions import write_transaction
from handoff.bindings import ShiftBinding, get_shift_binding, insert_shift_binding, same_binding
from handoff.read import ShiftReport, read_bound_report
from handoff.reports import insert_report
from intake.validation import require_identifier
from quality.assessment import assess_window
from quality.calibrations import RationalInput, get_calibration
from quality.limits import validate_limits
from windows.bounds import validate_window_bounds
from windows.raw_reader import read_indexed_window


def publish_shift(
    db: sqlite3.Connection,
    shift_id: str,
    waveform_revision: int,
    lo: int,
    hi: int,
    calibration_revision: int,
    lower: RationalInput,
    upper: RationalInput,
) -> ShiftReport:
    shift_id = require_identifier(shift_id, 'shift_id')
    with write_transaction(db):
        waveform = get_revision(db, waveform_revision)
        calibration = get_calibration(db, calibration_revision)
        bounds = validate_window_bounds(waveform.length, lo, hi)
        limits = validate_limits(lower, upper)
        binding = ShiftBinding(shift_id, waveform_revision, calibration_revision, bounds, limits)

        existing = get_shift_binding(db, shift_id)
        if existing is not None:
            if not same_binding(existing, binding):
                raise ValueError(f'conflicting binding for shift {shift_id!r}')
            return read_bound_report(db, existing)

        window = read_indexed_window(db, waveform_revision, bounds.lo, bounds.hi)
        assessment = assess_window(window, calibration, limits)
        report_id = insert_report(db, assessment)
        insert_shift_binding(db, binding, report_id)
        return ShiftReport(binding, assessment)
