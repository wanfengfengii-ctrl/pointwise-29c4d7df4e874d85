from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from fractions import Fraction

from quality.calibrations import CalibrationRevision
from windows.views import RawSample


@dataclass(frozen=True, slots=True)
class CalibratedSample:
    index: int
    count: int
    seconds: Fraction
    value: Fraction


def convert_samples(
    samples: Iterable[RawSample], calibration: CalibrationRevision
) -> Iterator[CalibratedSample]:
    for sample in samples:
        yield CalibratedSample(
            sample.index,
            sample.count,
            sample.seconds,
            sample.count * calibration.scale + calibration.offset,
        )
