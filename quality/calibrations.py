from dataclasses import dataclass
from fractions import Fraction
import sqlite3

from archive.transactions import write_transaction
from intake.validation import require_identifier


RationalInput = int | Fraction


@dataclass(frozen=True, slots=True)
class CalibrationRevision:
    revision: int
    channel: str
    scale: Fraction
    offset: Fraction


def exact_fraction(value: RationalInput, label: str) -> Fraction:
    if type(value) is int or isinstance(value, Fraction):
        return Fraction(value)
    raise ValueError(f'{label} must be an int or Fraction')


def fraction_fields(value: Fraction) -> tuple[str, str]:
    # Hexadecimal text preserves unbounded integers without SQLite coercion.
    return format(value.numerator, 'x'), format(value.denominator, 'x')


def fraction_from_fields(numerator: str, denominator: str) -> Fraction:
    return Fraction(int(numerator, 16), int(denominator, 16))


def ensure_calibration_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS calibrations (
            id INTEGER PRIMARY KEY,
            channel TEXT NOT NULL,
            scale_n TEXT NOT NULL,
            scale_d TEXT NOT NULL,
            offset_n TEXT NOT NULL,
            offset_d TEXT NOT NULL
        )
    ''')


def register_calibration(
    db: sqlite3.Connection, channel: str, scale: RationalInput, offset: RationalInput
) -> int:
    channel = require_identifier(channel, 'channel')
    factor = exact_fraction(scale, 'scale')
    bias = exact_fraction(offset, 'offset')
    with write_transaction(db):
        row = db.execute(
            '''INSERT INTO calibrations (channel, scale_n, scale_d, offset_n, offset_d)
               VALUES (?, ?, ?, ?, ?)''',
            (channel, *fraction_fields(factor), *fraction_fields(bias)),
        )
        return row.lastrowid


def get_calibration(db: sqlite3.Connection, revision: int) -> CalibrationRevision:
    if type(revision) is not int or not 1 <= revision < (1 << 63):
        raise KeyError(revision)
    row = db.execute(
        'SELECT channel, scale_n, scale_d, offset_n, offset_d FROM calibrations WHERE id = ?',
        (revision,),
    ).fetchone()
    if row is None:
        raise KeyError(revision)
    channel, scale_n, scale_d, offset_n, offset_d = row
    return CalibrationRevision(
        revision,
        channel,
        fraction_from_fields(scale_n, scale_d),
        fraction_from_fields(offset_n, offset_d),
    )
