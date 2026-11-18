from contextlib import closing
from fractions import Fraction
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from handoff.workspace import open_workspace
from intake.records import InstrumentRecord


class ReviewPlanTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / 'archive.sqlite3'
        self.workspace = self.enterContext(open_workspace(self.path))

    def waveform(self, counts, source_id='R1', rate=3):
        return self.workspace.register_raw(
            InstrumentRecord(source_id, 'Q07', '垂向', rate, len(counts), counts)
        )

    def seed_pair(self, lower=Fraction(-1, 2), upper=Fraction(1, 2)):
        revision = self.waveform([0, -1, 1, -1, 0, 0, 1, -1])
        calibration = self.workspace.register_calibration('垂向', 1, 0)
        first = self.workspace.publish_shift(
            'S1', revision, 0, 4, calibration, lower, upper
        )
        second = self.workspace.publish_shift(
            'S2', revision, 2, 8, calibration,
            Fraction(lower.numerator * 2, lower.denominator * 2),
            Fraction(upper.numerator * 2, upper.denominator * 2),
        )
        return revision, calibration, first, second

    def review_rows(self):
        with closing(sqlite3.connect(self.path)) as db:
            return (
                db.execute('SELECT COUNT(*) FROM review_plans').fetchone()[0],
                db.execute('SELECT COUNT(*) FROM review_reports').fetchone()[0],
                db.execute('SELECT COUNT(*) FROM review_plan_sources').fetchone()[0],
            )

    def test_publish_read_export_shape(self):
        revision, calibration, _, _ = self.seed_pair()
        plan = self.workspace.publish_review_plan('P1', ['S2', 'S1'], 2, 3)
        self.assertEqual(plan, {
            'plan_id': 'P1',
            'shift_ids': ['S1', 'S2'],
            'waveform_revision': revision,
            'calibration_revision': calibration,
            'limits': {'lower': Fraction(-1, 2), 'upper': Fraction(1, 2)},
            'max_segments': 2,
            'max_samples': 3,
            'segments': [[1, 2], [2, 4]],
            'covered_indices': [1, 2, 3],
            'total_samples': 3,
        })
        # Candidates are {1,2,3,6,7}; three reads cover at most three points.
        # The lex-smallest arrangement is the singleton at 1 plus [2, 4).
        self.assertEqual(self.workspace.read_review_plan('P1'), plan)
        exported = self.workspace.export_review_plan('P1')
        self.assertEqual(exported, self.workspace.export_review_plan('P1'))
        payload = json.loads(exported)
        self.assertEqual(payload['limits'], {
            'lower': {'numerator': -1, 'denominator': 2},
            'upper': {'numerator': 1, 'denominator': 2},
        })
        self.assertEqual(payload['segments'], [[1, 2], [2, 4]])
        self.assertEqual(payload['total_samples'], 3)
        for value in (
            payload['waveform_revision'], payload['calibration_revision'],
            payload['max_segments'], payload['max_samples'],
            *payload['covered_indices'], *(x for pair in payload['segments'] for x in pair),
        ):
            self.assertIs(type(value), int)

    def test_container_types_and_order_independence(self):
        self.seed_pair()
        expected = self.workspace.publish_review_plan('P1', ['S1', 'S2'], 1, 8)
        for container in (('S2', 'S1'), {'S1', 'S2'}, frozenset({'S2', 'S1'})):
            with self.subTest(container=type(container).__name__):
                self.assertEqual(
                    self.workspace.publish_review_plan('P9', container, 1, 8),
                    {**expected, 'plan_id': 'P9'},
                )

    def test_input_validation(self):
        self.seed_pair()
        for bad_sources in ('S1', b'S1', [], ['S1', 'S1'], ['S1', 42], iter(['S1'])):
            with self.subTest(bad=bad_sources), self.assertRaises(ValueError):
                self.workspace.publish_review_plan('P1', bad_sources, 1, 4)
        for segments, samples in ((-1, 4), (1.0, 4), (True, 4), (1, -2), (1, 2.0), (1, False)):
            with self.subTest(segments=segments, samples=samples), self.assertRaises(ValueError):
                self.workspace.publish_review_plan('P1', ['S1'], segments, samples)
        with self.assertRaises(ValueError):
            self.workspace.publish_review_plan('  ', ['S1'], 1, 4)
        with self.assertRaises(KeyError):
            self.workspace.publish_review_plan('P1', ['missing'], 1, 4)
        with self.assertRaises(KeyError):
            self.workspace.read_review_plan('P1')
        with self.assertRaises(KeyError):
            self.workspace.export_review_plan('P1')
        self.assertEqual(self.review_rows(), (0, 0, 0))

    def test_zero_budget_and_no_candidates(self):
        quiet = self.waveform([0, 0, 0], source_id='R-quiet')
        calibration = self.workspace.register_calibration('垂向', 1, 0)
        self.workspace.publish_shift('S0', quiet, 0, 3, calibration, -5, 5)
        empty = self.workspace.publish_review_plan('P0', ['S0'], 2, 4)
        self.assertEqual(empty['segments'], [])
        self.assertEqual(empty['covered_indices'], [])
        self.assertEqual(empty['total_samples'], 0)
        self.seed_pair()
        zero_segments = self.workspace.publish_review_plan('P1', ['S1', 'S2'], 0, 4)
        zero_samples = self.workspace.publish_review_plan('P2', ['S1', 'S2'], 2, 0)
        for plan in (zero_segments, zero_samples):
            self.assertEqual(plan['segments'], [])
            self.assertEqual(plan['covered_indices'], [])
            self.assertEqual(plan['total_samples'], 0)
        self.assertEqual(self.review_rows(), (3, 3, 5))

    def test_identity_conflict_between_sources(self):
        revision = self.waveform([-1, 0, 1, -1])
        first_calibration = self.workspace.register_calibration('垂向', 1, 0)
        second_calibration = self.workspace.register_calibration('垂向', 2, 0)
        self.workspace.publish_shift('S1', revision, 0, 4, first_calibration, 0, 0)
        self.workspace.publish_shift('S2', revision, 0, 4, second_calibration, 0, 0)
        with self.assertRaises(ValueError):
            self.workspace.publish_review_plan('P1', ['S1', 'S2'], 2, 4)
        # Different waveform revision is likewise a calibration-identity conflict.
        other = self.waveform([-1, 0, 1, -1], 'R2')
        self.workspace.publish_shift('S3', other, 0, 4, first_calibration, 0, 0)
        with self.assertRaises(ValueError):
            self.workspace.publish_review_plan('P2', ['S1', 'S3'], 2, 4)
        # Different limits on the same revisions also break eligibility.
        self.workspace.publish_shift('S4', revision, 0, 4, first_calibration, -1, 1)
        with self.assertRaises(ValueError):
            self.workspace.publish_review_plan('P3', ['S1', 'S4'], 2, 4)
        self.assertEqual(self.review_rows(), (0, 0, 0))

    def test_global_index_dedup_high_and_low(self):
        revision = self.waveform([1, -1, 1])
        calibration = self.workspace.register_calibration('垂向', 1, 0)
        self.workspace.publish_shift('S1', revision, 0, 3, calibration, 0, 0)
        self.workspace.publish_shift('S2', revision, 1, 3, calibration, 0, 0)
        # S1 anomalies: 0 high, 1 low, 2 high. S2 anomalies: 1 low, 2 high.
        # Global dedup leaves {0, 1, 2}; two reads cover two candidates and
        # the lex-smallest pair of singletons starts at the lowest index.
        plan = self.workspace.publish_review_plan('P1', ['S1', 'S2'], 2, 2)
        self.assertEqual(plan['covered_indices'], [0, 1])
        self.assertEqual(plan['segments'], [[0, 1], [1, 2]])
        self.assertEqual(plan['total_samples'], 2)

    def test_replay_and_binding_conflict(self):
        self.seed_pair()
        first = self.workspace.publish_review_plan('P1', ['S1', 'S2'], 2, 4)
        replayed = self.workspace.publish_review_plan(
            'P1', ('S2', 'S1'), 2, 4
        )
        self.assertEqual(replayed, first)
        self.assertEqual(self.review_rows(), (1, 1, 2))
        for kwargs in (
            {'max_segments': 1}, {'max_samples': 3},
        ):
            with self.subTest(**kwargs), self.assertRaises(ValueError):
                self.workspace.publish_review_plan(
                    'P1', ['S1', 'S2'],
                    kwargs.get('max_segments', 2),
                    kwargs.get('max_samples', 4),
                )
        with self.assertRaises(ValueError):
            self.workspace.publish_review_plan('P1', ['S1'], 2, 4)
        self.assertEqual(self.workspace.read_review_plan('P1'), first)
        self.assertEqual(self.review_rows(), (1, 1, 2))

    def test_input_and_return_mutation_isolation(self):
        self.seed_pair()
        sources = ['S1', 'S2']
        plan = self.workspace.publish_review_plan('P1', sources, 2, 4)
        sources.append('S-unknown')
        plan['segments'].append([99, 100])
        plan['shift_ids'].append('S-unknown')
        saved = self.workspace.read_review_plan('P1')
        self.assertEqual(saved['segments'], [[1, 3], [6, 8]])
        self.assertEqual(saved['covered_indices'], [1, 2, 6, 7])
        self.assertEqual(saved['shift_ids'], ['S1', 'S2'])

    def test_atomic_failure_and_same_id_retry(self):
        self.seed_pair()
        before = self.review_rows()
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute('''
                CREATE TRIGGER reject_review_plan BEFORE INSERT ON review_plans
                WHEN NEW.plan_id = 'P2'
                BEGIN SELECT RAISE(ABORT, 'review plan unavailable'); END
            ''')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'review plan unavailable'):
                self.workspace.publish_review_plan('P2', ['S1', 'S2'], 2, 4)
            self.assertEqual(self.review_rows(), before)
            db.execute('DROP TRIGGER reject_review_plan')
        retried = self.workspace.publish_review_plan('P2', ['S1', 'S2'], 2, 4)
        self.assertEqual(retried['covered_indices'], [1, 2, 6, 7])
        self.assertEqual(self.review_rows(), (before[0] + 1, before[1] + 1, before[2] + 2))

    def test_reopen_keeps_fixed_revision_and_export(self):
        revision, _, _, _ = self.seed_pair()
        plan = self.workspace.publish_review_plan('P1', ['S2', 'S1'], 2, 4)
        exported_before = self.workspace.export_review_plan('P1')
        old_shift_exports = [
            self.workspace.export_shift('S1'), self.workspace.export_shift('S2')
        ]
        correction = self.workspace.register_raw(
            InstrumentRecord('R2', 'Q07', '垂向', 3, 8, [0] * 8)
        )
        with open_workspace(self.path) as reopened:
            self.assertEqual(reopened.get_head('Q07'), correction)
            self.assertEqual(reopened.export_review_plan('P1'), exported_before)
            saved = reopened.read_review_plan('P1')
            self.assertEqual(saved, plan)
            self.assertEqual(saved['waveform_revision'], revision)
            reread = [
                reopened.read_window(saved['waveform_revision'], lo, hi)
                for lo, hi in saved['segments']
            ]
            self.assertEqual(reread, [[-1, 1], [1, -1]])
            self.assertEqual(
                [reopened.export_shift('S1'), reopened.export_shift('S2')],
                old_shift_exports,
            )

    def test_segment_budget_is_respected(self):
        self.seed_pair()
        # One segment may span the gap but must still start and end on candidates.
        plan = self.workspace.publish_review_plan('P1', ['S1', 'S2'], 1, 8)
        self.assertEqual(len(plan['segments']), 1)
        self.assertLessEqual(plan['total_samples'], 8)
        lo, hi = plan['segments'][0]
        self.assertIn(lo, plan['covered_indices'])
        self.assertIn(hi - 1, plan['covered_indices'])
        # The materialized read total always equals the sum of segment lengths.
        self.assertEqual(
            plan['total_samples'], sum(hi - lo for lo, hi in plan['segments'])
        )
        # Adjacent segments are allowed and never overlap.
        adjacent = self.workspace.publish_review_plan('P2', ['S1', 'S2'], 5, 5)
        ends = [pair[1] for pair in adjacent['segments']]
        starts = [pair[0] for pair in adjacent['segments']]
        self.assertEqual(starts, sorted(starts))
        for earlier, later in zip(ends, starts[1:]):
            self.assertLessEqual(earlier, later)
        self.assertLessEqual(len(adjacent['segments']), 5)
        self.assertLessEqual(adjacent['total_samples'], 5)
        self.assertEqual(
            adjacent['total_samples'],
            sum(hi - lo for lo, hi in adjacent['segments']),
        )

    def test_segment_spans_disjoint_source_gap(self):
        # Two source windows with a physical gap: [0,1) and [6,7). Candidates
        # are indices 0 and 6; one segment may span the gap, reading the five
        # non-candidate samples in between without counting them as covered.
        revision = self.waveform([-1, 0, 0, 0, 0, 0, -1])
        calibration = self.workspace.register_calibration('垂向', 1, 0)
        self.workspace.publish_shift('S1', revision, 0, 1, calibration, 0, 0)
        self.workspace.publish_shift('S2', revision, 6, 7, calibration, 0, 0)
        spanning = self.workspace.publish_review_plan('P1', ['S1', 'S2'], 1, 7)
        self.assertEqual(spanning['segments'], [[0, 7]])
        self.assertEqual(spanning['covered_indices'], [0, 6])
        self.assertEqual(spanning['total_samples'], 7)
        # Tight budgets instead force two singletons and drop nothing only when
        # the segment budget allows both.
        split = self.workspace.publish_review_plan('P2', ['S1', 'S2'], 2, 2)
        self.assertEqual(split['segments'], [[0, 1], [6, 7]])
        self.assertEqual(split['covered_indices'], [0, 6])
        self.assertEqual(split['total_samples'], 2)
        # A single read can only cover the lexicographically first candidate.
        single = self.workspace.publish_review_plan('P3', ['S1', 'S2'], 1, 1)
        self.assertEqual(single['segments'], [[0, 1]])
        self.assertEqual(single['covered_indices'], [0])
