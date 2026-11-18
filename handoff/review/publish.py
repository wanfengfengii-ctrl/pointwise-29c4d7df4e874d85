from collections.abc import Set
import sqlite3

from archive.transactions import write_transaction
from handoff.bindings import get_shift_binding
from handoff.reports import load_report
from handoff.review.bindings import (
    ReviewBinding,
    get_review_binding,
    insert_review_binding,
)
from handoff.review.reports import ReviewVerdict, insert_review_report, load_review_report
from handoff.review.selection import select_segments
from intake.validation import require_identifier
from quality.limits import LimitBand


def require_budget(value: int, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f'{label} must be a nonnegative integer')
    return value


def normalize_sources(shift_ids) -> list[str]:
    if isinstance(shift_ids, (str, bytes, bytearray)) or not isinstance(
        shift_ids, (list, tuple, Set)
    ):
        raise ValueError('shift_ids must be a list, tuple, set or frozenset')
    if len(shift_ids) == 0:
        raise ValueError('shift_ids must contain at least one source')
    normalized = []
    seen = set()
    for shift_id in shift_ids:
        if not isinstance(shift_id, str):
            raise ValueError('every shift id must be a string')
        if shift_id in seen:
            raise ValueError(f'duplicate shift id {shift_id!r}')
        seen.add(shift_id)
        normalized.append(shift_id)
    return normalized


def _load_source_bindings(
    db: sqlite3.Connection, shift_ids: list[str]
) -> list:
    stored = []
    for shift_id in shift_ids:
        require_identifier(shift_id, 'shift_id')
        binding = get_shift_binding(db, shift_id)
        if binding is None:
            raise KeyError(shift_id)
        stored.append(binding)
    return stored


def _merge_identity(stored_sources: list) -> tuple[int, int, LimitBand]:
    first = stored_sources[0].binding
    waveform_revision = first.waveform_revision
    calibration_revision = first.calibration_revision
    limits = first.limits
    for stored in stored_sources[1:]:
        binding = stored.binding
        if (
            binding.waveform_revision != waveform_revision
            or binding.calibration_revision != calibration_revision
            or binding.limits != limits
        ):
            raise ValueError('review sources must share waveform, calibration and limits')
    return waveform_revision, calibration_revision, limits


def collect_candidates(db: sqlite3.Connection, stored_sources: list) -> list[int]:
    candidates = set()
    for stored in stored_sources:
        assessment = load_report(db, stored.report_id)
        candidates.update(point.index for point in assessment.anomalies)
    return sorted(candidates)


def verdict_to_dict(
    binding: ReviewBinding, verdict: ReviewVerdict
) -> dict:
    return {
        'plan_id': binding.plan_id,
        'shift_ids': list(binding.shift_ids),
        'waveform_revision': binding.waveform_revision,
        'calibration_revision': binding.calibration_revision,
        'limits': {'lower': binding.limits.lower, 'upper': binding.limits.upper},
        'max_segments': binding.max_segments,
        'max_samples': binding.max_samples,
        'segments': [[lo, hi] for lo, hi in verdict.segments],
        'covered_indices': list(verdict.covered_indices),
        'total_samples': verdict.total_samples,
    }


def publish_review_plan(
    db: sqlite3.Connection,
    plan_id: str,
    shift_ids,
    max_segments: int,
    max_samples: int,
) -> dict:
    plan_id = require_identifier(plan_id, 'plan_id')
    requested_sources = normalize_sources(shift_ids)
    max_segments = require_budget(max_segments, 'max_segments')
    max_samples = require_budget(max_samples, 'max_samples')
    ordered_sources = sorted(requested_sources)

    with write_transaction(db):
        existing = get_review_binding(db, plan_id)
        if existing is not None:
            proposed = ReviewBinding(
                plan_id,
                tuple(ordered_sources),
                existing.binding.waveform_revision,
                existing.binding.calibration_revision,
                existing.binding.limits,
                max_segments,
                max_samples,
            )
            if proposed != existing.binding:
                raise ValueError(f'conflicting binding for review plan {plan_id!r}')
            return verdict_to_dict(
                existing.binding, load_review_report(db, existing.report_id)
            )

        stored_sources = _load_source_bindings(db, ordered_sources)
        waveform_revision, calibration_revision, limits = _merge_identity(stored_sources)
        candidates = collect_candidates(db, stored_sources)
        segments, covered_indices, total_samples = select_segments(
            candidates, max_segments, max_samples
        )
        binding = ReviewBinding(
            plan_id,
            tuple(ordered_sources),
            waveform_revision,
            calibration_revision,
            limits,
            max_segments,
            max_samples,
        )
        verdict = ReviewVerdict(
            tuple((lo, hi) for lo, hi in segments),
            tuple(covered_indices),
            total_samples,
        )
        report_id = insert_review_report(db, verdict)
        insert_review_binding(db, binding, report_id)
        return verdict_to_dict(binding, verdict)
