from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from quality.convert import CalibratedSample


@dataclass(frozen=True, slots=True)
class WindowSummary:
    sample_count: int
    anomaly_count: int
    minimum: Fraction | None
    maximum: Fraction | None


def summarize_window(samples: Sequence[CalibratedSample], anomaly_count: int) -> WindowSummary:
    return WindowSummary(
        len(samples),
        anomaly_count,
        min((sample.value for sample in samples), default=None),
        max((sample.value for sample in samples), default=None),
    )
