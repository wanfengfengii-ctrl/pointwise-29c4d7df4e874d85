from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True, slots=True)
class SourceReceipt:
    source_id: str
    content: str
    revision: int


def ensure_receipt_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS source_receipts (
            source_id TEXT NOT NULL PRIMARY KEY,
            content TEXT NOT NULL,
            revision INTEGER NOT NULL UNIQUE REFERENCES waveform_revisions(id)
        ) WITHOUT ROWID
    ''')


def get_receipt(db: sqlite3.Connection, source_id: str) -> SourceReceipt | None:
    row = db.execute(
        'SELECT content, revision FROM source_receipts WHERE source_id = ?',
        (source_id,),
    ).fetchone()
    if row is None:
        return None
    return SourceReceipt(source_id, *row)


def insert_receipt(db: sqlite3.Connection, receipt: SourceReceipt) -> None:
    db.execute(
        'INSERT INTO source_receipts (source_id, content, revision) VALUES (?, ?, ?)',
        (receipt.source_id, receipt.content, receipt.revision),
    )
