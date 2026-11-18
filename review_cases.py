import argparse
from fractions import Fraction
import json
from pathlib import Path
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


def main():
    parser = argparse.ArgumentParser(description="Review-plan business examples")
    parser.add_argument("action", choices=("sources", "demo"))
    if parser.parse_args().action == "sources":
        check_sources()
    else:
        review_demo()


if __name__ == "__main__":
    main()
