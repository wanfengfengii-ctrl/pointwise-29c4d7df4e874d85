import json

from intake.records import ValidatedRecord


def canonical_record_content(record: ValidatedRecord) -> str:
    fields = [
        record.trace_id,
        record.channel,
        format(record.sample_rate, 'x'),
        record.declared_length,
        [format(count, 'x') for count in record.counts],
    ]
    return json.dumps(fields, ensure_ascii=True, separators=(',', ':'))
