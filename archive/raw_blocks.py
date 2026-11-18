from collections.abc import Iterator
from dataclasses import dataclass
import json
import sqlite3


RAW_BLOCK_SIZE = 64


class ArchiveIntegrityError(RuntimeError):
    """持久块无法完整、唯一地提供请求的样点。"""


@dataclass(frozen=True, slots=True)
class RawBlock:
    start: int
    stop: int
    counts: tuple[int, ...]


def ensure_block_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS raw_blocks (
            revision INTEGER NOT NULL REFERENCES waveform_revisions(id),
            start INTEGER NOT NULL CHECK (start >= 0),
            stop INTEGER NOT NULL CHECK (stop > start),
            payload TEXT NOT NULL,
            PRIMARY KEY (revision, start)
        ) WITHOUT ROWID
    ''')


def insert_raw_blocks(
    db: sqlite3.Connection, revision: int, counts: tuple[int, ...]
) -> None:
    def rows() -> Iterator[tuple[int, int, int, str]]:
        for start in range(0, len(counts), RAW_BLOCK_SIZE):
            segment = counts[start:start + RAW_BLOCK_SIZE]
            payload = json.dumps([format(count, 'x') for count in segment])
            yield revision, start, start + len(segment), payload

    db.executemany(
        'INSERT INTO raw_blocks (revision, start, stop, payload) VALUES (?, ?, ?, ?)',
        rows(),
    )


def iter_overlapping_blocks(
    db: sqlite3.Connection, revision: int, lo: int, hi: int
) -> Iterator[RawBlock]:
    if lo == hi:
        return
    with_cursor = db.execute(
        '''SELECT start, stop, payload FROM raw_blocks
           WHERE revision = ? AND start < ? AND stop > ? ORDER BY start''',
        (revision, hi, lo),
    )
    try:
        for start, stop, payload in with_cursor:
            try:
                fields = json.loads(payload)
                if not isinstance(fields, list) or len(fields) != stop - start:
                    raise ValueError('block length does not match its payload')
                counts = tuple(int(field, 16) for field in fields)
            except (TypeError, ValueError) as error:
                raise ArchiveIntegrityError(
                    f'invalid block at sample {start} of revision {revision}'
                ) from error
            yield RawBlock(start, stop, counts)
    finally:
        with_cursor.close()
