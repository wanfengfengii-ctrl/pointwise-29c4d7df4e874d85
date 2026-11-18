from contextlib import closing
from fractions import Fraction
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from archive.raw_blocks import ArchiveIntegrityError, RAW_BLOCK_SIZE
from handoff.workspace import open_workspace
from intake.records import InstrumentRecord
from windows.bounds import WindowBounds
from windows.views import RawSample


class WindowTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / 'archive.sqlite3'
        self.workspace = self.enterContext(open_workspace(self.path))

    def register(self, values):
        return self.workspace.register_raw(InstrumentRecord('R1', 'Q07', '垂向', 3, len(values), values))

    def test_bounds(self):
        revision = self.register([-2, 0, 4])
        with self.assertRaises(ValueError):
            self.workspace.read_window(revision, 2, 4)
        self.assertEqual(self.workspace.read_window(revision, 3, 3), [])

    def test_bounds_edges(self):
        revision = self.register([-2, 0, 4])
        for unknown in (revision + 1, 1 << 100):
            with self.subTest(unknown=unknown), self.assertRaises(KeyError):
                self.workspace.read_window(unknown, 0, 0)
        for lo, hi in ((-1, 2), (2, 1), (4, 4), (True, 2), (0, 1.0)):
            with self.subTest(lo=lo, hi=hi), self.assertRaises(ValueError):
                self.workspace.read_window(revision, lo, hi)
        empty = self.workspace.read_indexed_window(revision, 1, 1)
        self.assertEqual(empty.revision, revision)
        self.assertEqual(empty.bounds, WindowBounds(1, 1))
        self.assertEqual(empty.samples, ())
        self.assertEqual(self.workspace.read_window(revision, 1, 2), [0])

    def test_block_continuity(self):
        boundary = RAW_BLOCK_SIZE
        revision = self.register(list(range(boundary + 3)))
        expected = [boundary - 1, boundary, boundary + 1]
        self.assertEqual(self.workspace.read_window(revision, boundary - 1, boundary + 2), expected)
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute('DELETE FROM raw_blocks WHERE revision = ? AND start = ?', (revision, boundary))
        self.assertEqual(self.workspace.read_window(revision, boundary, boundary), [])
        with self.assertRaises(ArchiveIntegrityError):
            self.workspace.read_window(revision, boundary - 1, boundary + 2)
        calibration = self.workspace.register_calibration('垂向', 1, 0)
        with self.assertRaises(ArchiveIntegrityError):
            self.workspace.publish_shift('S1', revision, boundary - 1, boundary + 2, calibration, 0, 2)
        with self.assertRaises(KeyError):
            self.workspace.read_shift('S1')

    def test_overlapping_blocks_are_rejected(self):
        boundary = RAW_BLOCK_SIZE
        revision = self.register(list(range(boundary + 3)))
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute(
                'INSERT INTO raw_blocks (revision, start, stop, payload) VALUES (?, ?, ?, ?)',
                (revision, boundary - 1, boundary + 1, '["0","0"]'),
            )
        with self.assertRaises(ArchiveIntegrityError):
            self.workspace.read_window(revision, boundary - 1, boundary + 1)

    def test_exact_time(self):
        revision = self.register([-2, 0, 4])
        window = self.workspace.read_indexed_window(revision, 1, 3)
        self.assertEqual(window.bounds, WindowBounds(1, 3))
        self.assertEqual(window.channel, '垂向')
        self.assertEqual(window.samples, (RawSample(1, 0, Fraction(1, 3)), RawSample(2, 4, Fraction(2, 3))))
