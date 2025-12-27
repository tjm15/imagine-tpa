from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from tpa_api.db import _db_execute


def _ensure_kg_node(*, node_id: str, node_type: str, canonical_fk: str | None = None, props: dict[str, Any] | None = None) -> None:
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
    edge_class: str | None = None,
    resolve_method: str | None = None,
    props: dict[str, Any] | None = None,
    evidence_ref_id: str | None = None,
    tool_run_id: str | None = None,
) -> None:
    _db_execute(
        """
        INSERT INTO kg_edge (
          edge_id, src_id, dst_id, edge_type, edge_class, resolve_method, props_jsonb,
          evidence_ref_id, tool_run_id, run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::uuid, %s::uuid, %s::uuid)
        """,
        (
            str(uuid4()),
            src_id,
            dst_id,
            edge_type,
            edge_class,
            resolve_method,
            json.dumps(props or {}, ensure_ascii=False),
            evidence_ref_id,
            tool_run_id,
            run_id,
        ),
    )


def _persist_kg_nodes(
    *,
    document_id: str,
    chunks: list[dict[str, Any]],
    visual_assets: list[dict[str, Any]],
    policy_sections: list[dict[str, Any]] | None = None,
    policy_clauses: list[dict[str, Any]] | None = None,
    definitions: list[dict[str, Any]] | None = None,
    targets: list[dict[str, Any]] | None = None,
    monitoring: list[dict[str, Any]] | None = None,
) -> None:
    _db_execute(
        "INSERT INTO kg_node (node_id, node_type, props_jsonb, canonical_fk) VALUES (%s, %s, %s::jsonb, %s)",
        (f"doc::{document_id}", "Document", json.dumps({}, ensure_ascii=False), document_id),
    )
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        if not chunk_id:
            continue
        _db_execute(
            "INSERT INTO kg_node (node_id, node_type, props_jsonb, canonical_fk) VALUES (%s, %s, %s::jsonb, %s)",
            (f"chunk::{chunk_id}", "Chunk", json.dumps({}, ensure_ascii=False), chunk_id),
        )
    for asset in visual_assets:
        asset_id = asset.get("visual_asset_id")
        if not asset_id:
            continue
        _db_execute(
            "INSERT INTO kg_node (node_id, node_type, props_jsonb, canonical_fk) VALUES (%s, %s, %s::jsonb, %s)",
            (f"visual_asset::{asset_id}", "VisualAsset", json.dumps(asset.get("metadata") or {}, ensure_ascii=False), asset_id),
        )

    for section in policy_sections or []:
        section_id = section.get("policy_section_id")
        if not section_id:
            continue
        _ensure_kg_node(
            node_id=f"policy_section::{section_id}",
            node_type="PolicySection",
            canonical_fk=str(section_id),
            props={"policy_code": section.get("policy_code"), "title": section.get("title")},
        )

    for clause in policy_clauses or []:
        clause_id = clause.get("policy_clause_id")
        if not clause_id:
            continue
        _ensure_kg_node(
            node_id=f"policy_clause::{clause_id}",
            node_type="PolicyClause",
            canonical_fk=str(clause_id),
            props={"policy_section_id": clause.get("policy_section_id"), "policy_code": clause.get("policy_code")},
        )

    for definition in definitions or []:
        definition_id = definition.get("definition_id")
        if not definition_id:
            continue
        _ensure_kg_node(
            node_id=f"definition::{definition_id}",
            node_type="Definition",
            canonical_fk=str(definition_id),
            props={"term": definition.get("term")},
        )

    for target in targets or []:
        target_id = target.get("target_id")
        if not target_id:
            continue
        _ensure_kg_node(
            node_id=f"target::{target_id}",
            node_type="Target",
            canonical_fk=str(target_id),
            props={},
        )

    for hook in monitoring or []:
        hook_id = hook.get("monitoring_hook_id")
        if not hook_id:
            continue
        _ensure_kg_node(
            node_id=f"monitoring::{hook_id}",
            node_type="MonitoringHook",
            canonical_fk=str(hook_id),
            props={"indicator_text": hook.get("indicator_text")},
        )
