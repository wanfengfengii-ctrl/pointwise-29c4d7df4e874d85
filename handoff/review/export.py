from fractions import Fraction
import sqlite3

from handoff.jsonio import deterministic_json
from handoff.review.read import read_review_plan


def _fraction_object(value: Fraction) -> dict[str, int]:
    return {'numerator': value.numerator, 'denominator': value.denominator}


def export_review_plan(db: sqlite3.Connection, plan_id: str) -> str:
    plan = read_review_plan(db, plan_id)
    payload = {
        'plan_id': plan['plan_id'],
        'shift_ids': list(plan['shift_ids']),
        'waveform_revision': plan['waveform_revision'],
        'calibration_revision': plan['calibration_revision'],
        'limits': {
            'lower': _fraction_object(plan['limits']['lower']),
            'upper': _fraction_object(plan['limits']['upper']),
        },
        'max_segments': plan['max_segments'],
        'max_samples': plan['max_samples'],
        'segments': [list(segment) for segment in plan['segments']],
        'covered_indices': list(plan['covered_indices']),
        'total_samples': plan['total_samples'],
    }
    return deterministic_json(payload)
