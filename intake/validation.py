from collections.abc import Mapping, Set

from intake.records import InstrumentRecord, ValidatedRecord


def require_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonblank string')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise ValueError(f'{label} must be valid UTF-8') from error
    return value


def validate_record(record: InstrumentRecord) -> ValidatedRecord:
    if not isinstance(record, InstrumentRecord):
        raise ValueError('expected an InstrumentRecord')
    source_id = require_identifier(record.source_id, 'source_id')
    trace_id = require_identifier(record.trace_id, 'trace_id')
    channel = require_identifier(record.channel, 'channel')
    if type(record.sample_rate) is not int or record.sample_rate <= 0:
        raise ValueError('sample_rate must be a positive integer')
    if type(record.declared_length) is not int or record.declared_length < 0:
        raise ValueError('declared_length must be a nonnegative integer')
    if isinstance(record.counts, (str, bytes, bytearray, Mapping, Set)):
        raise ValueError('counts must be an ordered iterable of integers')
    try:
        counts = tuple(record.counts)
    except TypeError as error:
        raise ValueError('counts must be an ordered iterable of integers') from error
    if len(counts) != record.declared_length:
        raise ValueError('declared_length does not match the actual sample count')
    if any(type(count) is not int for count in counts):
        raise ValueError('every count must be an integer')
    return ValidatedRecord(
        source_id, trace_id, channel, record.sample_rate, record.declared_length, counts
    )
