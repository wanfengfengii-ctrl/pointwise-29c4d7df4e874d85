from fractions import Fraction
import json
import sqlite3

from quality.assessment import Anomaly, WindowAssessment
from quality.calibrations import fraction_fields, fraction_from_fields
from quality.summary import WindowSummary


def ensure_report_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS shift_reports (
            id INTEGER PRIMARY KEY,
            payload TEXT NOT NULL
        )
    ''')


def _optional_fraction_fields(value: Fraction | None) -> tuple[str, str] | None:
    return None if value is None else fraction_fields(value)


def _optional_fraction(fields: list[str] | None) -> Fraction | None:
    return None if fields is None else fraction_from_fields(*fields)


def insert_report(db: sqlite3.Connection, assessment: WindowAssessment) -> int:
    summary = assessment.summary
    payload = {
        'sample_count': summary.sample_count,
        'anomaly_count': summary.anomaly_count,
        'minimum': _optional_fraction_fields(summary.minimum),
        'maximum': _optional_fraction_fields(summary.maximum),
        'anomalies': [
            {
                'index': point.index,
                'count_hex': format(point.count, 'x'),
                'seconds': fraction_fields(point.seconds),
                'value': fraction_fields(point.value),
                'side': point.side,
            }
            for point in assessment.anomalies
        ],
    }
    row = db.execute(
        'INSERT INTO shift_reports (payload) VALUES (?)',
        (json.dumps(payload, separators=(',', ':')),),
    )
    return row.lastrowid


def load_report(db: sqlite3.Connection, report_id: int) -> WindowAssessment:
    row = db.execute('SELECT payload FROM shift_reports WHERE id = ?', (report_id,)).fetchone()
    if row is None:
        raise sqlite3.DatabaseError(f'missing report {report_id} referenced by shift binding')
    payload = json.loads(row[0])
    anomalies = tuple(
        Anomaly(
            point['index'],
            int(point['count_hex'], 16),
            fraction_from_fields(*point['seconds']),
            fraction_from_fields(*point['value']),
            point['side'],
        )
        for point in payload['anomalies']
    )
    summary = WindowSummary(
        payload['sample_count'],
        payload['anomaly_count'],
        _optional_fraction(payload['minimum']),
        _optional_fraction(payload['maximum']),
    )
    return WindowAssessment(anomalies, summary)
