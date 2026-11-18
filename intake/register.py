import sqlite3

from archive.heads import set_head
from archive.raw_blocks import insert_raw_blocks
from archive.revisions import insert_revision
from archive.transactions import write_transaction
from intake.canonical import canonical_record_content
from intake.receipts import SourceReceipt, get_receipt, insert_receipt
from intake.records import InstrumentRecord
from intake.validation import validate_record


def register_raw(db: sqlite3.Connection, record: InstrumentRecord) -> int:
    validated = validate_record(record)
    content = canonical_record_content(validated)
    with write_transaction(db):
        existing = get_receipt(db, validated.source_id)
        if existing is not None:
            if existing.content != content:
                raise ValueError(f'conflicting content for source {validated.source_id!r}')
            return existing.revision

        revision = insert_revision(
            db,
            validated.trace_id,
            validated.channel,
            validated.sample_rate,
            validated.declared_length,
        )
        insert_raw_blocks(db, revision, validated.counts)
        set_head(db, validated.trace_id, revision)
        insert_receipt(db, SourceReceipt(validated.source_id, content, revision))
        return revision
