from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from quality.calibrations import RationalInput, exact_fraction


LimitSide = Literal['low', 'high']


@dataclass(frozen=True, slots=True)
class LimitBand:
    lower: Fraction
    upper: Fraction


def validate_limits(lower: RationalInput, upper: RationalInput) -> LimitBand:
    low = exact_fraction(lower, 'lower limit')
    high = exact_fraction(upper, 'upper limit')
    if low > high:
        raise ValueError('lower limit must not exceed upper limit')
    return LimitBand(low, high)


def classify_value(value: Fraction, limits: LimitBand) -> LimitSide | None:
    if value < limits.lower:
        return 'low'
    if value > limits.upper:
        return 'high'
    return None
