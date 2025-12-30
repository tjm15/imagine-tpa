from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from tpa_api.db import _db_execute, _db_fetch_all
import os

from tpa_api.prompting import _llm_structured_sync
from tpa_api.time_utils import _utc_now


def _ensure_kg_node(*, node_id: str, node_type: str, canonical_fk: str | None, props: dict[str, Any]) -> None:
    _db_execute(
        """
        INSERT INTO kg_node (node_id, node_type, props_jsonb, canonical_fk)
        VALUES (%s, %s, %s::jsonb, %s)
        ON CONFLICT (node_id) DO NOTHING
        """,
        (node_id, node_type, json.dumps(props or {}, ensure_ascii=False), canonical_fk),
    )


def _insert_kg_edge(
    *,
    src_id: str,
    dst_id: str,
    edge_type: str,
    run_id: str | None,
    resolve_method: str,
    props: dict[str, Any],
    tool_run_id: str | None,
) -> None:
    _db_execute(
        """
        INSERT INTO kg_edge (
          edge_id, src_id, dst_id, edge_type, edge_class, resolve_method,
          props_jsonb, evidence_ref_id, tool_run_id, run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NULL, %s::uuid, %s::uuid)
        """,
        (
            str(uuid4()),
            src_id,
            dst_id,
            edge_type,
            "llm",
            resolve_method,
            json.dumps(props or {}, ensure_ascii=False),
            tool_run_id,
            run_id,
        ),
    )


def link_policy_clauses_to_spatial_layers(
    *,
    authority_id: str,
    plan_cycle_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    layers = _db_fetch_all(
        """
        SELECT id, type, spatial_scope, properties
        FROM spatial_features
        WHERE authority_id = %s
          AND is_active = true
          AND (properties->>'layer_profile')::boolean = true
        ORDER BY type ASC
        """,
        (authority_id,),
    )
    if not layers:
        return {"linked": 0, "errors": []}

    clauses = _db_fetch_all(
        """
        SELECT pc.id AS policy_clause_id, pc.text, ps.policy_code, d.metadata->>'title' AS document_title
        FROM policy_clauses pc
        JOIN policy_sections ps ON ps.id = pc.policy_section_id
        JOIN documents d ON d.id = ps.document_id
        WHERE d.is_active = true
          AND d.authority_id = %s
          AND (%s::uuid IS NULL OR d.plan_cycle_id = %s::uuid)
        ORDER BY ps.policy_code ASC NULLS LAST, pc.clause_ref ASC NULLS LAST
        """,
        (authority_id, plan_cycle_id, plan_cycle_id),
    )

    layer_payload = []
    for layer in layers:
        props = layer.get("properties") if isinstance(layer.get("properties"), dict) else {}
        layer_payload.append(
            {
                "spatial_feature_id": str(layer.get("id")),
                "layer_key": props.get("layer_key") or layer.get("type"),
                "layer_name": props.get("layer_name") or layer.get("spatial_scope"),
                "summary": props.get("interpreted_summary") or props.get("layer_name") or layer.get("type"),
                "limitations": props.get("interpreted_limitations"),
            }
        )

    links: list[dict[str, Any]] = []
    errors: list[str] = []
    batch_size = 50
    for i in range(0, len(clauses), batch_size):
        batch = clauses[i : i + batch_size]
        payload = {
            "layers": layer_payload,
            "policy_clauses": [
                {
                    "policy_clause_id": str(c.get("policy_clause_id")),
                    "policy_code": c.get("policy_code"),
                    "document_title": c.get("document_title"),
                    "text": c.get("text"),
                }
                for c in batch
            ],
        }
        system = (
            "You are linking planning policy clauses to GIS layer profiles.\n"
            "Return ONLY valid JSON: {\"links\": [{\"policy_clause_id\": string, \"spatial_feature_id\": string, "
            "\"relation\": string, \"confidence\": string, \"notes\": string}]}.\n"
            "Rules:\n"
            "- Only use policy_clause_id and spatial_feature_id from the payload.\n"
            "- Only emit links that are clearly supported by the clause text.\n"
            "- Relation should be a short verb phrase (e.g. 'applies_in', 'constrains', 'requires_consideration_of').\n"
        )
        temperature = float(os.environ.get("TPA_LLM_SPATIAL_LINK_TEMPERATURE", "0.3"))
        obj, tool_run_id, errs = _llm_structured_sync(
            prompt_id="spatial_policy_links.v1",
            prompt_version=1,
            prompt_name="Spatial policy links",
            purpose="Propose policy ↔ GIS layer links for plan-making.",
            system_template=system,
            user_payload=payload,
            output_schema_ref="schemas/SpatialPolicyLinks.schema.json",
            run_id=run_id,
            temperature=temperature,
        )
        if errs:
            errors.extend(errs)
        if not isinstance(obj, dict):
            continue
        for link in obj.get("links") if isinstance(obj.get("links"), list) else []:
            if not isinstance(link, dict):
                continue
            policy_clause_id = link.get("policy_clause_id")
            spatial_feature_id = link.get("spatial_feature_id")
            if not isinstance(policy_clause_id, str) or not isinstance(spatial_feature_id, str):
                continue
            relation = link.get("relation") if isinstance(link.get("relation"), str) else "applies_in"
            confidence = link.get("confidence") if isinstance(link.get("confidence"), str) else "medium"
            notes = link.get("notes") if isinstance(link.get("notes"), str) else None
            _ensure_kg_node(
                node_id=f"policy_clause::{policy_clause_id}",
                node_type="PolicyClause",
                canonical_fk=policy_clause_id,
                props={},
            )
            _ensure_kg_node(
                node_id=f"spatial_feature::{spatial_feature_id}",
                node_type="SpatialFeature",
                canonical_fk=spatial_feature_id,
                props={},
            )
            _insert_kg_edge(
                src_id=f"policy_clause::{policy_clause_id}",
                dst_id=f"spatial_feature::{spatial_feature_id}",
                edge_type="APPLIES_IN",
                run_id=run_id,
                resolve_method="llm_spatial_policy_links_v1",
                props={"relation": relation, "confidence": confidence, "notes": notes, "linked_at": _utc_now().isoformat()},
                tool_run_id=tool_run_id,
            )
            links.append(link)

    return {"linked": len(links), "errors": errors}
