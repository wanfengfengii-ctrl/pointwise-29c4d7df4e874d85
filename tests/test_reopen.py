from fractions import Fraction
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from handoff.workspace import open_workspace
from intake.records import InstrumentRecord
from quality.assessment import Anomaly
from quality.summary import WindowSummary
from windows.bounds import WindowBounds


class ReopenTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / 'archive.sqlite3'
        self.original = InstrumentRecord('R1', 'Q07', '垂向', 3, 3, [-2, 0, 4])
        self.correction = InstrumentRecord('R2', 'Q07', '垂向', 3, 3, [-4, 0, 2])

    def test_historical_export(self):
        with open_workspace(self.path) as day:
            old_revision = day.register_raw(self.original)
            trial = day.read_window(old_revision, 0, 2)
            self.assertEqual(trial, [-2, 0])
            calibration = day.register_calibration('垂向', Fraction(1, 2), 1)
            day.publish_shift('S1', old_revision, 0, 3, calibration, 0, 2)
            old_export = day.export_shift('S1')
            new_revision = day.register_raw(self.correction)
            day.register_calibration('垂向', 9, 3)

        with open_workspace(self.path) as night:
            self.assertEqual(night.get_head('Q07'), new_revision)
            self.assertEqual(night.read_window(old_revision, 0, 3), [-2, 0, 4])
            self.assertEqual(night.read_window(new_revision, 0, 3), [-4, 0, 2])
            self.assertEqual(night.export_shift('S1'), old_export)
            night.publish_shift('S2', new_revision, 0, 3, calibration, 0, 2)

        with open_workspace(self.path) as archive:
            old = archive.read_shift('S1')
            new = archive.read_shift('S2')
            self.assertEqual(old.binding.waveform_revision, old_revision)
            self.assertEqual(new.binding.waveform_revision, new_revision)
            for report in (old, new):
                self.assertEqual(report.binding.calibration_revision, calibration)
                self.assertEqual(report.binding.bounds, WindowBounds(0, 3))
                self.assertEqual((report.binding.limits.lower, report.binding.limits.upper), (0, 2))
            self.assertEqual(old.anomalies, (Anomaly(2, 4, Fraction(2, 3), Fraction(3), 'high'),))
            self.assertEqual(new.anomalies, (Anomaly(0, -4, Fraction(0), Fraction(-1), 'low'),))
            self.assertEqual(old.summary, WindowSummary(3, 1, Fraction(0), Fraction(3)))
            self.assertEqual(new.summary, WindowSummary(3, 1, Fraction(-1), Fraction(2)))
            stable = archive.export_shift('S1') == old_export
            self.assertTrue(stable)
            new_export = json.loads(archive.export_shift('S2'))
            self.assertEqual(new_export['anomalies'][0]['index'], 0)
            self.assertEqual(new_export['anomalies'][0]['side'], 'low')

        evidence = {
            'case_id': 'v8',
            'input': {
                'R1': self.original.counts, 'R2': self.correction.counts, 'sample_rate': 3,
                'scale': [1, 2], 'offset': 1, 'limits': [0, 2], 'window': [0, 3],
            },
            'expected': {'trial': [-2, 0], 'old_anomaly_indices': [2]},
            'actual': {'trial': trial, 'old_anomaly_indices': [point.index for point in old.anomalies]},
            'downstream_expected': {'old_export_stable': True, 'new_anomaly_index': 0, 'new_side': 'low'},
            'downstream_actual': {
                'old_export_stable': stable,
                'new_anomaly_index': new_export['anomalies'][0]['index'],
                'new_side': new_export['anomalies'][0]['side'],
            },
            'code_paths': [
                'intake/register.py', 'windows/raw_reader.py', 'quality/assessment.py',
                'handoff/publish.py', 'handoff/read.py', 'handoff/export.py',
            ],
            'oracle': 'Apply count/2 + 1 by hand. R1 gives [0, 1, 3] and R2 gives [-1, 1, 2].',
        }
        print('POINTWISE_SCENARIO ' + json.dumps(evidence, separators=(',', ':')))

    def test_reinitialize(self):
        with open_workspace(self.path) as workspace:
            old = workspace.register_raw(self.original)
            new = workspace.register_raw(self.correction)
            calibration = workspace.register_calibration('垂向', Fraction(1, 2), 1)
            first = workspace.publish_shift('S1', old, 0, 3, calibration, 0, 2)
            second = workspace.publish_shift('S2', new, 0, 3, calibration, 0, 2)

        for attempt in range(2):
            with self.subTest(attempt=attempt), open_workspace(self.path) as workspace:
                self.assertEqual(workspace.get_head('Q07'), new)
                self.assertEqual(workspace.read_shift('S1'), first)
                self.assertEqual(workspace.read_shift('S2'), second)
                self.assertEqual(workspace.register_raw(self.original), old)
                self.assertEqual(workspace.register_raw(self.correction), new)
                self.assertEqual(workspace.get_head('Q07'), new)

    def test_unknown_shift(self):
        with open_workspace(self.path) as workspace:
            with self.assertRaises(KeyError):
                workspace.read_shift('unsent')
            with self.assertRaises(KeyError):
                workspace.export_shift('unsent')

    def test_export_shape(self):
        record = InstrumentRecord('R3', 'Q07', '垂向', 3, 3, [0, 0, 1])
        with open_workspace(self.path) as workspace:
            revision = workspace.register_raw(record)
            calibration = workspace.register_calibration('垂向', Fraction(1, 3), 0)
            workspace.publish_shift('S3', revision, 1, 3, calibration, -1, 0)
            workspace.publish_shift('empty', revision, 3, 3, calibration, -1, 0)
        with open_workspace(self.path) as workspace:
            self.assertEqual(workspace.read_shift('S3').anomalies[0].value, Fraction(1, 3))
            first = workspace.export_shift('S3')
            self.assertEqual(first, workspace.export_shift('S3'))
            data = json.loads(first)
            empty = json.loads(workspace.export_shift('empty'))
        self.assertEqual(data['shift_id'], 'S3')
        self.assertEqual(data['waveform_revision'], revision)
        self.assertEqual(data['calibration_revision'], calibration)
        self.assertEqual(data['window'], {'lo': 1, 'hi': 3})
        self.assertEqual(data['limits'], {
            'lower': {'numerator': -1, 'denominator': 1}, 'upper': {'numerator': 0, 'denominator': 1}
        })
        self.assertEqual(data['anomalies'], [{
            'index': 2, 'count': 1, 'side': 'high',
            'seconds': {'numerator': 2, 'denominator': 3},
            'value': {'numerator': 1, 'denominator': 3},
        }])
        point = data['anomalies'][0]
        for integer in (point['index'], point['count'], *point['seconds'].values(), *point['value'].values()):
            self.assertIs(type(integer), int)
        self.assertEqual(data['summary'], {
            'sample_count': 2, 'anomaly_count': 1,
            'minimum': {'numerator': 0, 'denominator': 1},
            'maximum': {'numerator': 1, 'denominator': 3},
        })
        self.assertEqual(empty['anomalies'], [])
        self.assertEqual(empty['summary'], {
            'sample_count': 0, 'anomaly_count': 0, 'minimum': None, 'maximum': None,
        })
