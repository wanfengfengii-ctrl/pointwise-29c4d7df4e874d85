from dataclasses import dataclass
from fractions import Fraction

from quality.calibrations import CalibrationRevision
from quality.convert import convert_samples
from quality.limits import LimitBand, LimitSide, classify_value
from quality.summary import WindowSummary, summarize_window
from windows.views import RawWindow


@dataclass(frozen=True, slots=True)
class Anomaly:
    index: int
    count: int
    seconds: Fraction
    value: Fraction
    side: LimitSide


@dataclass(frozen=True, slots=True)
class WindowAssessment:
    anomalies: tuple[Anomaly, ...]
    summary: WindowSummary


def assess_window(
    window: RawWindow, calibration: CalibrationRevision, limits: LimitBand
) -> WindowAssessment:
    if window.channel != calibration.channel:
        raise ValueError('calibration channel does not match waveform channel')
    samples = tuple(convert_samples(window.samples, calibration))
    anomalies = []
    for sample in samples:
        side = classify_value(sample.value, limits)
        if side is not None:
            anomalies.append(Anomaly(sample.index, sample.count, sample.seconds, sample.value, side))
    return WindowAssessment(tuple(anomalies), summarize_window(samples, len(anomalies)))
