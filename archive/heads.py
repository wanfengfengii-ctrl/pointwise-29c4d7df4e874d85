import sqlite3


def ensure_head_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS waveform_heads (
            trace_id TEXT NOT NULL PRIMARY KEY,
            revision INTEGER NOT NULL REFERENCES waveform_revisions(id)
        ) WITHOUT ROWID
    ''')


def get_head(db: sqlite3.Connection, trace_id: str) -> int:
    row = db.execute(
        'SELECT revision FROM waveform_heads WHERE trace_id = ?', (trace_id,)
    ).fetchone()
    if row is None:
        raise KeyError(trace_id)
    return row[0]


def set_head(db: sqlite3.Connection, trace_id: str, revision: int) -> None:
    db.execute(
        '''INSERT INTO waveform_heads (trace_id, revision) VALUES (?, ?)
           ON CONFLICT (trace_id) DO UPDATE SET revision = excluded.revision''',
        (trace_id, revision),
    )
