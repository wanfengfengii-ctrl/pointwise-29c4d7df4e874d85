from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True, slots=True)
class WaveformRevision:
    revision: int
    trace_id: str
    channel: str
    sample_rate: int
    length: int


def ensure_revision_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS waveform_revisions (
            id INTEGER PRIMARY KEY,
            trace_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            rate_hex TEXT NOT NULL,
            sample_count INTEGER NOT NULL CHECK (sample_count >= 0)
        )
    ''')


def insert_revision(
    db: sqlite3.Connection,
    trace_id: str,
    channel: str,
    sample_rate: int,
    length: int,
) -> int:
    row = db.execute(
        '''INSERT INTO waveform_revisions (trace_id, channel, rate_hex, sample_count)
           VALUES (?, ?, ?, ?)''',
        (trace_id, channel, format(sample_rate, 'x'), length),
    )
    return row.lastrowid


def get_revision(db: sqlite3.Connection, revision: int) -> WaveformRevision:
    if type(revision) is not int or not 1 <= revision < (1 << 63):
        raise KeyError(revision)
    row = db.execute(
        '''SELECT trace_id, channel, rate_hex, sample_count
           FROM waveform_revisions WHERE id = ?''',
        (revision,),
    ).fetchone()
    if row is None:
        raise KeyError(revision)
    trace_id, channel, rate_hex, length = row
    return WaveformRevision(revision, trace_id, channel, int(rate_hex, 16), length)
