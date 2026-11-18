from collections.abc import Iterator
from contextlib import closing
import sqlite3

from archive.raw_blocks import ArchiveIntegrityError, iter_overlapping_blocks
from archive.revisions import get_revision
from windows.bounds import WindowBounds, intersect_bounds, validate_window_bounds
from windows.time_axis import sample_time
from windows.views import RawSample, RawWindow


def _read_counts(
    db: sqlite3.Connection, revision: int, bounds: WindowBounds
) -> Iterator[int]:
    if not bounds.length:
        return
    next_index = bounds.lo
    with closing(iter_overlapping_blocks(db, revision, bounds.lo, bounds.hi)) as blocks:
        for block in blocks:
            overlap = intersect_bounds(bounds, block.start, block.stop)
            if overlap is None:
                continue
            if overlap.lo != next_index:
                raise ArchiveIntegrityError(
                    f'revision {revision} expected sample {next_index}, got {overlap.lo}'
                )
            yield from block.counts[overlap.lo - block.start:overlap.hi - block.start]
            next_index = overlap.hi
    if next_index != bounds.hi:
        raise ArchiveIntegrityError(f'revision {revision} has no sample at {next_index}')


def read_indexed_window(
    db: sqlite3.Connection, revision: int, lo: int, hi: int
) -> RawWindow:
    metadata = get_revision(db, revision)
    bounds = validate_window_bounds(metadata.length, lo, hi)
    samples = tuple(
        RawSample(index, count, sample_time(index, metadata.sample_rate))
        for index, count in enumerate(_read_counts(db, revision, bounds), bounds.lo)
    )
    return RawWindow(revision, metadata.channel, bounds, samples)


def read_window(db: sqlite3.Connection, revision: int, lo: int, hi: int) -> list[int]:
    return read_indexed_window(db, revision, lo, hi).counts()
