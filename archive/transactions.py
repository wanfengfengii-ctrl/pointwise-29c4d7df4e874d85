from collections.abc import Iterator
from contextlib import contextmanager
import sqlite3


@contextmanager
def write_transaction(db: sqlite3.Connection) -> Iterator[None]:
    # Reserve the writer before any read that determines whether to insert.
    db.execute('BEGIN IMMEDIATE')
    try:
        yield
        db.commit()
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
