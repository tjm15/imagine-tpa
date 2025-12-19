from __future__ import annotations


def _vector_literal(vec: list[float]) -> str:
    cleaned = [float(x) for x in vec if isinstance(x, (int, float))]
    return "[" + ",".join(f"{x:.8f}" for x in cleaned) + "]"

