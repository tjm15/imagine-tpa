from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..db import _db_fetch_all, _db_fetch_one
from ..time_utils import _utc_now_iso


def trace_run(run_id: str, mode: str = "summary") -> JSONResponse:
    if mode not in {"summary", "inspect", "forensic"}:
        raise HTTPException(status_code=400, detail="mode must be one of: summary, inspect, forensic")

    run = _db_fetch_one(
        "SELECT id, profile, culp_stage_id, anchors_jsonb, created_at FROM runs WHERE id = %s::uuid",
        (run_id,),
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    moves = _db_fetch_all(
        """
        SELECT id, move_type, sequence, status, created_at, inputs_jsonb, outputs_jsonb,
               evidence_refs_considered_jsonb, tool_run_ids_jsonb, uncertainty_remaining_jsonb
        FROM move_events
        WHERE run_id = %s::uuid
        ORDER BY sequence ASC
        """,
        (run_id,),
    )

    audit_rows = _db_fetch_all(
        """
        SELECT id, timestamp, event_type, actor_type, actor_id, payload_jsonb
        FROM audit_events
        WHERE run_id = %s::uuid
        ORDER BY timestamp ASC
        """,
        (run_id,),
    )

    move_ids = [str(m["id"]) for m in moves]
    evidence_links: list[dict[str, Any]] = []
    if move_ids:
        evidence_links = _db_fetch_all(
            """
            SELECT
              rel.id AS link_id,
              rel.move_event_id,
              rel.role,
              er.source_type,
              er.source_id,
              er.fragment_id
            FROM reasoning_evidence_links rel
            JOIN evidence_refs er ON er.id = rel.evidence_ref_id
            WHERE rel.move_event_id = ANY(%s::uuid[])
            ORDER BY rel.created_at ASC
            """,
            (move_ids,),
        )

    def evidence_ref_str(row: dict[str, Any]) -> str:
        return f"{row['source_type']}::{row['source_id']}::{row['fragment_id']}"

    tool_run_ids: list[str] = []
    for m in moves:
        ids = m.get("tool_run_ids_jsonb") or []
        if isinstance(ids, list):
            tool_run_ids.extend([str(x) for x in ids if isinstance(x, str)])
    tool_run_ids = sorted(set(tool_run_ids))

    tool_runs: list[dict[str, Any]] = []
    if tool_run_ids:
        tool_runs = _db_fetch_all(
            """
            SELECT id, tool_name, status, started_at, ended_at, confidence_hint
            FROM tool_runs
            WHERE id = ANY(%s::uuid[])
            ORDER BY started_at ASC NULLS LAST
            """,
            (tool_run_ids,),
        )

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    run_node_id = f"run::{run_id}"
    nodes.append(
        {
            "node_id": run_node_id,
            "node_type": "run",
            "label": f"Run ({run.get('profile')})",
            "ref": {"run_id": run_id, "culp_stage_id": run.get("culp_stage_id")},
            "layout": {"x": 0, "y": 0, "group": None},
            "severity": None,
        }
    )

    move_node_ids: dict[str, str] = {}
    for idx, m in enumerate(moves, start=1):
        move_id = str(m["id"])
        node_id = f"move::{move_id}"
        move_node_ids[move_id] = node_id
        status = m.get("status")
        severity = "error" if status == "error" else "warning" if status == "partial" else "info"
        nodes.append(
            {
                "node_id": node_id,
                "node_type": "move",
                "label": f"{m.get('sequence')}. {m.get('move_type')}",
                "ref": {"move_id": move_id, "move_type": m.get("move_type"), "status": status},
                "layout": {"x": 220, "y": idx * 120, "group": None},
                "severity": severity,
            }
        )
        edges.append(
            {
                "edge_id": f"edge::{uuid4()}",
                "src_id": run_node_id,
                "dst_id": node_id,
                "edge_type": "TRIGGERS",
                "label": None,
            }
        )

    tool_node_ids: dict[str, str] = {}
    tool_by_id = {str(t["id"]): t for t in tool_runs}
    for m in moves:
        move_id = str(m["id"])
        ids = m.get("tool_run_ids_jsonb") or []
        if not isinstance(ids, list):
            continue
        for j, tr_id in enumerate([x for x in ids if isinstance(x, str)], start=1):
            tr_id_str = str(tr_id)
            if tr_id_str not in tool_node_ids:
                tr = tool_by_id.get(tr_id_str) or {"tool_name": "tool", "status": "unknown"}
                status = tr.get("status")
                severity = "error" if status == "error" else "warning" if status == "partial" else "info"
                tool_node_ids[tr_id_str] = f"tool_run::{tr_id_str}"
                nodes.append(
                    {
                        "node_id": tool_node_ids[tr_id_str],
                        "node_type": "tool_run",
                        "label": f"{tr.get('tool_name')} ({status})",
                        "ref": {"tool_run_id": tr_id_str, "tool_name": tr.get("tool_name")},
                        "layout": {"x": 520, "y": (m.get("sequence") or 0) * 120 + (j * 18), "group": move_node_ids.get(move_id)},
                        "severity": severity,
                    }
                )
            edges.append(
                {
                    "edge_id": f"edge::{uuid4()}",
                    "src_id": move_node_ids.get(move_id) or run_node_id,
                    "dst_id": tool_node_ids[tr_id_str],
                    "edge_type": "USES",
                    "label": None,
                }
            )

    evidence_node_ids: dict[str, str] = {}
    for link in evidence_links:
        move_id = str(link["move_event_id"])
        ev = evidence_ref_str(link)
        if ev not in evidence_node_ids:
            evidence_node_ids[ev] = f"evidence::{ev}"
            nodes.append(
                {
                    "node_id": evidence_node_ids[ev],
                    "node_type": "evidence",
                    "label": link.get("source_type") or "evidence",
                    "ref": {"evidence_ref": ev},
                    "layout": {"x": 840, "y": 0, "group": move_node_ids.get(move_id)},
                    "severity": None,
                }
            )
        edges.append(
            {
                "edge_id": f"edge::{uuid4()}",
                "src_id": move_node_ids.get(move_id) or run_node_id,
                "dst_id": evidence_node_ids[ev],
                "edge_type": "CITES",
                "label": link.get("role"),
            }
        )

    # Also include audit events linked to the run (selection, completion, etc.)
    for idx, a in enumerate(audit_rows[:50], start=1):
        node_id = f"audit::{a['id']}"
        nodes.append(
            {
                "node_id": node_id,
                "node_type": "audit_event",
                "label": a.get("event_type") or "audit_event",
                "ref": {"audit_event_id": str(a["id"]), "timestamp": a.get("timestamp")},
                "layout": {"x": 0, "y": 120 + idx * 26, "group": None},
                "severity": None,
            }
        )
        edges.append(
            {
                "edge_id": f"edge::{uuid4()}",
                "src_id": node_id,
                "dst_id": run_node_id,
                "edge_type": "TRIGGERS",
                "label": a.get("actor_type"),
            }
        )

    trace = {
        "trace_graph_id": str(uuid4()),
        "run_id": run_id,
        "mode": mode,
        "nodes": nodes,
        "edges": edges,
        "created_at": _utc_now_iso(),
    }
    return JSONResponse(content=jsonable_encoder(trace))
