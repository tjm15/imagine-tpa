from __future__ import annotations

import base64
import os
from typing import Any

import httpx


def _llm_model_id() -> str:
    return os.environ.get("TPA_LLM_MODEL_ID") or os.environ.get("TPA_LLM_MODEL") or "openai/gpt-oss-20b"


def _vlm_model_id() -> str:
    return os.environ.get("TPA_VLM_MODEL_ID") or "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8"


def _model_supervisor_headers() -> dict[str, str]:
    token = os.environ.get("TPA_MODEL_SUPERVISOR_TOKEN")
    if not token:
        return {}
    return {"x-tpa-model-supervisor-token": token}


def _ensure_model_role_sync(*, role: str, timeout_seconds: float = 180.0) -> str | None:
    supervisor = os.environ.get("TPA_MODEL_SUPERVISOR_URL")
    if not supervisor:
        return None

    url = supervisor.rstrip("/") + "/ensure"
    timeout = None
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json={"role": role}, headers=_model_supervisor_headers())
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001
        return None

    base_url = data.get("base_url") if isinstance(data, dict) else None
    if isinstance(base_url, str) and base_url.startswith("http"):
        return base_url
    return None


async def _ensure_model_role(*, role: str, timeout_seconds: float = 180.0) -> str | None:
    supervisor = os.environ.get("TPA_MODEL_SUPERVISOR_URL")
    if not supervisor:
        return None

    url = supervisor.rstrip("/") + "/ensure"
    timeout = None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json={"role": role}, headers=_model_supervisor_headers())
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001
        return None

    base_url = data.get("base_url") if isinstance(data, dict) else None
    if isinstance(base_url, str) and base_url.startswith("http"):
        return base_url
    return None


def _rerank_texts_sync(
    *,
    query: str,
    texts: list[str],
    model_id: str | None = None,
    time_budget_seconds: float = 60.0,
) -> list[float] | None:
    base_url = _ensure_model_role_sync(role="reranker", timeout_seconds=180.0) or os.environ.get("TPA_RERANKER_BASE_URL")
    if not base_url:
        return None

    model_id = model_id or os.environ.get("TPA_RERANKER_MODEL_ID", "Qwen/Qwen3-Reranker-4B")
    timeout = None
    url_base = base_url.rstrip("/")

    docs = [{"id": str(i), "text": t} for i, t in enumerate(texts)]
    payloads: list[tuple[str, dict[str, Any]]] = [
        (url_base + "/v1/rerank", {"model": model_id, "query": query, "documents": docs, "top_n": len(docs)}),
        (url_base + "/rerank", {"model": model_id, "query": query, "documents": docs, "top_n": len(docs)}),
        (url_base + "/rerank", {"query": query, "texts": texts}),
    ]

    for url, payload in payloads:
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=payload)
                if resp.status_code >= 400:
                    continue
                data = resp.json()
        except Exception:  # noqa: BLE001
            continue

        # Common shapes:
        # - { results: [{ index, score | relevance_score }] }
        # - { data: [{ index, score }] }
        # - [ { index, score } ]
        # - [score, score, ...]
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            scores = [0.0 for _ in texts]
            for item in data["results"]:
                if not isinstance(item, dict):
                    continue
                idx = item.get("index")
                val = item.get("score") if isinstance(item.get("score"), (int, float)) else item.get("relevance_score")
                if isinstance(idx, int) and isinstance(val, (int, float)) and 0 <= idx < len(scores):
                    scores[idx] = float(val)
            return scores

        if isinstance(data, dict) and isinstance(data.get("data"), list):
            scores = [0.0 for _ in texts]
            for item in data["data"]:
                if not isinstance(item, dict):
                    continue
                idx = item.get("index")
                val = item.get("score")
                if isinstance(idx, int) and isinstance(val, (int, float)) and 0 <= idx < len(scores):
                    scores[idx] = float(val)
            return scores

        if isinstance(data, list) and all(isinstance(x, dict) for x in data):
            scores = [0.0 for _ in texts]
            for item in data:
                idx = item.get("index") if isinstance(item, dict) else None
                val = item.get("score") if isinstance(item, dict) else None
                if isinstance(idx, int) and isinstance(val, (int, float)) and 0 <= idx < len(scores):
                    scores[idx] = float(val)
            return scores

        if isinstance(data, list) and all(isinstance(x, (int, float)) for x in data):
            return [float(x) for x in data]

    return None


async def _embed_texts(
    *,
    texts: list[str],
    model_id: str | None = None,
    time_budget_seconds: float = 30.0,
) -> list[list[float]] | None:
    base_url = await _ensure_model_role(role="embeddings", timeout_seconds=180.0) or os.environ.get("TPA_EMBEDDINGS_BASE_URL")
    if not base_url:
        return None

    model_id = model_id or os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B")
    timeout = None
    url_base = base_url.rstrip("/")

    candidates: list[tuple[str, dict[str, Any]]] = [
        (url_base + "/v1/embeddings", {"model": model_id, "input": texts}),
        (url_base + "/embeddings", {"model": model_id, "input": texts}),
        (url_base + "/embed", {"inputs": texts}),
    ]

    last_err: str | None = None
    for url, payload in candidates:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code >= 400:
                    last_err = f"{resp.status_code} {resp.text[:200]}"
                    continue
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            continue

        if isinstance(data, dict) and isinstance(data.get("data"), list):
            out: list[list[float]] = []
            for item in data["data"]:
                emb = item.get("embedding") if isinstance(item, dict) else None
                if isinstance(emb, list):
                    out.append([float(x) for x in emb if isinstance(x, (int, float))])
            return out if len(out) == len(texts) else None

        if isinstance(data, dict) and isinstance(data.get("embeddings"), list):
            embs = data["embeddings"]
            if all(isinstance(e, list) for e in embs):
                return [[float(x) for x in e if isinstance(x, (int, float))] for e in embs]

        if isinstance(data, list) and all(isinstance(e, list) for e in data):
            return [[float(x) for x in e if isinstance(x, (int, float))] for e in data]

        last_err = f"Unrecognized embedding response shape from {url}"

    if last_err:
        return None
    return None


def _embed_texts_sync(
    *,
    texts: list[str],
    model_id: str | None = None,
    time_budget_seconds: float = 30.0,
) -> list[list[float]] | None:
    base_url = _ensure_model_role_sync(role="embeddings", timeout_seconds=180.0) or os.environ.get("TPA_EMBEDDINGS_BASE_URL")
    if not base_url:
        return None

    model_id = model_id or os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B")
    timeout = None
    url_base = base_url.rstrip("/")

    candidates: list[tuple[str, dict[str, Any]]] = [
        (url_base + "/v1/embeddings", {"model": model_id, "input": texts}),
        (url_base + "/embeddings", {"model": model_id, "input": texts}),
        (url_base + "/embed", {"inputs": texts}),
    ]

    last_err: str | None = None
    for url, payload in candidates:
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=payload)
                if resp.status_code >= 400:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    continue
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            last_err = f"Request failed: {exc}"
            continue

        if isinstance(data, dict) and isinstance(data.get("data"), list):
            out: list[list[float]] = []
            for item in data["data"]:
                emb = item.get("embedding") if isinstance(item, dict) else None
                if isinstance(emb, list):
                    out.append([float(x) for x in emb if isinstance(x, (int, float))])
            if len(out) == len(texts):
                return out
            last_err = f"Mismatched embedding count: expected {len(texts)}, got {len(out)} from {url}"
            continue

        if isinstance(data, dict) and isinstance(data.get("embeddings"), list):
            embs = data["embeddings"]
            if all(isinstance(e, list) for e in embs):
                if len(embs) == len(texts):
                    return [[float(x) for x in e if isinstance(x, (int, float))] for e in embs]
                last_err = f"Mismatched embedding count (flat): expected {len(texts)}, got {len(embs)} from {url}"
            continue

        if isinstance(data, list) and all(isinstance(e, list) for e in data):
            if len(data) == len(texts):
                return [[float(x) for x in e if isinstance(x, (int, float))] for e in data]
            last_err = f"Mismatched embedding count (list): expected {len(texts)}, got {len(data)} from {url}"
            continue

        last_err = f"Unrecognized embedding response shape from {url}: {str(data)[:200]}"

    if last_err:
        print(f"DEBUG: _embed_texts_sync failed. Last error: {last_err}", flush=True)

    return None


def _embed_multimodal_sync(
    *,
    image_bytes: bytes,
    text: str,
    model_id: str | None = None,
    time_budget_seconds: float = 60.0,
) -> list[float] | None:
    base_url = _ensure_model_role_sync(role="embeddings", timeout_seconds=180.0) or os.environ.get("TPA_EMBEDDINGS_MM_BASE_URL") or os.environ.get("TPA_EMBEDDINGS_BASE_URL")
    if not base_url:
        return None

    model_id = model_id or os.environ.get("TPA_EMBEDDINGS_MM_MODEL_ID", "nomic-ai/colnomic-embed-multimodal-7b")
    timeout = None
    url_base = base_url.rstrip("/")

    data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    payloads: list[tuple[str, dict[str, Any]]] = [
        (url_base + "/v1/embeddings", {"model": model_id, "input": [{"image": data_url, "text": text}]}),
        (url_base + "/embeddings", {"model": model_id, "input": [{"image": data_url, "text": text}]}),
        (url_base + "/embed", {"model": model_id, "input": {"image": data_url, "text": text}}),
        (url_base + "/embed", {"inputs": [{"image": data_url, "text": text}]}),
    ]

    for url, payload in payloads:
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=payload)
                if resp.status_code >= 400:
                    continue
                data = resp.json()
        except Exception:  # noqa: BLE001
            continue

        if isinstance(data, dict) and isinstance(data.get("data"), list) and data["data"]:
            item = data["data"][0]
            emb = item.get("embedding") if isinstance(item, dict) else None
            if isinstance(emb, list):
                return [float(x) for x in emb if isinstance(x, (int, float))]

        if isinstance(data, dict) and isinstance(data.get("embedding"), list):
            return [float(x) for x in data["embedding"] if isinstance(x, (int, float))]

        if isinstance(data, list) and data and all(isinstance(x, (int, float)) for x in data):
            return [float(x) for x in data]

        if isinstance(data, list) and data and isinstance(data[0], list):
            emb = data[0]
            if all(isinstance(x, (int, float)) for x in emb):
                return [float(x) for x in emb]

    return None


def _generate_completion_sync(
    *,
    prompt: str,
    system: str | None = None,
    model_id: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    time_budget_seconds: float = 60.0,
) -> str | None:
    base_url = _ensure_model_role_sync(role="llm", timeout_seconds=180.0) or os.environ.get("TPA_LLM_BASE_URL")
    if not base_url:
        return None

    model_id = model_id or _llm_model_id()
    timeout = None
    url = base_url.rstrip("/") + "/v1/chat/completions"

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=_model_supervisor_headers())
            if resp.status_code >= 400:
                return None
            data = resp.json()
            if isinstance(data, dict) and "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
    except Exception:
        pass
    return None
