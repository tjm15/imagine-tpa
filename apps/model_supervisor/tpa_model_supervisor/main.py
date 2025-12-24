from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Literal

import docker
import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel


Role = Literal["llm", "vlm", "embeddings", "embeddings_mm", "reranker", "sam2"]


@dataclass(frozen=True)
class RoleSpec:
    role: Role
    compose_service: str
    base_url_env: str
    default_base_url: str
    ready_path: str
    gpu_exclusive: bool


ROLE_SPECS: dict[Role, RoleSpec] = {
    "llm": RoleSpec(
        role="llm",
        compose_service=os.environ.get("TPA_LLM_COMPOSE_SERVICE", "tpa-llm"),
        base_url_env="TPA_LLM_BASE_URL",
        default_base_url="http://tpa-llm:8000/v1",
        ready_path="/models",
        gpu_exclusive=True,
    ),
    "vlm": RoleSpec(
        role="vlm",
        compose_service=os.environ.get("TPA_VLM_COMPOSE_SERVICE", "tpa-vlm"),
        base_url_env="TPA_VLM_BASE_URL",
        default_base_url="http://tpa-vlm:8000/v1",
        ready_path="/models",
        gpu_exclusive=True,
    ),
    "embeddings": RoleSpec(
        role="embeddings",
        compose_service=os.environ.get("TPA_EMBEDDINGS_COMPOSE_SERVICE", "tpa-embeddings"),
        base_url_env="TPA_EMBEDDINGS_BASE_URL",
        default_base_url="http://tpa-embeddings:8080",
        ready_path="/health",
        gpu_exclusive=True,
    ),
    "embeddings_mm": RoleSpec(
        role="embeddings_mm",
        compose_service=os.environ.get("TPA_EMBEDDINGS_MM_COMPOSE_SERVICE", "tpa-embeddings-mm"),
        base_url_env="TPA_EMBEDDINGS_MM_BASE_URL",
        default_base_url="http://tpa-embeddings-mm:8080",
        ready_path="/health",
        gpu_exclusive=True,
    ),
    "reranker": RoleSpec(
        role="reranker",
        compose_service=os.environ.get("TPA_RERANKER_COMPOSE_SERVICE", "tpa-reranker"),
        base_url_env="TPA_RERANKER_BASE_URL",
        default_base_url="http://tpa-reranker:8080",
        ready_path="/health",
        gpu_exclusive=True,
    ),
    "sam2": RoleSpec(
        role="sam2",
        compose_service=os.environ.get("TPA_SAM2_COMPOSE_SERVICE", "tpa-sam2-segmentation"),
        base_url_env="TPA_SAM2_BASE_URL",
        default_base_url="http://tpa-sam2-segmentation:8088",
        ready_path="/healthz",
        gpu_exclusive=True,
    ),
}

GPU_EXCLUSIVE_ROLES: set[Role] = {r for r, spec in ROLE_SPECS.items() if spec.gpu_exclusive}


class EnsureRequest(BaseModel):
    role: Role


class EnsureResponse(BaseModel):
    role: Role
    base_url: str
    status: Literal["ready"]
    stopped_roles: list[Role] = []


class StopRequest(BaseModel):
    role: Role


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _auth_or_401(request: Request) -> None:
    token = os.environ.get("TPA_MODEL_SUPERVISOR_TOKEN")
    if not token:
        return
    provided = request.headers.get("x-tpa-model-supervisor-token")
    if provided != token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _docker_client() -> docker.DockerClient:
    try:
        return docker.from_env()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Docker Engine unavailable: {exc}") from exc


def _compose_filters_for_service(*, service: str) -> dict[str, Any]:
    labels = [f"com.docker.compose.service={service}"]
    project = os.environ.get("TPA_COMPOSE_PROJECT")
    if project:
        labels.append(f"com.docker.compose.project={project}")
    return {"label": labels}


def _find_compose_container(*, client: docker.DockerClient, service: str) -> docker.models.containers.Container | None:
    containers = client.containers.list(all=True, filters=_compose_filters_for_service(service=service))
    if not containers:
        return None
    # Prefer the newest (in case old stopped containers still exist).
    containers.sort(key=lambda c: c.attrs.get("Created", ""), reverse=True)
    return containers[0]


def _container_running(container: docker.models.containers.Container) -> bool:
    container.reload()
    state = container.attrs.get("State") or {}
    return state.get("Status") == "running"


def _container_start(container: docker.models.containers.Container) -> None:
    if _container_running(container):
        return
    container.start()


def _container_stop(container: docker.models.containers.Container, *, timeout_seconds: int) -> None:
    if not _container_running(container):
        return
    container.stop(timeout=timeout_seconds)


def _wait_http_ready(*, url: str, timeout_seconds: float) -> None:
    deadline = time.time() + max(timeout_seconds, 1.0)
    last_err: str | None = None
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(url)
                # Any response means the process is up; treat 5xx as not-ready.
                if resp.status_code < 500:
                    return
                last_err = f"{resp.status_code} {resp.text[:200]}"
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
        time.sleep(0.5)
    raise HTTPException(status_code=504, detail=f"Timed out waiting for model role to be ready: {last_err}")


def _role_base_url(spec: RoleSpec) -> str:
    return (os.environ.get(spec.base_url_env) or spec.default_base_url).rstrip("/")


def _role_ready_url(spec: RoleSpec) -> str:
    base = _role_base_url(spec)
    return base + spec.ready_path


def _missing_container_error(service: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=(
            f"Compose container for service '{service}' not found. "
            "Create model containers once with: "
            "`docker compose -f docker/compose.oss.yml --profile models create "
            "tpa-llm tpa-vlm tpa-embeddings tpa-embeddings-mm tpa-reranker tpa-sam2-segmentation`."
        ),
    )


app = FastAPI(title="TPA Model Supervisor", version="0.1.0")

_AUTO_STOP_GPU_PEER = _bool_env("TPA_MODEL_SUPERVISOR_ENFORCE_GPU_EXCLUSIVITY", True)
_STOP_TIMEOUT_SECONDS = int(os.environ.get("TPA_MODEL_SUPERVISOR_STOP_TIMEOUT_SECONDS", "30"))
_READY_TIMEOUT_SECONDS = float(os.environ.get("TPA_MODEL_SUPERVISOR_READY_TIMEOUT_SECONDS", "180"))


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict[str, Any]:
    client = _docker_client()
    out: dict[str, Any] = {"roles": {}}
    for role, spec in ROLE_SPECS.items():
        container = _find_compose_container(client=client, service=spec.compose_service)
        if not container:
            out["roles"][role] = {"present": False, "compose_service": spec.compose_service}
            continue
        container.reload()
        state = container.attrs.get("State") or {}
        out["roles"][role] = {
            "present": True,
            "compose_service": spec.compose_service,
            "container_name": container.name,
            "status": state.get("Status"),
        }
    return out


@app.post("/ensure", response_model=EnsureResponse)
def ensure(req: EnsureRequest, request: Request) -> EnsureResponse:
    _auth_or_401(request)
    spec = ROLE_SPECS.get(req.role)
    if not spec:
        raise HTTPException(status_code=400, detail="Unknown role")

    client = _docker_client()
    stopped: list[Role] = []

    if _AUTO_STOP_GPU_PEER and spec.gpu_exclusive:
        for other_role in GPU_EXCLUSIVE_ROLES:
            if other_role == req.role:
                continue
            other_spec = ROLE_SPECS[other_role]
            other_container = _find_compose_container(client=client, service=other_spec.compose_service)
            if not other_container:
                continue
            if _container_running(other_container):
                _container_stop(other_container, timeout_seconds=_STOP_TIMEOUT_SECONDS)
                stopped.append(other_role)

    container = _find_compose_container(client=client, service=spec.compose_service)
    if not container:
        raise _missing_container_error(spec.compose_service)

    _container_start(container)

    ready_url = _role_ready_url(spec)
    _wait_http_ready(url=ready_url, timeout_seconds=_READY_TIMEOUT_SECONDS)

    return EnsureResponse(role=req.role, base_url=_role_base_url(spec), status="ready", stopped_roles=stopped)


@app.post("/stop")
def stop(req: StopRequest, request: Request) -> dict[str, Any]:
    _auth_or_401(request)
    spec = ROLE_SPECS.get(req.role)
    if not spec:
        raise HTTPException(status_code=400, detail="Unknown role")

    client = _docker_client()
    container = _find_compose_container(client=client, service=spec.compose_service)
    if not container:
        raise _missing_container_error(spec.compose_service)

    _container_stop(container, timeout_seconds=_STOP_TIMEOUT_SECONDS)
    return {"role": req.role, "stopped": True}
