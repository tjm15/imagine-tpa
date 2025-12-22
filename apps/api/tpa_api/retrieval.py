from __future__ import annotations

import json
import os
import re
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from .db import _db_execute, _db_fetch_all
from .model_clients import _embed_texts_sync, _rerank_texts_sync
from .time_utils import _utc_now
from .vector_utils import _vector_literal


def _gather_draft_evidence(
    *,
    authority_id: str,
    query_text: str,
    plan_cycle_id: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """
    Retrieval for drafting (Loop A).

    Prefer hybrid retrieval (FTS + pgvector + optional reranker) and fall back to simple keyword
    matching if indexing is not present yet.
    """
    limit = max(1, min(int(limit), 20))

    try:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()

        clause = _retrieve_policy_clauses_hybrid_sync(
            query=query_text,
            authority_id=authority_id,
            plan_cycle_id=plan_cycle_id,
            limit=min(12, max(limit, 6)),
            use_vector=True,
            use_fts=True,
            rerank=True,
            rerank_top_n=20,
        )
        clause_results = clause.get("results") if isinstance(clause, dict) else None
        if isinstance(clause_results, list):
            for r in clause_results:
                ev = r.get("evidence_ref")
                if not isinstance(ev, str) or ev in seen:
                    continue
                seen.add(ev)
                merged.append(
                    {
                        "evidence_ref": ev,
                        "document_title": r.get("document_title"),
                        "page_number": None,
                        "snippet": r.get("snippet"),
                        "policy_ref": r.get("policy_ref"),
                    }
                )

        hybrid = _retrieve_chunks_hybrid_sync(
            query=query_text,
            authority_id=authority_id,
            plan_cycle_id=plan_cycle_id,
            limit=min(12, max(limit, 6)),
            use_vector=True,
            use_fts=True,
            rerank=True,
            rerank_top_n=20,
        )
        chunk_results = hybrid.get("results") if isinstance(hybrid, dict) else None
        if isinstance(chunk_results, list):
            for r in chunk_results:
                ev = r.get("evidence_ref")
                if not isinstance(ev, str) or ev in seen:
                    continue
                seen.add(ev)
                merged.append(
                    {
                        "evidence_ref": ev,
                        "document_title": r.get("document_title"),
                        "page_number": r.get("page_number"),
                        "snippet": r.get("snippet"),
                    }
                )

        if merged:
            return merged[:limit]
    except Exception:  # noqa: BLE001
        pass

    terms = [t.lower() for t in re.findall(r"[A-Za-z]{4,}", query_text)][:3]
    if not terms:
        terms = ["policy"]

    where = " OR ".join(["c.text ILIKE %s" for _ in terms])
    clauses: list[str] = ["d.authority_id = %s"]
    params: list[Any] = [authority_id]
    if plan_cycle_id:
        clauses.append("d.plan_cycle_id = %s::uuid")
        params.append(plan_cycle_id)
    clauses.append("d.is_active = true")
    clauses.append(f"({where})")
    params.extend([f"%{t}%" for t in terms])
    params.append(limit)

    sql = f"""
        SELECT
          c.id AS chunk_id,
          c.page_number,
          LEFT(c.text, 800) AS snippet,
          er.source_type,
          er.source_id,
          er.fragment_id,
          d.metadata->>'title' AS document_title
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        LEFT JOIN evidence_refs er ON er.id = c.evidence_ref_id
        WHERE {" AND ".join(clauses)}
        ORDER BY c.page_number NULLS LAST
        LIMIT %s
    """

    try:
        rows = _db_fetch_all(sql, tuple(params))
    except HTTPException:
        return []

    out: list[dict[str, Any]] = []
    for r in rows:
        if r.get("source_type") and r.get("source_id") and r.get("fragment_id"):
            evidence_ref = f"{r['source_type']}::{r['source_id']}::{r['fragment_id']}"
        else:
            evidence_ref = f"chunk::{r['chunk_id']}::page-unknown"
        out.append(
            {
                "evidence_ref": evidence_ref,
                "document_title": r.get("document_title"),
                "page_number": r.get("page_number"),
                "snippet": r.get("snippet"),
            }
        )
    return out


def _retrieve_chunks_hybrid_sync(
    *,
    query: str,
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    limit: int = 12,
    rrf_k: int = 60,
    use_vector: bool = True,
    use_fts: bool = True,
    rerank: bool = True,
    rerank_top_n: int = 20,
) -> dict[str, Any]:
    """
    OSS RetrievalProvider v0:
    - FTS (websearch_to_tsquery) + pgvector (unit_embeddings) merged via RRF.
    - Optional reranking via external reranker service (Qwen3 reranker family).

    Always logs a ToolRun (and optionally a rerank ToolRun) and returns ids.
    """
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    limit = max(1, min(int(limit), 50))
    rrf_k = max(1, min(int(rrf_k), 500))
    rerank_top_n = max(1, min(int(rerank_top_n), 50))

    embedding_model_id = os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B")
    reranker_model_id = os.environ.get("TPA_RERANKER_MODEL_ID", "Qwen/Qwen3-Reranker-4B")

    retrieval_tool_run_id = str(uuid4())
    started_at = _utc_now()

    kw_rows: list[dict[str, Any]] = []
    vec_rows: list[dict[str, Any]] = []
    used: dict[str, bool] = {"fts": False, "vector": False, "rerank": False}
    errors: list[str] = []

    where: list[str] = []
    params_base: list[Any] = []
    if authority_id:
        where.append("d.authority_id = %s")
        params_base.append(authority_id)
    if plan_cycle_id:
        where.append("d.plan_cycle_id = %s::uuid")
        params_base.append(plan_cycle_id)
    where.append("d.is_active = true")
    where_sql = " AND ".join(where) if where else "TRUE"

    if use_fts:
        try:
            kw_rows = _db_fetch_all(
                f"""
                SELECT
                  c.id AS chunk_id,
                  c.page_number,
                  c.section_path,
                  LEFT(c.text, 800) AS snippet,
                  c.text AS full_text,
                  er.source_type,
                  er.source_id,
                  er.fragment_id AS fragment_id,
                  d.metadata->>'title' AS document_title,
                  ts_rank_cd(
                    to_tsvector('english', c.text),
                    websearch_to_tsquery('english', %s)
                  ) AS kw_score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                LEFT JOIN evidence_refs er ON er.id = c.evidence_ref_id
                WHERE {where_sql}
                  AND to_tsvector('english', c.text) @@ websearch_to_tsquery('english', %s)
                ORDER BY kw_score DESC
                LIMIT %s
                """,
                tuple(params_base + [query, query, limit]),
            )
            used["fts"] = True
        except Exception as exc:  # noqa: BLE001
            errors.append(f"fts_failed: {exc}")
            kw_rows = []

    query_vec: list[float] | None = None
    if use_vector:
        try:
            embedded = _embed_texts_sync(texts=[query], model_id=embedding_model_id, time_budget_seconds=30.0)
            if embedded and embedded[0]:
                query_vec = embedded[0]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"embed_failed: {exc}")
            query_vec = None

        if query_vec:
            try:
                vec_rows = _db_fetch_all(
                    f"""
                    SELECT
                      c.id AS chunk_id,
                      c.page_number,
                      c.section_path,
                      LEFT(c.text, 800) AS snippet,
                      c.text AS full_text,
                      er.source_type,
                      er.source_id,
                      er.fragment_id AS fragment_id,
                      d.metadata->>'title' AS document_title,
                      (ue.embedding <=> %s::vector) AS vec_distance
                    FROM unit_embeddings ue
                    JOIN chunks c ON c.id = ue.unit_id
                    JOIN documents d ON d.id = c.document_id
                    LEFT JOIN evidence_refs er ON er.id = c.evidence_ref_id
                    WHERE {where_sql}
                      AND ue.embedding_model_id = %s
                      AND ue.unit_type = 'chunk'
                    ORDER BY vec_distance ASC
                    LIMIT %s
                    """,
                    tuple([_vector_literal(query_vec)] + params_base + [embedding_model_id, limit]),
                )
                used["vector"] = True
            except Exception as exc:  # noqa: BLE001
                errors.append(f"vector_search_failed: {exc}")
                vec_rows = []

    def rrf_scores(rows: list[dict[str, Any]]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for rank, r in enumerate(rows, start=1):
            cid = str(r.get("chunk_id"))
            if not cid:
                continue
            scores[cid] = 1.0 / float(rrf_k + rank)
        return scores

    kw_rrf = rrf_scores(kw_rows)
    vec_rrf = rrf_scores(vec_rows)

    merged_ids = set(kw_rrf.keys()) | set(vec_rrf.keys())
    merged: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for r in kw_rows + vec_rows:
        cid = str(r.get("chunk_id"))
        if not cid or cid in by_id:
            continue
        by_id[cid] = r

    for cid in merged_ids:
        base = by_id.get(cid) or {}
        merged.append(
            {
                "chunk_id": cid,
                "page_number": base.get("page_number"),
                "section_path": base.get("section_path"),
                "snippet": base.get("snippet"),
                "full_text": base.get("full_text"),
                "document_title": base.get("document_title"),
                "fragment_id": base.get("fragment_id") or "page-unknown",
                "rrf_score": float(kw_rrf.get(cid, 0.0) + vec_rrf.get(cid, 0.0)),
                "kw_score": float(base.get("kw_score") or 0.0) if cid in kw_rrf else 0.0,
                "vec_distance": float(base.get("vec_distance") or 0.0) if cid in vec_rrf else None,
            }
        )

    merged.sort(key=lambda x: x["rrf_score"], reverse=True)
    merged = merged[: max(limit, rerank_top_n)]

    rerank_used = False
    rerank_tool_run_id: str | None = None
    if rerank and merged:
        top = merged[:rerank_top_n]
        scores = _rerank_texts_sync(query=query, texts=[str(r.get("full_text") or "")[:4000] for r in top], model_id=reranker_model_id)
        if scores and len(scores) == len(top):
            rerank_used = True
            used["rerank"] = True
            rerank_tool_run_id = str(uuid4())
            r_started = _utc_now()
            for r, score in zip(top, scores, strict=True):
                r["rerank_score"] = float(score)
            top.sort(key=lambda x: float(x.get("rerank_score") or 0.0), reverse=True)
            merged = top + merged[rerank_top_n:]

            _db_execute(
                """
                INSERT INTO tool_runs (
                  id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
                )
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
                """,
                (
                    rerank_tool_run_id,
                    "rerank_chunks",
                    json.dumps(
                        {
                            "model_id": reranker_model_id,
                            "query": query,
                            "candidate_count": len(top),
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "top": [
                                {"chunk_id": r["chunk_id"], "score": r.get("rerank_score")}
                                for r in top[: min(20, len(top))]
                            ]
                        },
                        ensure_ascii=False,
                    ),
                    "success",
                    r_started,
                    _utc_now(),
                    "medium",
                    "Cross-encoder reranking is an evidence instrument; treat as a relevance aid, not a determination.",
                ),
            )
        else:
            errors.append("rerank_unavailable_or_failed")

    # finalize, strip full_text from response
    results: list[dict[str, Any]] = []
    for r in merged[:limit]:
        if r.get("source_type") and r.get("source_id") and r.get("fragment_id"):
            evidence_ref = f"{r['source_type']}::{r['source_id']}::{r['fragment_id']}"
        else:
            evidence_ref = f"chunk::{r['chunk_id']}::page-unknown"
        results.append(
            {
                "chunk_id": r["chunk_id"],
                "evidence_ref": evidence_ref,
                "document_title": r.get("document_title"),
                "page_number": r.get("page_number"),
                "section_path": r.get("section_path"),
                "snippet": r.get("snippet"),
                "scores": {
                    "rrf": r.get("rrf_score"),
                    "keyword": r.get("kw_score") if r.get("kw_score") else None,
                    "vector_distance": r.get("vec_distance"),
                    "rerank_score": r.get("rerank_score"),
                },
            }
        )

    ended_at = _utc_now()
    _db_execute(
        """
        INSERT INTO tool_runs (
          id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
        )
        VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
        """,
        (
            retrieval_tool_run_id,
            "retrieve_chunks_hybrid",
            json.dumps(
                {
                    "query": query,
                    "authority_id": authority_id,
                    "plan_cycle_id": plan_cycle_id,
                    "limit": limit,
                    "use_vector": use_vector,
                    "use_fts": use_fts,
                    "rrf_k": rrf_k,
                    "rerank": rerank,
                    "rerank_top_n": rerank_top_n,
                    "embedding_model_id": embedding_model_id,
                    "reranker_model_id": reranker_model_id,
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "used": used,
                    "rerank_used": rerank_used,
                    "errors": errors[:20],
                    "top_ids": [r["chunk_id"] for r in results[: min(20, len(results))]],
                },
                ensure_ascii=False,
            ),
            "success" if results and not errors else ("partial" if results else "error"),
            started_at,
            ended_at,
            "medium" if results else "low",
            "Hybrid retrieval is an evidence instrument; verify relevance and provenance in-context.",
        ),
    )

    return {"results": results, "tool_run_id": retrieval_tool_run_id, "rerank_tool_run_id": rerank_tool_run_id}


def _retrieve_policy_clauses_hybrid_sync(
    *,
    query: str,
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    limit: int = 12,
    rrf_k: int = 60,
    use_vector: bool = True,
    use_fts: bool = True,
    rerank: bool = True,
    rerank_top_n: int = 20,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    limit = max(1, min(int(limit), 50))
    rrf_k = max(1, min(int(rrf_k), 500))
    rerank_top_n = max(1, min(int(rerank_top_n), 50))

    embedding_model_id = os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B")
    reranker_model_id = os.environ.get("TPA_RERANKER_MODEL_ID", "Qwen/Qwen3-Reranker-4B")

    retrieval_tool_run_id = str(uuid4())
    started_at = _utc_now()

    kw_rows: list[dict[str, Any]] = []
    vec_rows: list[dict[str, Any]] = []
    used: dict[str, bool] = {"fts": False, "vector": False, "rerank": False}
    errors: list[str] = []

    where: list[str] = ["d.is_active = true"]
    params_base: list[Any] = []
    if authority_id:
        where.append("d.authority_id = %s")
        params_base.append(authority_id)
    if plan_cycle_id:
        where.append("d.plan_cycle_id = %s::uuid")
        params_base.append(plan_cycle_id)
        # Default to the latest completed ingest batch for this plan cycle to avoid mixing parse versions.
        where.append(
            """
            d.ingest_batch_id = (
              SELECT ib.id
              FROM ingest_batches ib
              WHERE ib.plan_cycle_id = %s::uuid
                AND ib.status IN ('success', 'partial')
              ORDER BY ib.completed_at DESC NULLS LAST, ib.started_at DESC
              LIMIT 1
            )
            """
        )
        params_base.append(plan_cycle_id)
    where_sql = " AND ".join(where) if where else "TRUE"

    if use_fts:
        try:
            kw_rows = _db_fetch_all(
                f"""
                SELECT
                  pc.id AS policy_clause_id,
                  pc.clause_ref,
                  ps.section_path AS section_path,
                  pc.speech_act_jsonb AS speech_act,
                  LEFT(pc.text, 800) AS snippet,
                  pc.text AS full_text,
                  ps.id AS policy_section_id,
                  ps.policy_code AS policy_code,
                  ps.title AS policy_title,
                  d.metadata->>'title' AS document_title,
                  ts_rank_cd(
                    to_tsvector('english', pc.text),
                    websearch_to_tsquery('english', %s)
                  ) AS kw_score
                FROM policy_clauses pc
                JOIN policy_sections ps ON ps.id = pc.policy_section_id
                JOIN documents d ON d.id = ps.document_id
                WHERE {where_sql}
                  AND to_tsvector('english', pc.text) @@ websearch_to_tsquery('english', %s)
                ORDER BY kw_score DESC
                LIMIT %s
                """,
                tuple(params_base + [query, query, limit]),
            )
            used["fts"] = True
        except Exception as exc:  # noqa: BLE001
            errors.append(f"fts_failed: {exc}")
            kw_rows = []

    query_vec: list[float] | None = None
    if use_vector:
        try:
            embedded = _embed_texts_sync(texts=[query], model_id=embedding_model_id, time_budget_seconds=30.0)
            if embedded and embedded[0]:
                query_vec = embedded[0]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"embed_failed: {exc}")
            query_vec = None

        if query_vec:
            try:
                vec_rows = _db_fetch_all(
                    f"""
                    SELECT
                      pc.id AS policy_clause_id,
                      pc.clause_ref,
                      ps.section_path AS section_path,
                      pc.speech_act_jsonb AS speech_act,
                      LEFT(pc.text, 800) AS snippet,
                      pc.text AS full_text,
                      ps.id AS policy_section_id,
                      ps.policy_code AS policy_code,
                      ps.title AS policy_title,
                      d.metadata->>'title' AS document_title,
                      (ue.embedding <=> %s::vector) AS vec_distance
                    FROM unit_embeddings ue
                    JOIN policy_clauses pc ON pc.id = ue.unit_id
                    JOIN policy_sections ps ON ps.id = pc.policy_section_id
                    JOIN documents d ON d.id = ps.document_id
                    WHERE {where_sql}
                      AND ue.embedding_model_id = %s
                      AND ue.unit_type = 'policy_clause'
                    ORDER BY vec_distance ASC
                    LIMIT %s
                    """,
                    tuple([_vector_literal(query_vec)] + params_base + [embedding_model_id, limit]),
                )
                used["vector"] = True
            except Exception as exc:  # noqa: BLE001
                errors.append(f"vector_search_failed: {exc}")
                vec_rows = []

    def rrf_scores(rows: list[dict[str, Any]]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for rank, r in enumerate(rows, start=1):
            cid = str(r.get("policy_clause_id"))
            if not cid:
                continue
            scores[cid] = 1.0 / float(rrf_k + rank)
        return scores

    kw_rrf = rrf_scores(kw_rows)
    vec_rrf = rrf_scores(vec_rows)

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in kw_rows + vec_rows:
        cid = str(r.get("policy_clause_id"))
        if not cid or cid in seen:
            continue
        seen.add(cid)
        rrf_score = float(kw_rrf.get(cid, 0.0) + vec_rrf.get(cid, 0.0))
        merged.append(
            {
                "policy_clause_id": cid,
                "policy_section_id": str(r.get("policy_section_id")) if r.get("policy_section_id") else None,
                "clause_ref": r.get("clause_ref"),
                "policy_ref": r.get("policy_code"),
                "policy_title": r.get("policy_title"),
                "document_title": r.get("document_title"),
                "section_path": r.get("section_path"),
                "speech_act": r.get("speech_act"),
                "snippet": r.get("snippet"),
                "full_text": r.get("full_text"),
                "rrf_score": rrf_score,
                "kw_score": float(r.get("kw_score") or 0.0) if cid in kw_rrf else 0.0,
                "vec_distance": float(r.get("vec_distance") or 0.0) if cid in vec_rrf else None,
            }
        )

    merged.sort(key=lambda x: x["rrf_score"], reverse=True)
    merged = merged[: max(limit, rerank_top_n)]

    rerank_used = False
    rerank_tool_run_id: str | None = None
    if rerank and merged:
        top = merged[:rerank_top_n]
        scores = _rerank_texts_sync(query=query, texts=[str(r.get("full_text") or "")[:4000] for r in top], model_id=reranker_model_id)
        if scores and len(scores) == len(top):
            rerank_used = True
            used["rerank"] = True
            rerank_tool_run_id = str(uuid4())
            r_started = _utc_now()
            for r, score in zip(top, scores, strict=True):
                r["rerank_score"] = float(score)
            top.sort(key=lambda x: float(x.get("rerank_score") or 0.0), reverse=True)
            merged = top + merged[rerank_top_n:]

            _db_execute(
                """
                INSERT INTO tool_runs (
                  id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
                )
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
                """,
                (
                    rerank_tool_run_id,
                    "rerank_policy_clauses",
                    json.dumps(
                        {
                            "model_id": reranker_model_id,
                            "query": query,
                            "candidate_count": len(top),
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "top": [
                                {"policy_clause_id": r["policy_clause_id"], "score": r.get("rerank_score")}
                                for r in top[: min(20, len(top))]
                            ]
                        },
                        ensure_ascii=False,
                    ),
                    "success",
                    r_started,
                    _utc_now(),
                    "medium",
                    "Cross-encoder reranking is an evidence instrument; treat as a relevance aid, not a determination.",
                ),
            )
        else:
            errors.append("rerank_unavailable_or_failed")

    results: list[dict[str, Any]] = []
    for r in merged[:limit]:
        evidence_ref = f"policy_clause::{r['policy_clause_id']}::text"
        results.append(
            {
                "policy_clause_id": r["policy_clause_id"],
                "evidence_ref": evidence_ref,
                "policy_section_id": r.get("policy_section_id"),
                "clause_ref": r.get("clause_ref"),
                "policy_ref": r.get("policy_ref"),
                "policy_title": r.get("policy_title"),
                "document_title": r.get("document_title"),
                "section_path": r.get("section_path"),
                "speech_act": r.get("speech_act"),
                "snippet": r.get("snippet"),
                "scores": {
                    "rrf": r.get("rrf_score"),
                    "keyword": r.get("kw_score") if r.get("kw_score") else None,
                    "vector_distance": r.get("vec_distance"),
                    "rerank_score": r.get("rerank_score"),
                },
            }
        )

    ended_at = _utc_now()
    _db_execute(
        """
        INSERT INTO tool_runs (
          id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
        )
        VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
        """,
        (
            retrieval_tool_run_id,
            "retrieve_policy_clauses_hybrid",
            json.dumps(
                {
                    "query": query,
                    "authority_id": authority_id,
                    "plan_cycle_id": plan_cycle_id,
                    "limit": limit,
                    "use_vector": use_vector,
                    "use_fts": use_fts,
                    "rrf_k": rrf_k,
                    "rerank": rerank,
                    "rerank_top_n": rerank_top_n,
                    "embedding_model_id": embedding_model_id,
                    "reranker_model_id": reranker_model_id,
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "used": used,
                    "rerank_used": rerank_used,
                    "errors": errors[:20],
                    "top_ids": [r["policy_clause_id"] for r in results[: min(20, len(results))]],
                },
                ensure_ascii=False,
            ),
            "success" if results and not errors else ("partial" if results else "error"),
            started_at,
            ended_at,
            "medium" if results else "low",
            "Hybrid retrieval is an evidence instrument; verify relevance and provenance in-context.",
        ),
    )

    return {"results": results, "tool_run_id": retrieval_tool_run_id, "rerank_tool_run_id": rerank_tool_run_id}
