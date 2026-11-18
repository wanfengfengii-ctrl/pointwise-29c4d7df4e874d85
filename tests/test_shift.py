from contextlib import closing
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from archive.raw_blocks import RAW_BLOCK_SIZE
from handoff.workspace import open_workspace
from intake.records import InstrumentRecord
from quality.assessment import Anomaly
from quality.summary import WindowSummary


class ShiftTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / 'archive.sqlite3'
        self.workspace = self.enterContext(open_workspace(self.path))

    def waveform(self, counts, source_id='R1', rate=3):
        return self.workspace.register_raw(
            InstrumentRecord(source_id, 'Q07', '垂向', rate, len(counts), counts)
        )

    def shift_rows(self):
        with closing(sqlite3.connect(self.path)) as db:
            return (
                db.execute('SELECT COUNT(*) FROM shift_reports').fetchone()[0],
                db.execute('SELECT COUNT(*) FROM shift_bindings').fetchone()[0],
            )

    def test_exact_limits(self):
        revision = self.waveform([-2, 0, 4])
        calibration = self.workspace.register_calibration('垂向', Fraction(1, 2), 1)
        report = self.workspace.publish_shift('S1', revision, 0, 3, calibration, 0, 2)
        self.assertEqual(report.binding.waveform_revision, revision)
        self.assertEqual(report.binding.calibration_revision, calibration)
        self.assertEqual(report.anomalies, (Anomaly(2, 4, Fraction(2, 3), Fraction(3), 'high'),))
        self.assertEqual(report.summary, WindowSummary(3, 1, Fraction(0), Fraction(3)))
        middle = self.workspace.publish_shift('S-mid', revision, 1, 2, calibration, 0, 2)
        self.assertEqual(middle.summary, WindowSummary(1, 0, Fraction(1), Fraction(1)))
        self.assertEqual(self.workspace.read_shift('S1'), report)

    def test_limit_edges(self):
        revision = self.waveform([-1, 0, 1, 2, 3])
        calibration = self.workspace.register_calibration('垂向', 1, 0)
        report = self.workspace.publish_shift('S1', revision, 0, 5, calibration, 0, 2)
        self.assertEqual([(p.index, p.side) for p in report.anomalies], [(0, 'low'), (4, 'high')])
        equal = self.workspace.publish_shift('S2', revision, 0, 5, calibration, 1, 1)
        self.assertEqual([(p.index, p.side) for p in equal.anomalies], [
            (0, 'low'), (1, 'low'), (3, 'high'), (4, 'high')
        ])
        for lower, upper in ((2, 0), (False, 1), (0, 2.0)):
            with self.subTest(lower=lower, upper=upper), self.assertRaises(ValueError):
                self.workspace.publish_shift('S3', revision, 0, 5, calibration, lower, upper)
        with self.assertRaises(KeyError):
            self.workspace.read_shift('S3')
        self.assertEqual(self.shift_rows(), (2, 2))

    def test_precision(self):
        revision = self.waveform([1, 2, 3])
        denominator = 2**60
        calibration = self.workspace.register_calibration('垂向', Fraction(1, denominator), 1)
        report = self.workspace.publish_shift(
            'S1', revision, 0, 3, calibration, 0, Fraction(denominator + 2, denominator)
        )
        self.assertEqual(report.anomalies, (
            Anomaly(2, 3, Fraction(2, 3), Fraction(denominator + 3, denominator), 'high'),
        ))
        self.assertEqual(report.summary, WindowSummary(
            3, 1, Fraction(denominator + 1, denominator), Fraction(denominator + 3, denominator)
        ))
        self.assertEqual(self.workspace.read_shift('S1'), report)

    def test_large_integer_export(self):
        large = 10**4600 + 3
        rate = large + 4
        revision = self.waveform([-large, large], rate=rate)
        calibration = self.workspace.register_calibration('垂向', Fraction(1, 7), Fraction(1, 7))
        report = self.workspace.publish_shift('S1', revision, 1, 2, calibration, 0, 1)
        expected_value = Fraction(large + 1, 7)
        self.assertEqual(report.anomalies, (Anomaly(1, large, Fraction(1, rate), expected_value, 'high'),))
        with open_workspace(self.path) as reopened:
            self.assertEqual(reopened.read_window(revision, 0, 2), [-large, large])
            self.assertEqual(reopened.read_shift('S1'), report)
            data = json.loads(reopened.export_shift('S1'), parse_int=Decimal)
        point = data['anomalies'][0]
        self.assertEqual(point['count'], Decimal(large))
        self.assertEqual(point['seconds']['denominator'], Decimal(rate))
        self.assertEqual(point['value']['numerator'], Decimal(expected_value.numerator))
        self.assertEqual(point['value']['denominator'], Decimal(expected_value.denominator))

    def test_empty_window(self):
        revision = self.waveform([-2, 0, 4])
        calibration = self.workspace.register_calibration('垂向', 1, 0)
        report = self.workspace.publish_shift('S1', revision, 3, 3, calibration, 0, 2)
        self.assertEqual(report.anomalies, ())
        self.assertEqual(report.summary, WindowSummary(0, 0, None, None))
        self.assertEqual(self.workspace.read_shift('S1'), report)

    def test_channel_conflict(self):
        revision = self.waveform([-2, 0, 4])
        wrong = self.workspace.register_calibration('横向', 1, 0)
        right = self.workspace.register_calibration('垂向', 1, 0)
        with self.assertRaises(ValueError):
            self.workspace.publish_shift('S1', revision, 0, 3, wrong, 0, 2)
        with self.assertRaises(KeyError):
            self.workspace.read_shift('S1')
        self.assertEqual(self.shift_rows(), (0, 0))
        report = self.workspace.publish_shift('S1', revision, 0, 3, right, 0, 2)
        self.assertEqual(report.binding.calibration_revision, right)
        self.assertEqual([point.index for point in report.anomalies], [0, 2])
        self.assertEqual(self.workspace.read_shift('S1'), report)

    def test_calibration_identity(self):
        for channel, scale, offset in (('', 1, 0), ('垂向', 0.5, 0), ('垂向', 1, True)):
            with self.subTest(channel=channel, scale=scale, offset=offset), self.assertRaises(ValueError):
                self.workspace.register_calibration(channel, scale, offset)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM calibrations').fetchone()[0], 0)
        revision = self.waveform([-2, 0, 4])
        first = self.workspace.register_calibration('垂向', 1, 0)
        second = self.workspace.register_calibration('垂向', 2, 0)
        self.assertNotEqual(first, second)
        first_report = self.workspace.publish_shift('S1', revision, 2, 3, first, 0, 0)
        second_report = self.workspace.publish_shift('S2', revision, 2, 3, second, 0, 0)
        self.assertEqual(first_report.binding.calibration_revision, first)
        self.assertEqual(second_report.binding.calibration_revision, second)
        self.assertEqual([first_report.anomalies[0].value, second_report.anomalies[0].value], [4, 8])
        for unknown_wave, unknown_cal in ((revision + 1, first), (revision, second + 1)):
            with self.assertRaises(KeyError):
                self.workspace.publish_shift('S3', unknown_wave, 0, 3, unknown_cal, 0, 2)
        self.assertEqual(self.shift_rows(), (2, 2))

    def test_cross_block_shift(self):
        boundary = RAW_BLOCK_SIZE
        revision = self.waveform([0] * (boundary - 1) + [1, 2, 3])
        denominator = 2**60
        upper = Fraction(denominator + 2, denominator)
        wrong = self.workspace.register_calibration('横向', Fraction(1, denominator), 1)
        right = self.workspace.register_calibration('垂向', Fraction(1, denominator), 1)
        with self.assertRaises(ValueError):
            self.workspace.publish_shift('S1', revision, boundary - 1, boundary + 2, wrong, 0, upper)
        report = self.workspace.publish_shift('S1', revision, boundary - 1, boundary + 2, right, 0, upper)
        maximum = Fraction(denominator + 3, denominator)
        self.assertEqual(report.anomalies, (
            Anomaly(boundary + 1, 3, Fraction(boundary + 1, 3), maximum, 'high'),
        ))
        self.assertEqual(report.summary, WindowSummary(3, 1, Fraction(denominator + 1, denominator), maximum))
        self.assertEqual(self.workspace.read_shift('S1'), report)

    def test_same_binding(self):
        revision = self.waveform([-2, 0, 4])
        correction = self.waveform([-4, 0, 2], 'R2')
        calibration = self.workspace.register_calibration('垂向', 1, 0)
        other = self.workspace.register_calibration('垂向', 2, 0)
        original = (revision, 0, 3, calibration, Fraction(1, 2), 2)
        report = self.workspace.publish_shift('S1', *original)
        replayed = self.workspace.publish_shift('S1', revision, 0, 3, calibration, Fraction(2, 4), Fraction(4, 2))
        self.assertEqual(report, replayed)
        for slot, replacement in enumerate((correction, 1, 2, other, 0, 3)):
            changed = list(original)
            changed[slot] = replacement
            with self.subTest(slot=slot), self.assertRaises(ValueError):
                self.workspace.publish_shift('S1', *changed)
        self.assertEqual(self.shift_rows(), (1, 1))
        self.assertEqual(self.workspace.read_shift('S1'), report)

    def test_publish_error(self):
        revision = self.waveform([-2, 0, 4])
        calibration = self.workspace.register_calibration('垂向', Fraction(1, 2), 1)
        old = self.workspace.publish_shift('S1', revision, 0, 3, calibration, 0, 2)
        original_export = self.workspace.export_shift('S1')
        before = self.shift_rows()
        second = (revision, 2, 3, calibration, 0, 2)
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute('''
                CREATE TRIGGER reject_binding BEFORE INSERT ON shift_bindings
                WHEN NEW.shift_id = 'S2'
                     AND EXISTS (SELECT 1 FROM shift_reports WHERE id = NEW.report_id)
                BEGIN SELECT RAISE(ABORT, 'binding unavailable'); END
            ''')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'binding unavailable'):
                self.workspace.publish_shift('S2', *second)
            with open_workspace(self.path) as reopened:
                self.assertEqual(reopened.read_shift('S1'), old)
                self.assertEqual(reopened.export_shift('S1'), original_export)
                with self.assertRaises(KeyError):
                    reopened.read_shift('S2')
                self.assertEqual(self.shift_rows(), before)
            db.execute('DROP TRIGGER reject_binding')
        new = self.workspace.publish_shift('S2', *second)
        self.assertEqual(new.summary, WindowSummary(1, 1, Fraction(3), Fraction(3)))
        self.assertEqual(self.workspace.read_shift('S2'), new)
        self.assertEqual(self.shift_rows(), (2, 2))
