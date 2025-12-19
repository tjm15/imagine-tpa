from __future__ import annotations


_PLAN_CYCLE_EMERGING_STATUSES = ("draft", "emerging", "submitted", "examination")


def _normalize_plan_cycle_status(value: str) -> str:
    return (value or "").strip().lower() or "unknown"


def _plan_cycle_conflict_statuses(status: str) -> tuple[str, ...] | None:
    """
    Returns the set of statuses that are mutually exclusive (for a single authority) with the given status,
    or None if we don't enforce a group constraint for this status.
    """
    status = _normalize_plan_cycle_status(status)
    if status == "adopted":
        return ("adopted",)
    if status in _PLAN_CYCLE_EMERGING_STATUSES:
        return _PLAN_CYCLE_EMERGING_STATUSES
    return None

