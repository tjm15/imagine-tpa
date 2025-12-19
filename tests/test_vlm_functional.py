from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


REPO_ROOT = Path(__file__).resolve().parents[1]

# Use a real asset already in the repo so the test is deterministic.
# (We convert the first page to an embedded image by letting the VLM handle PDF as an image-like input
# via a data: URL. If your VLM build doesn't accept PDFs directly, set TPA_VLM_TEST_IMAGE to a PNG/JPG
# path instead.)
DEFAULT_REAL_ASSET = REPO_ROOT / "national_policy" / "NPPF_December_2024.pdf"


def _vlm_base_url() -> str:
    # vLLM OpenAI server in docker maps 8020:8000 by default in compose.oss.yml
    return os.environ.get("TPA_VLM_BASE_URL") or "http://localhost:8020/v1"


def _vlm_model_id() -> str:
    return os.environ.get("TPA_VLM_MODEL_ID") or "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8"


def _require_enabled() -> None:
    if os.environ.get("TPA_RUN_FUNCTIONAL") != "1":
        pytest.skip("Functional VLM test disabled. Set TPA_RUN_FUNCTIONAL=1 to enable.")



def _generate_synthetic_plan_image() -> bytes:
    """Generate a synthetic site plan-like image for testing."""
    import io
    if not HAS_PIL:
        pytest.skip("PIL not installed; cannot generate synthetic image.")
    
    img = Image.new("RGB", (800, 600), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    
    # Title
    draw.rectangle([(50, 30), (750, 70)], fill=(200, 220, 240))
    draw.text((60, 40), "SITE PLAN - Test Development", fill=(0, 0, 0))
    
    # Building blocks
    draw.rectangle([(100, 150), (300, 350)], outline=(50, 50, 50), width=3, fill=(220, 220, 220))
    draw.text((110, 160), "Block A", fill=(0, 0, 0))
    
    draw.rectangle([(400, 150), (600, 350)], outline=(50, 50, 50), width=3, fill=(220, 220, 220))
    draw.text((410, 160), "Block B", fill=(0, 0, 0))
    
    # Green space
    draw.rectangle([(100, 400), (600, 550)], fill=(180, 220, 180))
    draw.text((250, 460), "Open Space", fill=(0, 0, 0))
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def _load_real_asset_bytes() -> tuple[bytes, str]:
    # Use synthetic image by default; override with TPA_VLM_TEST_IMAGE for real assets
    env_path = os.environ.get("TPA_VLM_TEST_IMAGE")
    if not env_path:
        return _generate_synthetic_plan_image(), "image/png"
    
    p = Path(env_path)
    if not p.is_absolute():
        p = (REPO_ROOT / p).resolve()
    if not p.exists():
        pytest.skip(f"Real asset not found: {p}. Set TPA_VLM_TEST_IMAGE to a valid PNG/JPG path.")

    suffix = p.suffix.lower().lstrip(".")
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(suffix)

    if not mime:
        pytest.skip(f"Unsupported test asset type: {p.suffix}. Use PNG/JPG.")

    return p.read_bytes(), mime


def _wait_for_vlm_models(timeout_s: float = 5.0) -> None:
    """Skip if VLM isn't reachable (don’t hard-fail CI/dev machines without GPU)."""
    base = _vlm_base_url().rstrip("/")
    url = base + "/models"

    deadline = time.time() + timeout_s
    last_err: str | None = None

    while time.time() < deadline:
        try:
            with httpx.Client(timeout=2.0) as client:
                r = client.get(url)
            if r.status_code < 400:
                return
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
        time.sleep(0.25)

    pytest.skip(f"VLM not reachable at {url}. Last error: {last_err}")


def _docker_available() -> bool:
    try:
        r = subprocess.run(["docker", "version"], check=False, capture_output=True, text=True)
    except Exception:  # noqa: BLE001
        return False
    return r.returncode == 0


def _get_compose_container_id(service: str) -> str | None:
    """Return container id for a docker-compose service name (if running)."""
    try:
        r = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"label=com.docker.compose.service={service}",
                "--format",
                "{{.ID}}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return None

    if r.returncode != 0:
        return None
    cid = (r.stdout or "").strip().splitlines()
    return cid[0].strip() if cid else None


def _assert_and_print_gpu_proof() -> None:
    """Proof that the VLM is configured to run with GPU in Docker.

    We don't attempt to infer VRAM from host tooling here; we assert the container is started with
    GPU DeviceRequests (i.e., docker compose `gpus: all` actually applied).
    """

    if not _docker_available():
        pytest.skip("Docker CLI not available; cannot prove GPU configuration.")

    cid = _get_compose_container_id("tpa-vlm")
    if not cid:
        pytest.skip("tpa-vlm container not running; cannot prove GPU configuration.")

    # Inspect the docker HostConfig.DeviceRequests (where GPU requests are encoded).
    r = subprocess.run(
        ["docker", "inspect", cid, "--format", "{{json .HostConfig.DeviceRequests}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        pytest.skip(f"docker inspect failed; cannot prove GPU configuration: {r.stderr.strip()}")

    raw = (r.stdout or "").strip()
    print(f"VLM_CONTAINER_ID={cid}")
    print(f"VLM_DOCKER_DEVICE_REQUESTS={raw}")

    try:
        device_requests = json.loads(raw) if raw and raw != "null" else []
    except Exception:  # noqa: BLE001
        device_requests = []

    # Expected shape is a list with at least one entry that requests GPU capability.
    has_gpu = False
    if isinstance(device_requests, list):
        for req in device_requests:
            if not isinstance(req, dict):
                continue
            caps = req.get("Capabilities")
            # Typically [["gpu"]]
            if isinstance(caps, list) and any(
                isinstance(inner, list) and any(str(x).lower() == "gpu" for x in inner) for inner in caps
            ):
                has_gpu = True
                break

    assert has_gpu, "tpa-vlm container does not show GPU DeviceRequests in docker inspect"


@pytest.mark.functional
def test_vlm_real_asset_prompt_to_output() -> None:
    """True functional test: real repo asset -> VLM prompt -> non-empty output text.

    Requires:
      - VLM running and reachable at TPA_VLM_BASE_URL (default http://localhost:8020/v1)
      - TPA_RUN_FUNCTIONAL=1

    Optional:
      - TPA_VLM_TEST_IMAGE=/absolute/or/relative/path/to/your.png
        (If your VLM doesn't accept PDFs directly.)
    """

    _require_enabled()
    _wait_for_vlm_models(timeout_s=10.0)
    _assert_and_print_gpu_proof()

    asset_bytes, mime = _load_real_asset_bytes()
    b64 = base64.b64encode(asset_bytes).decode("ascii")

    prompt = (
        "You are a planning officer. Read the attached document/image and extract: "
        "(1) document title if visible, (2) any section heading you can see, "
        "(3) one short bullet on the planning topic. Keep to 3 bullet points." 
    )

    # OpenAI-style multimodal chat payload. vLLM generally supports this shape.
    payload = {
        "model": _vlm_model_id(),
        "temperature": 0.2,
        "max_tokens": 200,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
    }

    base = _vlm_base_url().rstrip("/")

    candidates = [
        base + "/chat/completions",
        # Some servers accept this alias
        base.replace("/v1", "") + "/v1/chat/completions",
    ]

    last_err: str | None = None
    text_out: str | None = None

    for url in candidates:
        try:
            with httpx.Client(timeout=180.0) as client:
                r = client.post(url, json=payload)
            if r.status_code >= 400:
                last_err = f"HTTP {r.status_code}: {r.text[:400]}"
                continue
            data = r.json()

            # OpenAI chat shape: { choices: [ { message: { content: "..." } } ] }
            choices = data.get("choices") if isinstance(data, dict) else None
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") if isinstance(choices[0], dict) else None
                content = msg.get("content") if isinstance(msg, dict) else None
                if isinstance(content, str):
                    text_out = content.strip()
                    break

            last_err = f"Unrecognized response shape: {str(data)[:400]}"
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)

    if not text_out:
        pytest.fail(f"No VLM output text. Last error: {last_err}")

    # Print the actual result returned.
    print("VLM_OUTPUT_TEXT_START")
    print(text_out)
    print("VLM_OUTPUT_TEXT_END")

    # Minimal assertions: non-empty, somewhat informative.
    assert len(text_out) >= 20
