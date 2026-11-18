import argparse
from contextlib import closing
from fractions import Fraction
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from handoff.workspace import open_workspace
from intake.records import InstrumentRecord


SHIFT_IDS = ("S1", "S2")
POINT_COUNTS = {0: -3, 2: 3, 3: -3, 10: 3, 11: -3, 20: 3, 21: -3}
ORIGINAL = tuple(POINT_COUNTS.get(index, 0) for index in range(22))


def require_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def seed_sources(workspace):
    revision = workspace.register_raw(
        InstrumentRecord("R-review", "Q07", "垂向", 3, len(ORIGINAL), ORIGINAL)
    )
    calibration = workspace.register_calibration("垂向", 1, 0)
    workspace.publish_shift("S1", revision, 0, 3, calibration, Fraction(-1, 2), Fraction(1, 2))
    workspace.publish_shift("S2", revision, 2, 22, calibration, Fraction(-2, 4), Fraction(2, 4))
    return revision, calibration


def source_points(workspace):
    actual = [
        [[point.index, point.side] for point in workspace.read_shift(shift_id).anomalies]
        for shift_id in SHIFT_IDS
    ]
    require_equal(actual, [
        [[0, "low"], [2, "high"]],
        [[2, "high"], [3, "low"], [10, "high"], [11, "low"], [20, "high"], [21, "low"]],
    ], "issued shift anomalies")
    return actual


def check_sources():
    with open_workspace(":memory:") as workspace:
        revision, _ = seed_sources(workspace)
        print(json.dumps({"waveform_revision": revision, "shift_ids": SHIFT_IDS,
                          "anomalies_by_shift": source_points(workspace)}))


def review_demo():
    with TemporaryDirectory(prefix="review-plan-") as directory:
        database = Path(directory) / "archive.sqlite3"
        with open_workspace(database) as workspace:
            revision, calibration = seed_sources(workspace)
            anomalies = source_points(workspace)
            expected = {
                "plan_id": "S1",
                "shift_ids": list(SHIFT_IDS),
                "waveform_revision": revision,
                "calibration_revision": calibration,
                "limits": {"lower": Fraction(-1, 2), "upper": Fraction(1, 2)},
                "max_segments": 2,
                "max_samples": 4,
                "segments": [[2, 4], [10, 12]],
                "covered_indices": [2, 3, 10, 11],
                "total_samples": 4,
            }
            plan = workspace.publish_review_plan("S1", SHIFT_IDS[::-1], 2, 4)
            require_equal(plan, expected, "published plan")
            require_equal(workspace.publish_review_plan("S1", list(SHIFT_IDS), 2, 4),
                          expected, "reordered replay")
            before = workspace.export_review_plan("S1")
            old_shifts = [workspace.export_shift(shift_id) for shift_id in SHIFT_IDS]
            correction = workspace.register_raw(
                InstrumentRecord("R-review-2", "Q07", "垂向", 3, len(ORIGINAL), [0] * len(ORIGINAL))
            )

        with open_workspace(database) as workspace:
            require_equal(workspace.get_head("Q07"), correction, "waveform head")
            require_equal([workspace.export_shift(shift_id) for shift_id in SHIFT_IDS],
                          old_shifts, "old shift exports")
            saved = workspace.read_review_plan("S1")
            require_equal(saved, expected, "reopened plan")
            export = workspace.export_review_plan("S1")
            require_equal(export, before, "reopened plan export")
            payload = json.loads(export)
            require_equal(payload, {**expected, "limits": {
                "lower": {"numerator": -1, "denominator": 2},
                "upper": {"numerator": 1, "denominator": 2},
            }}, "exported plan fields")
            reread = [workspace.read_window(saved["waveform_revision"], lo, hi)
                      for lo, hi in saved["segments"]]
            require_equal(reread, [[3, -3], [3, -3]], "reread counts")
            print(json.dumps({"head_revision": correction, "anomalies_by_shift": anomalies,
                              "plan": payload, "reread_counts": reread}, ensure_ascii=False))


# Hand-computed witnesses. Each entry records the candidate indices, budgets,
# the winning plan and a plain-language explanation of the three-level verdict,
# so the ledger can be re-checked on paper without reading the solver.
VERDICT_WITNESSES = (
    {
        "case_id": "coverage-before-cost",
        "candidates": [0, 2, 3],
        "max_segments": 1,
        "max_samples": 3,
        "expected": {"segments": [[2, 4]], "covered_indices": [2, 3], "total_samples": 2},
        "oracle": "[2,4) covers two candidates with two reads; [0,3) also "
                  "reads two samples but covers only candidate 0, so coverage wins.",
    },
    {
        "case_id": "more-reads-full-coverage",
        "candidates": [0, 2, 3],
        "max_segments": 1,
        "max_samples": 4,
        "expected": {"segments": [[0, 4]], "covered_indices": [0, 2, 3], "total_samples": 4},
        "oracle": "Only [0,4) covers all three candidates; the extra read at "
                  "index 1 is paid to maximize coverage.",
    },
    {
        "case_id": "gap-read-is-not-coverage",
        "candidates": [0, 2],
        "max_segments": 1,
        "max_samples": 3,
        "expected": {"segments": [[0, 3]], "covered_indices": [0, 2], "total_samples": 3},
        "oracle": "One segment covering both candidates must be [0,3); index 1 "
                  "is read but never counted as covered.",
    },
    {
        "case_id": "budget-drops-the-lonely-candidate",
        "candidates": [0, 2],
        "max_segments": 1,
        "max_samples": 2,
        "expected": {"segments": [[0, 1]], "covered_indices": [0], "total_samples": 1},
        "oracle": "[0,3) needs three reads and is infeasible; the singleton "
                 "[0,1) is the lex-smallest one-candidate plan.",
    },
    {
        "case_id": "lexicographic-adjacent-pair",
        "candidates": [0, 1],
        "max_segments": 2,
        "max_samples": 2,
        "expected": {
            "segments": [[0, 1], [1, 2]],
            "covered_indices": [0, 1],
            "total_samples": 2,
        },
        "oracle": "Both [[0,1],[1,2]] and [[0,2]] cover two candidates with "
                  "two reads; the pair sequence is lexicographically smaller.",
    },
)


def audit_verdicts():
    from handoff.review.selection import select_segments

    ledger = []
    for witness in VERDICT_WITNESSES:
        result = select_segments(
            witness["candidates"], witness["max_segments"], witness["max_samples"]
        )
        actual = {
            "segments": result[0],
            "covered_indices": result[1],
            "total_samples": result[2],
        }
        require_equal(actual, witness["expected"], witness["case_id"])
        ledger.append({"case_id": witness["case_id"], "actual": actual,
                       "oracle": witness["oracle"]})
    empty_cases = (
        ("zero-segment-budget", [1, 2], 0, 4),
        ("zero-sample-budget", [1, 2], 2, 0),
        ("no-candidates", [], 2, 4),
    )
    for case_id, candidates, segments, samples in empty_cases:
        require_equal(
            select_segments(candidates, segments, samples),
            ([], [], 0),
            case_id,
        )
        ledger.append({"case_id": case_id, "actual": {
            "segments": [], "covered_indices": [], "total_samples": 0}})
    return ledger


def audit_persistence():
    from handoff.review.selection import select_segments

    ledger = []
    with TemporaryDirectory(prefix="review-audit-") as directory:
        database = Path(directory) / "archive.sqlite3"
        with open_workspace(database) as workspace:
            revision, calibration = seed_sources(workspace)
            plan = workspace.publish_review_plan("P1", ["S2", "S1"], 2, 4)
            require_equal(plan["segments"], [[2, 4], [10, 12]], "eligibility merge")
            require_equal(plan["covered_indices"], [2, 3, 10, 11], "dedup candidates")
            # A source outside the shared waveform/calibration/limits identity
            # is rejected and leaves no plan behind.
            other_trace = workspace.register_raw(
                InstrumentRecord("R-other", "Q08", "垂向", 3, 3, [-2, 0, 4])
            )
            workspace.publish_shift(
                "S3", other_trace, 0, 3, calibration, Fraction(-1, 2), Fraction(1, 2)
            )
            try:
                workspace.publish_review_plan("P2", ["S1", "S3"], 2, 4)
            except ValueError:
                pass
            else:
                raise AssertionError("identity conflict must raise ValueError")
            try:
                workspace.read_review_plan("P2")
            except KeyError:
                pass
            else:
                raise AssertionError("failed plan id must not be bound")
            ledger.append({"case_id": "identity-conflict-rejected",
                           "actual": {"bound_plans": ["P1"]}})
            export_before = workspace.export_review_plan("P1")

        with closing(sqlite3.connect(database, isolation_level=None)) as db:
            db.execute('''
                CREATE TRIGGER reject_review BEFORE INSERT ON review_plans
                WHEN NEW.plan_id = 'P3'
                BEGIN SELECT RAISE(ABORT, 'review plan unavailable'); END
            ''')
        with open_workspace(database) as workspace:
            try:
                workspace.publish_review_plan("P3", ["S1", "S2"], 1, 6)
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError("injected write failure must propagate")
            with closing(sqlite3.connect(database)) as db:
                orphan_reports = db.execute(
                    'SELECT COUNT(*) FROM review_reports r '
                    'WHERE NOT EXISTS (SELECT 1 FROM review_plans p WHERE p.report_id = r.id)'
                ).fetchone()[0]
            require_equal(orphan_reports, 0, "rollback leaves no orphan report")
            # The original plan is untouched and the failed id can be retried.
            require_equal(workspace.export_review_plan("P1"), export_before,
                          "prior plan survives failure")
        with closing(sqlite3.connect(database, isolation_level=None)) as db:
            db.execute('DROP TRIGGER reject_review')
        with open_workspace(database) as workspace:
            retried = workspace.publish_review_plan("P3", ["S1", "S2"], 1, 6)
            require_equal(retried["segments"], [[0, 4]], "same id retry")
            ledger.append({
                "case_id": "sqlite-failure-rollback-and-retry",
                "actual": {"orphan_reports": orphan_reports,
                           "retried_segments": retried["segments"],
                           "retried_covered": retried["covered_indices"]},
            })
            # Reopen semantics: the fixed revision and stored verdict are reused,
            # and deterministic export does not recompute.
            saved = workspace.read_review_plan("P3")
            require_equal(saved, retried, "readback matches saved verdict")
            require_equal(workspace.export_review_plan("P3"),
                          workspace.export_review_plan("P3"), "deterministic export")
        with open_workspace(database) as workspace:
            require_equal(workspace.read_review_plan("P3"), retried, "reopen readback")
            require_equal(workspace.export_review_plan("P3"),
                          workspace.export_review_plan("P3"), "reopen export stable")
            reread = [workspace.read_window(revision, lo, hi)
                      for lo, hi in retried["segments"]]
            ledger.append({
                "case_id": "fixed-revision-reread",
                "actual": {"segments": retried["segments"], "reread_counts": reread},
            })
    return ledger


def run_audit():
    ledger = audit_verdicts() + audit_persistence()
    print(json.dumps({"audit": ledger}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Review-plan business examples")
    parser.add_argument("action", choices=("sources", "demo", "audit"))
    action = parser.parse_args().action
    if action == "sources":
        check_sources()
    elif action == "audit":
        run_audit()
    else:
        review_demo()


if __name__ == "__main__":
    main()
