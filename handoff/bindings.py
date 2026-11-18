from dataclasses import dataclass
import sqlite3

from quality.calibrations import fraction_fields, fraction_from_fields
from quality.limits import LimitBand
from windows.bounds import WindowBounds


@dataclass(frozen=True, slots=True)
class ShiftBinding:
    shift_id: str
    waveform_revision: int
    calibration_revision: int
    bounds: WindowBounds
    limits: LimitBand


@dataclass(frozen=True, slots=True)
class StoredBinding:
    binding: ShiftBinding
    report_id: int


def ensure_binding_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS shift_bindings (
            shift_id TEXT NOT NULL PRIMARY KEY,
            waveform_revision INTEGER NOT NULL REFERENCES waveform_revisions(id),
            calibration_revision INTEGER NOT NULL REFERENCES calibrations(id),
            lo INTEGER NOT NULL CHECK (lo >= 0),
            hi INTEGER NOT NULL CHECK (hi >= lo),
            lower_n TEXT NOT NULL,
            lower_d TEXT NOT NULL,
            upper_n TEXT NOT NULL,
            upper_d TEXT NOT NULL,
            report_id INTEGER NOT NULL UNIQUE REFERENCES shift_reports(id)
        ) WITHOUT ROWID
    ''')


def get_shift_binding(db: sqlite3.Connection, shift_id: str) -> StoredBinding | None:
    row = db.execute(
        '''SELECT waveform_revision, calibration_revision, lo, hi,
                  lower_n, lower_d, upper_n, upper_d, report_id
           FROM shift_bindings WHERE shift_id = ?''',
        (shift_id,),
    ).fetchone()
    if row is None:
        return None
    waveform, calibration, lo, hi, lower_n, lower_d, upper_n, upper_d, report_id = row
    bounds = WindowBounds(lo, hi)
    limits = LimitBand(
        fraction_from_fields(lower_n, lower_d), fraction_from_fields(upper_n, upper_d)
    )
    return StoredBinding(ShiftBinding(shift_id, waveform, calibration, bounds, limits), report_id)


def insert_shift_binding(db: sqlite3.Connection, binding: ShiftBinding, report_id: int) -> None:
    db.execute(
        '''INSERT INTO shift_bindings (
               shift_id, waveform_revision, calibration_revision, lo, hi,
               lower_n, lower_d, upper_n, upper_d, report_id
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            binding.shift_id,
            binding.waveform_revision,
            binding.calibration_revision,
            binding.bounds.lo,
            binding.bounds.hi,
            *fraction_fields(binding.limits.lower),
            *fraction_fields(binding.limits.upper),
            report_id,
        ),
    )


def same_binding(existing: StoredBinding, proposed: ShiftBinding) -> bool:
    return existing.binding == proposed
