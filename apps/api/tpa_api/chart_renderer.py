from __future__ import annotations

from typing import Any


def _normalize_series(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in series:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        value = item.get("value")
        if not isinstance(label, str):
            continue
        try:
            numeric = float(value)
        except Exception:  # noqa: BLE001
            continue
        out.append({"label": label, "value": numeric})
    return out


def render_bar_chart_svg(spec: dict[str, Any]) -> str:
    title = spec.get("title") if isinstance(spec.get("title"), str) else "Chart"
    series = _normalize_series(spec.get("series") if isinstance(spec.get("series"), list) else [])
    width = int(spec.get("width") or 640)
    height = int(spec.get("height") or 360)
    width = max(320, min(width, 1200))
    height = max(240, min(height, 900))
    margin = 48
    chart_width = width - margin * 2
    chart_height = height - margin * 2
    max_val = max([s["value"] for s in series], default=1.0) or 1.0
    bar_count = max(len(series), 1)
    bar_width = chart_width / bar_count

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{margin}" y="{margin - 16}" font-family="Arial" font-size="14" fill="#1f2937">{title}</text>',
        f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#cbd5f5" stroke-width="1"/>',
    ]

    palette = ["#3b82f6", "#0ea5e9", "#14b8a6", "#22c55e", "#f59e0b", "#f97316"]
    for idx, item in enumerate(series):
        bar_height = (item["value"] / max_val) * chart_height if max_val else 0
        x = margin + idx * bar_width + (bar_width * 0.1)
        y = height - margin - bar_height
        w = bar_width * 0.8
        color = palette[idx % len(palette)]
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{bar_height:.1f}" fill="{color}"/>')
        parts.append(
            f'<text x="{x + w / 2:.1f}" y="{height - margin + 16}" text-anchor="middle" '
            f'font-family="Arial" font-size="10" fill="#475569">{item["label"]}</text>'
        )
        parts.append(
            f'<text x="{x + w / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle" '
            f'font-family="Arial" font-size="10" fill="#475569">{item["value"]:.0f}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def render_chart_svg(spec: dict[str, Any]) -> str:
    chart_type = spec.get("chart_type") if isinstance(spec.get("chart_type"), str) else "bar"
    if chart_type != "bar":
        chart_type = "bar"
    return render_bar_chart_svg(spec)
