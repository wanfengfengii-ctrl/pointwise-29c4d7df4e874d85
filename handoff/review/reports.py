from dataclasses import dataclass
import json
import sqlite3

from handoff.jsonio import deterministic_json


@dataclass(frozen=True, slots=True)
class ReviewVerdict:
    segments: tuple[tuple[int, int], ...]
    covered_indices: tuple[int, ...]
    total_samples: int


def insert_review_report(db: sqlite3.Connection, verdict: ReviewVerdict) -> int:
    payload = {
        'segments': [[lo, hi] for lo, hi in verdict.segments],
        'covered_indices': list(verdict.covered_indices),
        'total_samples': verdict.total_samples,
    }
    row = db.execute(
        'INSERT INTO review_reports (payload) VALUES (?)',
        (deterministic_json(payload),),
    )
    return row.lastrowid


def load_review_report(db: sqlite3.Connection, report_id: int) -> ReviewVerdict:
    row = db.execute(
        'SELECT payload FROM review_reports WHERE id = ?', (report_id,)
    ).fetchone()
    if row is None:
        raise sqlite3.DatabaseError(
            f'missing review report {report_id} referenced by review plan'
        )
    payload = json.loads(row[0])
    return ReviewVerdict(
        tuple((segment[0], segment[1]) for segment in payload['segments']),
        tuple(payload['covered_indices']),
        payload['total_samples'],
    )
