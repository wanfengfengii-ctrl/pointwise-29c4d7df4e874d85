from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from handoff.workspace import open_workspace
from intake.records import InstrumentRecord


class IntakeTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / 'archive.sqlite3'
        self.workspace = self.enterContext(open_workspace(self.path))
        self.record = InstrumentRecord('R1', 'Q07', '垂向', 3, 3, [-2, 0, 4])

    def archive_rows(self):
        with closing(sqlite3.connect(self.path)) as db:
            return (
                db.execute('SELECT COUNT(*) FROM waveform_revisions').fetchone()[0],
                db.execute('SELECT COUNT(*) FROM raw_blocks').fetchone()[0],
                db.execute('SELECT COUNT(*) FROM waveform_heads').fetchone()[0],
                db.execute('SELECT COUNT(*) FROM source_receipts').fetchone()[0],
            )

    def test_replay(self):
        first = self.workspace.register_raw(replace(self.record, counts=iter([-2, 0, 4])))
        self.assertEqual(self.workspace.register_raw(self.record), first)
        self.assertEqual(self.workspace.get_head('Q07'), first)
        self.assertEqual(self.workspace.read_window(first, 0, 2), [-2, 0])
        self.assertEqual(self.archive_rows(), (1, 1, 1, 1))

    def test_empty_record(self):
        empty = replace(self.record, declared_length=0, counts=[])
        revision = self.workspace.register_raw(empty)
        self.assertEqual(self.workspace.register_raw(empty), revision)
        self.assertEqual(self.workspace.get_head('Q07'), revision)
        self.assertEqual(self.workspace.read_window(revision, 0, 0), [])
        self.assertEqual(self.archive_rows(), (1, 0, 1, 1))

    def test_truncated(self):
        with self.assertRaises(ValueError):
            self.workspace.register_raw(replace(self.record, counts=[-2, 0]))
        self.assertEqual(self.archive_rows(), (0, 0, 0, 0))
        revision = self.workspace.register_raw(self.record)
        self.assertEqual(self.workspace.read_window(revision, 0, 3), [-2, 0, 4])

    def test_input_domain(self):
        invalid_fields = (
            {'source_id': ' '}, {'trace_id': '\t'}, {'channel': ''},
            {'sample_rate': 0}, {'sample_rate': -3}, {'sample_rate': True},
            {'sample_rate': 3.0}, {'declared_length': -1}, {'declared_length': True},
            {'counts': [-2, 0.0, 4]}, {'counts': [-2, False, 4]}, {'counts': None},
            {'counts': {-2, 0, 4}},
        )
        for change in invalid_fields:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.workspace.register_raw(replace(self.record, **change))
        self.assertEqual(self.archive_rows(), (0, 0, 0, 0))
        revision = self.workspace.register_raw(self.record)
        spaced = self.workspace.register_raw(replace(self.record, source_id=' R1 '))
        self.assertNotEqual(revision, spaced)
        self.assertEqual(self.workspace.register_raw(self.record), revision)
        self.assertEqual(self.workspace.get_head('Q07'), spaced)

    def test_source_conflict(self):
        first = self.workspace.register_raw(self.record)
        with self.assertRaises(ValueError):
            self.workspace.register_raw(replace(self.record, counts=[-2, 1, 4]))
        self.assertEqual(self.workspace.read_window(first, 0, 3), [-2, 0, 4])
        self.assertEqual(self.workspace.register_raw(self.record), first)
        self.assertEqual(self.archive_rows(), (1, 1, 1, 1))

    def test_identity_fields(self):
        first = self.workspace.register_raw(self.record)
        changes = (
            {'trace_id': 'Q08'}, {'channel': '横向'}, {'sample_rate': 4},
            {'declared_length': 2, 'counts': [-2, 0]}, {'counts': [0, -2, 4]},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.workspace.register_raw(replace(self.record, **change))
        self.assertEqual(self.workspace.get_head('Q07'), first)
        self.assertEqual(self.archive_rows(), (1, 1, 1, 1))

    def test_replay_after_correction(self):
        old = self.workspace.register_raw(self.record)
        correction = replace(self.record, source_id='R2', counts=[-4, 0, 2])
        new = self.workspace.register_raw(correction)
        self.assertNotEqual(old, new)
        self.assertEqual(self.workspace.get_head('Q07'), new)
        self.assertEqual(self.workspace.register_raw(self.record), old)
        self.assertEqual(self.workspace.get_head('Q07'), new)
        self.assertEqual(self.workspace.read_window(old, 0, 3), [-2, 0, 4])
        self.assertEqual(self.workspace.read_window(new, 0, 3), [-4, 0, 2])
        self.assertEqual(self.archive_rows(), (2, 2, 1, 2))

    def test_atomic_record(self):
        old = self.workspace.register_raw(self.record)
        correction = replace(self.record, source_id='R2', counts=[-4, 0, 2])
        before = self.archive_rows()
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute('''
                CREATE TRIGGER reject_receipt BEFORE INSERT ON source_receipts
                WHEN NEW.source_id = 'R2'
                BEGIN SELECT RAISE(ABORT, 'receipt unavailable'); END
            ''')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt unavailable'):
                self.workspace.register_raw(correction)
            self.assertIsNone(db.execute(
                'SELECT revision FROM source_receipts WHERE source_id = ?', ('R2',)
            ).fetchone())
            self.assertEqual(self.archive_rows(), before)
            self.assertEqual(self.workspace.get_head('Q07'), old)
            self.assertEqual(self.workspace.read_window(old, 0, 3), [-2, 0, 4])
            db.execute('DROP TRIGGER reject_receipt')
        new = self.workspace.register_raw(correction)
        self.assertEqual(self.workspace.get_head('Q07'), new)
        self.assertEqual(self.workspace.read_window(new, 0, 3), [-4, 0, 2])
        self.assertEqual(self.archive_rows(), (2, 2, 1, 2))
