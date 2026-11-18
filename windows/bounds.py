from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WindowBounds:
    lo: int
    hi: int

    @property
    def length(self) -> int:
        return self.hi - self.lo


def validate_window_bounds(length: int, lo: int, hi: int) -> WindowBounds:
    if type(lo) is not int or type(hi) is not int or not 0 <= lo <= hi <= length:
        raise ValueError('window must satisfy 0 <= lo <= hi <= revision length')
    return WindowBounds(lo, hi)


def intersect_bounds(bounds: WindowBounds, start: int, stop: int) -> WindowBounds | None:
    lo = max(bounds.lo, start)
    hi = min(bounds.hi, stop)
    return WindowBounds(lo, hi) if lo < hi else None
