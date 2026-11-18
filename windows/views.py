from dataclasses import dataclass
from fractions import Fraction

from windows.bounds import WindowBounds


@dataclass(frozen=True, slots=True)
class RawSample:
    index: int
    count: int
    seconds: Fraction


@dataclass(frozen=True, slots=True)
class RawWindow:
    revision: int
    channel: str
    bounds: WindowBounds
    samples: tuple[RawSample, ...]

    def counts(self) -> list[int]:
        return [sample.count for sample in self.samples]
