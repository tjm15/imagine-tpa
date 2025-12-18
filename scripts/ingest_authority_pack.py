#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid


def _http_json(method: str, url: str, payload: object | None = None, timeout_seconds: float = 60.0) -> object:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:  # noqa: S310
            raw = resp.read()
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            detail = ""
        raise RuntimeError(f"{exc.code} {exc.reason}{(': ' + detail[:600]) if detail else ''}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc)) from exc

    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Start and monitor an authority pack ingest run.")
    parser.add_argument("--api-base", default="http://localhost:8000", help="TPA API base URL (default: http://localhost:8000)")
    parser.add_argument("--authority-id", required=True, help="Authority ID (folder name under authority_packs/)")
    parser.add_argument("--plan-cycle-id", required=True, help="Existing plan_cycle_id (UUID)")
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="Polling interval (default: 2s)")
    parser.add_argument("--timeout-minutes", type=float, default=120.0, help="Stop polling after this long (default: 120m)")
    args = parser.parse_args()

    api_base = args.api_base.rstrip("/")
    try:
        uuid.UUID(str(args.plan_cycle_id))
    except Exception:  # noqa: BLE001
        print(
            "ERROR: --plan-cycle-id must be a UUID.\n"
            "List cycles: curl \"http://localhost:8000/plan-cycles?authority_id=<authority_id>\"\n"
            "Create one:  curl -X POST http://localhost:8000/plan-cycles -H 'content-type: application/json' "
            "-d '{\"authority_id\":\"<authority_id>\",\"plan_name\":\"Local Plan\",\"status\":\"draft\"}'",
            file=sys.stderr,
        )
        return 2

    start_url = f"{api_base}/ingest/authority-packs/{args.authority_id}/start"
    print(f"Starting ingest: {start_url}", flush=True)
    start = _http_json("POST", start_url, {"plan_cycle_id": args.plan_cycle_id}, timeout_seconds=60.0)
    if not isinstance(start, dict):
        print("Unexpected response shape from start endpoint.", file=sys.stderr)
        return 2

    ingest_batch_id = start.get("ingest_batch_id")
    if not isinstance(ingest_batch_id, str) or not ingest_batch_id:
        print(f"Start response did not include ingest_batch_id: {start}", file=sys.stderr)
        return 2

    print(f"Ingest batch: {ingest_batch_id}", flush=True)

    batch_url = f"{api_base}/ingest/batches/{ingest_batch_id}"
    deadline = time.time() + max(args.timeout_minutes, 1.0) * 60.0
    last_line = None

    while time.time() < deadline:
        res = _http_json("GET", batch_url, None, timeout_seconds=60.0)
        if not isinstance(res, dict) or not isinstance(res.get("ingest_batch"), dict):
            print(f"Unexpected batch response: {res}", file=sys.stderr)
            return 2

        b = res["ingest_batch"]
        status = b.get("status")
        outputs = b.get("outputs") if isinstance(b.get("outputs"), dict) else {}
        counts = outputs.get("counts") if isinstance(outputs.get("counts"), dict) else {}
        progress = outputs.get("progress") if isinstance(outputs.get("progress"), dict) else {}

        docs_seen = counts.get("documents_seen")
        chunks = counts.get("chunks")
        current_doc = progress.get("current_document")
        line = f"status={status} docs_seen={docs_seen} chunks={chunks}" + (f" current={current_doc}" if current_doc else "")
        if line != last_line:
            print(line, flush=True)
            last_line = line

        if status and status != "running":
            if status in {"success", "partial"}:
                return 0
            return 1

        time.sleep(max(args.poll_seconds, 0.5))

    print("Timed out waiting for ingest to finish. Check /ingest/batches in the UI/API.", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
