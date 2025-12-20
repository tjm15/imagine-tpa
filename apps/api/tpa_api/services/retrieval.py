from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import _db_fetch_all
from ..retrieval import _retrieve_chunks_hybrid_sync, _retrieve_policy_clauses_hybrid_sync


def search_chunks(
    *,
    q: str,
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    active_only: bool = True,
    limit: int = 12,
) -> JSONResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="q must not be empty")
    limit = max(1, min(int(limit), 50))

    like = f"%{query}%"
    where: list[str] = ["c.text ILIKE %s"]
    params: list[Any] = [like]
    if authority_id:
        where.append("d.authority_id = %s")
        params.append(authority_id)
    if plan_cycle_id:
        where.append("d.plan_cycle_id = %s::uuid")
        params.append(plan_cycle_id)
    if active_only:
        where.append("d.is_active = true")

    rows = _db_fetch_all(
        f"""
        SELECT
          c.id AS chunk_id,
          c.document_id,
          c.page_number,
          LEFT(c.text, 800) AS snippet,
          er.fragment_id AS fragment_id,
          d.metadata->>'title' AS document_title,
          d.blob_path AS blob_path,
          d.plan_cycle_id AS plan_cycle_id
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        LEFT JOIN evidence_refs er ON er.source_type = 'chunk' AND er.source_id = c.id::text
        WHERE {" AND ".join(where)}
        ORDER BY c.page_number NULLS LAST
        LIMIT %s
        """,
        tuple(params + [limit]),
    )

    results = [
        {
            "chunk_id": str(r["chunk_id"]),
            "document_id": str(r["document_id"]),
            "page_number": r["page_number"],
            "evidence_ref": f"chunk::{r['chunk_id']}::{r['fragment_id'] or 'page-unknown'}",
            "document_title": r["document_title"],
            "blob_path": r["blob_path"],
            "plan_cycle_id": str(r["plan_cycle_id"]) if r.get("plan_cycle_id") else None,
            "snippet": r["snippet"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"results": results}))


class RetrieveChunksRequest(BaseModel):
    query: str
    authority_id: str | None = None
    plan_cycle_id: str | None = None
    limit: int = 12
    rrf_k: int = 60
    use_vector: bool = True
    use_fts: bool = True
    rerank: bool = True
    rerank_top_n: int = 20


def retrieve_chunks(body: RetrieveChunksRequest) -> JSONResponse:
    out = _retrieve_chunks_hybrid_sync(
        query=body.query,
        authority_id=body.authority_id,
        plan_cycle_id=body.plan_cycle_id,
        limit=body.limit,
        rrf_k=body.rrf_k,
        use_vector=bool(body.use_vector),
        use_fts=bool(body.use_fts),
        rerank=bool(body.rerank),
        rerank_top_n=body.rerank_top_n,
    )
    return JSONResponse(content=jsonable_encoder(out))


class RetrievePolicyClausesRequest(BaseModel):
    query: str
    authority_id: str | None = None
    plan_cycle_id: str | None = None
    limit: int = 12
    rrf_k: int = 60
    use_vector: bool = True
    use_fts: bool = True
    rerank: bool = True
    rerank_top_n: int = 20


def retrieve_policy_clauses(body: RetrievePolicyClausesRequest) -> JSONResponse:
    out = _retrieve_policy_clauses_hybrid_sync(
        query=body.query,
        authority_id=body.authority_id,
        plan_cycle_id=body.plan_cycle_id,
        limit=body.limit,
        rrf_k=body.rrf_k,
        use_vector=bool(body.use_vector),
        use_fts=bool(body.use_fts),
        rerank=bool(body.rerank),
        rerank_top_n=body.rerank_top_n,
    )
    return JSONResponse(content=jsonable_encoder(out))
