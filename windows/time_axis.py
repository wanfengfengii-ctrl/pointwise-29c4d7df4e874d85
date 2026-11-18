from fractions import Fraction


def sample_time(index: int, sample_rate: int) -> Fraction:
    return Fraction(index, sample_rate)
