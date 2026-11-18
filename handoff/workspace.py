from __future__ import annotations

import argparse
from fractions import Fraction
import json
from os import PathLike
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from archive.heads import ensure_head_schema, get_head
from archive.raw_blocks import ensure_block_schema
from archive.revisions import ensure_revision_schema
from archive.transactions import write_transaction
from handoff.bindings import ensure_binding_schema
from handoff.export import export_shift
from handoff.publish import publish_shift
from handoff.read import ShiftReport, read_shift
from handoff.reports import ensure_report_schema
from intake.receipts import ensure_receipt_schema
from intake.records import InstrumentRecord
from intake.register import register_raw
from quality.calibrations import RationalInput, ensure_calibration_schema, register_calibration
from windows.raw_reader import read_indexed_window, read_window
from windows.views import RawWindow


class ArchiveWorkspace:
    def __init__(self, database: str | PathLike[str]) -> None:
        db = sqlite3.connect(database, isolation_level=None)
        try:
            db.execute('PRAGMA foreign_keys = ON')
            with write_transaction(db):
                ensure_revision_schema(db)
                ensure_block_schema(db)
                ensure_head_schema(db)
                ensure_receipt_schema(db)
                ensure_calibration_schema(db)
                ensure_report_schema(db)
                ensure_binding_schema(db)
        except BaseException:
            db.close()
            raise
        self._db = db

    def __enter__(self) -> ArchiveWorkspace:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._db.close()

    def register_raw(self, record: InstrumentRecord) -> int:
        return register_raw(self._db, record)

    def get_head(self, trace_id: str) -> int:
        return get_head(self._db, trace_id)

    def read_window(self, revision: int, lo: int, hi: int) -> list[int]:
        return read_window(self._db, revision, lo, hi)

    def read_indexed_window(self, revision: int, lo: int, hi: int) -> RawWindow:
        return read_indexed_window(self._db, revision, lo, hi)

    def register_calibration(self, channel: str, scale: RationalInput, offset: RationalInput) -> int:
        return register_calibration(self._db, channel, scale, offset)

    def publish_shift(
        self,
        shift_id: str,
        waveform_revision: int,
        lo: int,
        hi: int,
        calibration_revision: int,
        lower: RationalInput,
        upper: RationalInput,
    ) -> ShiftReport:
        return publish_shift(
            self._db, shift_id, waveform_revision, lo, hi, calibration_revision, lower, upper
        )

    def read_shift(self, shift_id: str) -> ShiftReport:
        return read_shift(self._db, shift_id)

    def export_shift(self, shift_id: str) -> str:
        return export_shift(self._db, shift_id)


def open_workspace(database: str | PathLike[str]) -> ArchiveWorkspace:
    return ArchiveWorkspace(database)


def _demo(sample_path: Path) -> None:
    with sample_path.open(encoding='utf-8') as stream:
        sample = json.load(stream)
    original = InstrumentRecord(**sample['original'])
    correction = InstrumentRecord(**sample['correction'])
    calibration = sample['calibration']
    lo, hi = sample['window']
    lower, upper = (Fraction(value) for value in sample['limits'])
    old_number, new_number = sample['shift_ids']

    with TemporaryDirectory(prefix='vibration-demo-') as directory:
        database = Path(directory) / 'archive.sqlite3'
        with open_workspace(database) as workspace:
            old_revision = workspace.register_raw(original)
            trial = workspace.read_window(old_revision, 0, min(2, original.declared_length))
            print(json.dumps({'trial_revision': old_revision, 'counts': trial}))
            calibration_revision = workspace.register_calibration(
                calibration['channel'], Fraction(calibration['scale']), Fraction(calibration['offset'])
            )
            workspace.publish_shift(old_number, old_revision, lo, hi, calibration_revision, lower, upper)
            exported_before = workspace.export_shift(old_number)
            new_revision = workspace.register_raw(correction)

        with open_workspace(database) as workspace:
            exported_after = workspace.export_shift(old_number)
            if exported_after != exported_before:
                raise RuntimeError('historical export changed after correction and reopen')
            workspace.publish_shift(new_number, new_revision, lo, hi, calibration_revision, lower, upper)
            print(exported_after)
            print(workspace.export_shift(new_number))


def main() -> None:
    parser = argparse.ArgumentParser(description='Run the crane vibration archive demo')
    parser.add_argument('command', choices=('demo',))
    parser.add_argument('sample', type=Path)
    args = parser.parse_args()
    _demo(args.sample)


if __name__ == '__main__':
    main()
