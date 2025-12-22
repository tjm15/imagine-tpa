from __future__ import annotations

from uuid import uuid4

from .db import _db_execute, _db_fetch_one


def _parse_evidence_ref(evidence_ref: str) -> tuple[str, str, str] | None:
    parts = evidence_ref.split("::", 2)
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2]


def _ensure_evidence_ref_row(
    evidence_ref: str,
    run_id: str | None = None,
    document_id: str | None = None,
    locator_type: str | None = None,
    locator_value: str | None = None,
    excerpt: str | None = None,
) -> str | None:
    parsed = _parse_evidence_ref(evidence_ref)
    if not parsed:
        return None
    source_type, source_id, fragment_id = parsed
    row = _db_fetch_one(
        "SELECT id FROM evidence_refs WHERE source_type = %s AND source_id = %s AND fragment_id = %s",
        (source_type, source_id, fragment_id),
    )
    if row and row.get("id"):
        evidence_ref_id = str(row["id"])
        if document_id or locator_type or locator_value or excerpt:
            _db_execute(
                """
                UPDATE evidence_refs
                SET document_id = COALESCE(%s::uuid, document_id),
                    locator_type = COALESCE(%s, locator_type),
                    locator_value = COALESCE(%s, locator_value),
                    excerpt = COALESCE(%s, excerpt)
                WHERE id = %s::uuid
                """,
                (
                    document_id,
                    locator_type,
                    locator_value,
                    excerpt,
                    evidence_ref_id,
                ),
            )
        return evidence_ref_id
    evidence_ref_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO evidence_refs (
          id, source_type, source_id, fragment_id, run_id,
          document_id, locator_type, locator_value, excerpt
        )
        VALUES (%s, %s, %s, %s, %s::uuid, %s::uuid, %s, %s, %s)
        """,
        (
            evidence_ref_id,
            source_type,
            source_id,
            fragment_id,
            run_id,
            document_id,
            locator_type,
            locator_value,
            excerpt,
        ),
    )
    return evidence_ref_id
