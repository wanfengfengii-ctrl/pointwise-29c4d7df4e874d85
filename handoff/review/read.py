import sqlite3

from handoff.review.bindings import get_review_binding
from handoff.review.publish import verdict_to_dict
from handoff.review.reports import load_review_report
from intake.validation import require_identifier


def read_review_plan(db: sqlite3.Connection, plan_id: str) -> dict:
    try:
        require_identifier(plan_id, 'plan_id')
    except ValueError:
        raise KeyError(plan_id) from None
    stored = get_review_binding(db, plan_id)
    if stored is None:
        raise KeyError(plan_id)
    return verdict_to_dict(stored.binding, load_review_report(db, stored.report_id))
