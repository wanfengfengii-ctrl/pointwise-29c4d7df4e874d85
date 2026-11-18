from fractions import Fraction
import sqlite3

from handoff.jsonio import deterministic_json
from handoff.read import read_shift


def _fraction_object(value: Fraction | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {'numerator': value.numerator, 'denominator': value.denominator}


def export_shift(db: sqlite3.Connection, shift_id: str) -> str:
    report = read_shift(db, shift_id)
    binding = report.binding
    summary = report.summary
    payload = {
        'shift_id': binding.shift_id,
        'waveform_revision': binding.waveform_revision,
        'calibration_revision': binding.calibration_revision,
        'window': {'lo': binding.bounds.lo, 'hi': binding.bounds.hi},
        'limits': {
            'lower': _fraction_object(binding.limits.lower),
            'upper': _fraction_object(binding.limits.upper),
        },
        'summary': {
            'sample_count': summary.sample_count,
            'anomaly_count': summary.anomaly_count,
            'minimum': _fraction_object(summary.minimum),
            'maximum': _fraction_object(summary.maximum),
        },
        'anomalies': [
            {
                'index': point.index,
                'count': point.count,
                'seconds': _fraction_object(point.seconds),
                'value': _fraction_object(point.value),
                'side': point.side,
            }
            for point in report.anomalies
        ],
    }
    return deterministic_json(payload)
