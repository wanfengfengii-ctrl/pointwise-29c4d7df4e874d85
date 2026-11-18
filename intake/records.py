from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstrumentRecord:
    source_id: str
    trace_id: str
    channel: str
    sample_rate: int
    declared_length: int
    counts: Iterable[int]


@dataclass(frozen=True, slots=True)
class ValidatedRecord:
    source_id: str
    trace_id: str
    channel: str
    sample_rate: int
    declared_length: int
    counts: tuple[int, ...]
