from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..db import _db_fetch_all, _db_fetch_one
from ..spec_io import _read_yaml, _spec_root


def _load_advice_catalogue() -> dict[str, Any]:
    path = _spec_root() / "governance" / "GOOD_PRACTICE_CARDS.yaml"
    data = _read_yaml(path)
    return data if isinstance(data, dict) else {}


def list_advice_cards(
    *,
    plan_project_id: str | None = None,
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    limit: int = 200,
) -> JSONResponse:
    resolved_authority = authority_id
    resolved_plan_cycle = plan_cycle_id

    if plan_project_id:
        plan_project = _db_fetch_one(
            "SELECT authority_id, metadata_jsonb FROM plan_projects WHERE id = %s::uuid",
            (plan_project_id,),
        )
        if not plan_project:
            raise HTTPException(status_code=404, detail="Plan project not found")
        resolved_authority = plan_project.get("authority_id")
        metadata = plan_project.get("metadata_jsonb") if isinstance(plan_project.get("metadata_jsonb"), dict) else {}
        if not resolved_plan_cycle and isinstance(metadata.get("plan_cycle_id"), str):
            resolved_plan_cycle = metadata.get("plan_cycle_id")

    if not resolved_authority:
        raise HTTPException(status_code=400, detail="authority_id or plan_project_id is required")

    rows = _db_fetch_all(
        """
        SELECT
          aci.id AS instance_id,
          aci.card_id,
          aci.card_version,
          aci.scope_type,
          aci.scope_id,
          aci.status,
          aci.trigger_cues_jsonb,
          aci.evidence_refs_jsonb,
          aci.tool_run_id,
          aci.created_at,
          aci.notes,
          d.metadata->>'title' AS document_title,
          d.document_status,
          d.weight_hint
        FROM advice_card_instances aci
        JOIN documents d ON d.id = aci.scope_id
        WHERE aci.status = 'active'
          AND aci.scope_type = 'document'
          AND d.is_active = true
          AND d.authority_id = %s
          AND (%s::uuid IS NULL OR d.plan_cycle_id = %s::uuid)
        ORDER BY aci.created_at DESC
        LIMIT %s
        """,
        (resolved_authority, resolved_plan_cycle, resolved_plan_cycle, limit),
    )

    catalogue = _load_advice_catalogue()
    cards = catalogue.get("cards") if isinstance(catalogue.get("cards"), list) else []
    card_by_id = {c.get("card_id"): c for c in cards if isinstance(c, dict) and isinstance(c.get("card_id"), str)}

    items: list[dict[str, Any]] = []
    for row in rows:
        card_id = row.get("card_id")
        card = card_by_id.get(card_id, {})
        items.append(
            {
                "instance_id": str(row.get("instance_id")),
                "card_id": card_id,
                "card_version": row.get("card_version"),
                "card_title": card.get("title"),
                "card_type": card.get("type"),
                "basis": card.get("basis"),
                "priority": card.get("priority"),
                "status": card.get("status") or "Advisory only — planner judgement required",
                "prompt": card.get("prompt"),
                "applies_at": card.get("applies_at"),
                "dimensions": card.get("dimensions"),
                "trigger_cues": row.get("trigger_cues_jsonb") or [],
                "evidence_refs": row.get("evidence_refs_jsonb") or [],
                "tool_run_id": str(row.get("tool_run_id")) if row.get("tool_run_id") else None,
                "created_at": row.get("created_at"),
                "notes": row.get("notes"),
                "document_title": row.get("document_title"),
                "document_status": row.get("document_status"),
                "weight_hint": row.get("weight_hint"),
            }
        )

    return JSONResponse(
        content=jsonable_encoder(
            {
                "advice_cards": items,
                "meta": {
                    "authority_id": resolved_authority,
                    "plan_cycle_id": resolved_plan_cycle,
                    "plan_project_id": plan_project_id,
                    "count": len(items),
                },
            }
        )
    )
