import asyncio
import json
from uuid import uuid4
from datetime import datetime
from typing import Dict, Any, List

from tpa_api.chunking import _semantic_chunk_lines
from tpa_api.db import _db_execute, _db_execute_returning
from tpa_api.model_clients import _embed_texts_sync, _generate_completion_sync
from tpa_api.vector_utils import _vector_literal

class KnowledgeGraphIngester:
    """
    Ingests CanonicalDocument -> Chunks -> Embeddings -> KG Nodes (Policies).
    """

    async def ingest_document(self, canonical_doc: Dict[str, Any], authority_id: str):
        doc_id = str(uuid4())
        title = canonical_doc.get("title", "Untitled Document")
        url = canonical_doc.get("url")
        content = canonical_doc.get("content_markdown", "")
        
        print(f"Ingesting doc {doc_id}: {title}")

        # 1. Persist Document
        _db_execute(
            """
            INSERT INTO documents (id, authority_id, metadata, is_active, created_at)
            VALUES (%s, %s, %s::jsonb, true, NOW())
            """,
            (doc_id, authority_id, json.dumps({"title": title, "url": url}))
        )

        # 2. Chunking
        lines = content.split("\n")
        chunks, _ = _semantic_chunk_lines(lines=lines, section_stack=[])
        print(f"  -> Generated {len(chunks)} chunks.")

        # Batch embed
        chunk_texts = [c["text"] for c in chunks]
        embeddings = _embed_texts_sync(texts=chunk_texts, time_budget_seconds=120.0)
        
        if not embeddings:
            print("  -> Warning: Embeddings failed. Using NULL vectors.")
            embeddings = [None] * len(chunks)

        for i, chunk in enumerate(chunks):
            chunk_id = str(uuid4())
            text = chunk["text"]
            embedding = embeddings[i]

            # 3. Persist Chunk
            _db_execute(
                """
                INSERT INTO chunks (id, document_id, page_number, section_path, text)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (chunk_id, doc_id, 1, chunk.get("section_path", ""), text)
            )

            # 4. Persist Embedding
            if embedding:
                 _db_execute(
                    """
                    INSERT INTO chunk_embeddings (chunk_id, embedding_model_id, embedding)
                    VALUES (%s, %s, %s::vector)
                    """,
                    (chunk_id, "Qwen/Qwen3-Embedding-8B", _vector_literal(embedding))
                )

            # 5. Extract Policy Node (Heuristic + LLM)
            if chunk["type"] == "heading" and "policy" in text.lower():
                await self._extract_policy_node(doc_id, chunk, authority_id, text)

    async def _extract_policy_node(self, doc_id: str, chunk: Dict[str, Any], authority_id: str, text: str):
        """
        Uses LLM to extract policy details since this looks like a policy.
        """
        prompt = (
            f"Extract the Policy Reference Code (e.g. 'CS1', 'dm4') and Title from this text.\n"
            f"Text: {text}\n"
            f"Return JSON: {{'code': '...', 'title': '...'}}"
        )
        
        resp = _generate_completion_sync(prompt=prompt, temperature=0.0)
        policy_code = "UNKNOWN"
        policy_title = "Unknown Policy"

        if resp:
            try:
                # Naive JSON parsing, in real code using a robust parser is better
                clean = resp.strip().replace("```json", "").replace("```", "")
                data = json.loads(clean)
                policy_code = data.get("code")
                policy_title = data.get("title")
            except Exception:
                pass
        
        # Fallback if LLM failed or wasn't clear
        if policy_code == "UNKNOWN":
             policy_title = text[:100]

        print(f"  -> Extracted Policy: {policy_code} - {policy_title}")

        # Upsert Policy Container
        # We assume one policy per code per authority for simplicity here
        policy_id = str(uuid4())
        
        # 6. Persist Policy
        _db_execute(
            """
            INSERT INTO policies (id, authority_id, metadata, is_active)
            VALUES (%s, %s, %s::jsonb, true)
            """,
            (policy_id, authority_id, json.dumps({"policy_ref": policy_code, "policy_title": policy_title, "document_title": "Local Plan"}))
        )
        
        # 7. Persist Policy Clause (The Text)
        _db_execute(
            """
            INSERT INTO policy_clauses (id, policy_id, clause_ref, text, metadata)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (str(uuid4()), policy_id, "full", text, json.dumps({"speech_act": "policy"}))
        )
