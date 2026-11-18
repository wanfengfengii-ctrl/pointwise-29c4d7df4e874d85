from dataclasses import dataclass
import sqlite3

from quality.calibrations import fraction_fields, fraction_from_fields
from quality.limits import LimitBand


@dataclass(frozen=True, slots=True)
class ReviewBinding:
    plan_id: str
    shift_ids: tuple[str, ...]
    waveform_revision: int
    calibration_revision: int
    limits: LimitBand
    max_segments: int
    max_samples: int


@dataclass(frozen=True, slots=True)
class StoredReviewBinding:
    binding: ReviewBinding
    report_id: int


def ensure_review_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS review_reports (
            id INTEGER PRIMARY KEY,
            payload TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS review_plans (
            plan_id TEXT NOT NULL PRIMARY KEY,
            waveform_revision INTEGER NOT NULL REFERENCES waveform_revisions(id),
            calibration_revision INTEGER NOT NULL REFERENCES calibrations(id),
            lower_n TEXT NOT NULL,
            lower_d TEXT NOT NULL,
            upper_n TEXT NOT NULL,
            upper_d TEXT NOT NULL,
            max_segments INTEGER NOT NULL CHECK (max_segments >= 0),
            max_samples INTEGER NOT NULL CHECK (max_samples >= 0),
            report_id INTEGER NOT NULL UNIQUE REFERENCES review_reports(id)
        ) WITHOUT ROWID
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS review_plan_sources (
            plan_id TEXT NOT NULL REFERENCES review_plans(plan_id),
            shift_id TEXT NOT NULL REFERENCES shift_bindings(shift_id),
            ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
            PRIMARY KEY (plan_id, shift_id)
        ) WITHOUT ROWID
    ''')


def get_review_binding(db: sqlite3.Connection, plan_id: str) -> StoredReviewBinding | None:
    row = db.execute(
        '''SELECT waveform_revision, calibration_revision, lower_n, lower_d,
                  upper_n, upper_d, max_segments, max_samples, report_id
           FROM review_plans WHERE plan_id = ?''',
        (plan_id,),
    ).fetchone()
    if row is None:
        return None
    (
        waveform, calibration, lower_n, lower_d, upper_n, upper_d,
        max_segments, max_samples, report_id,
    ) = row
    source_rows = db.execute(
        'SELECT shift_id FROM review_plan_sources WHERE plan_id = ? ORDER BY ordinal',
        (plan_id,),
    ).fetchall()
    binding = ReviewBinding(
        plan_id,
        tuple(source_id for (source_id,) in source_rows),
        waveform,
        calibration,
        LimitBand(fraction_from_fields(lower_n, lower_d),
                  fraction_from_fields(upper_n, upper_d)),
        max_segments,
        max_samples,
    )
    return StoredReviewBinding(binding, report_id)


def insert_review_binding(
    db: sqlite3.Connection, binding: ReviewBinding, report_id: int
) -> None:
    db.execute(
        '''INSERT INTO review_plans (
               plan_id, waveform_revision, calibration_revision, lower_n, lower_d,
               upper_n, upper_d, max_segments, max_samples, report_id
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            binding.plan_id,
            binding.waveform_revision,
            binding.calibration_revision,
            *fraction_fields(binding.limits.lower),
            *fraction_fields(binding.limits.upper),
            binding.max_segments,
            binding.max_samples,
            report_id,
        ),
    )
    db.executemany(
        'INSERT INTO review_plan_sources (plan_id, shift_id, ordinal) VALUES (?, ?, ?)',
        [
            (binding.plan_id, shift_id, ordinal)
            for ordinal, shift_id in enumerate(binding.shift_ids)
        ],
    )
