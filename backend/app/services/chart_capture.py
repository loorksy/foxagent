from __future__ import annotations

import base64
import io
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from app.schemas import OHLCV, KlineOverlay

FIB_RATIOS = (0.0, 0.5, 0.618, 0.786, 1.0)


def _mpl_color(value: str | None, fallback: str | tuple):
    if not value:
        return fallback
    if value.startswith("rgba"):
        try:
            inner = value[value.find("(") + 1 : value.find(")")]
            parts = [float(x.strip()) for x in inner.split(",")]
            r, g, b, a = parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else 1
            return (r / 255.0, g / 255.0, b / 255.0, a)
        except Exception:
            return fallback
    return value


def _x_for_ts(ts: int, shown: list[OHLCV], ts_to_x: dict[int, int]) -> float | None:
    if ts in ts_to_x:
        return float(ts_to_x[ts])
    if not shown:
        return None
    nearest = min(shown, key=lambda c: abs(c.timestamp - ts))
    return float(ts_to_x[nearest.timestamp])


def _styles(ov: KlineOverlay) -> dict:
    return ov.styles if isinstance(ov.styles, dict) else ov.styles.model_dump()


def _label(ov: KlineOverlay) -> str:
    if ov.annotationText:
        return str(ov.annotationText)
    if ov.extendData and isinstance(ov.extendData, str):
        return ov.extendData
    return ""


def render_candles_png(
    candles: list[OHLCV],
    title: str,
    overlays: Iterable[KlineOverlay] | None = None,
    width: int = 1280,
    height: int = 720,
) -> bytes:
    if not candles:
        raise ValueError("No candles to render")

    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_facecolor("#070b12")
    ax.set_facecolor("#070b12")

    shown = candles[-180:]
    ts_to_x = {c.timestamp: i for i, c in enumerate(shown)}
    for i, c in enumerate(shown):
        color = "#22c55e" if c.close >= c.open else "#ef4444"
        ax.vlines(i, c.low, c.high, color=color, linewidth=0.8, zorder=2)
        body_low = min(c.open, c.close)
        body_h = max(abs(c.close - c.open), (c.high - c.low) * 0.04)
        ax.add_patch(
            Rectangle(
                (i - 0.32, body_low),
                0.64,
                body_h,
                facecolor=color,
                edgecolor=color,
                linewidth=0.4,
                zorder=3,
            )
        )

    if overlays:
        for ov in overlays:
            pts = ov.points
            if not pts:
                continue
            xs_ov = [_x_for_ts(p.timestamp, shown, ts_to_x) for p in pts]
            if any(x is None for x in xs_ov):
                continue
            styles = _styles(ov)
            name = ov.name
            label = _label(ov)

            if name == "rect" and len(pts) >= 2:
                x0, x1 = float(xs_ov[0]), float(xs_ov[1])
                y0, y1 = pts[0].value, pts[1].value
                ax.add_patch(
                    Rectangle(
                        (min(x0, x1), min(y0, y1)),
                        max(abs(x1 - x0), 1),
                        max(abs(y1 - y0), 1e-8),
                        facecolor=_mpl_color(styles.get("fillColor"), (0.13, 0.77, 0.37, 0.28)),
                        edgecolor=_mpl_color(styles.get("borderColor"), "#22c55e"),
                        linewidth=1,
                        alpha=0.9,
                        zorder=1,
                    )
                )
                if label:
                    ax.text(
                        min(x0, x1) + 0.4,
                        max(y0, y1),
                        label,
                        color=styles.get("borderColor") or "#86efac",
                        fontsize=8,
                        va="bottom",
                        zorder=5,
                    )
            elif name in {"trendLine", "segment", "rayLine"} and len(pts) >= 2:
                ax.plot(
                    xs_ov,
                    [p.value for p in pts],
                    color=styles.get("lineColor") or "#eab308",
                    linewidth=styles.get("lineWidth") or 1.5,
                    zorder=4,
                )
                if label:
                    ax.text(
                        xs_ov[-1],
                        pts[-1].value,
                        label,
                        color=styles.get("lineColor") or "#eab308",
                        fontsize=7.5,
                        va="bottom",
                        zorder=5,
                    )
            elif name in {"fibonacci", "fibonacciLine"} and len(pts) >= 2:
                y0, y1 = pts[0].value, pts[1].value
                x0, x1 = float(xs_ov[0]), float(xs_ov[1])
                left, right = min(x0, x1), max(x0, x1, len(shown) - 1)
                for ratio in FIB_RATIOS:
                    y = y0 + (y1 - y0) * ratio
                    ax.hlines(y, left, right, colors="#60a5fa", linewidth=0.7, linestyles="--", zorder=4)
                    ax.text(right + 0.3, y, f"{ratio:.3g}", color="#93c5fd", fontsize=7, va="center", zorder=5)
            elif name in {"priceLine", "horizontalStraightLine"}:
                color = styles.get("lineColor") or styles.get("color") or "#f8fafc"
                ax.axhline(pts[0].value, color=color, linewidth=0.9, linestyle="--", zorder=4)
                if label:
                    ax.text(
                        len(shown) + 0.2,
                        pts[0].value,
                        f"{label} {pts[0].value:g}",
                        color=color,
                        fontsize=8,
                        va="center",
                        zorder=5,
                    )
            elif name in {"textAnnotation", "simpleAnnotation"}:
                text = label or "Note"
                ax.annotate(
                    text,
                    xy=(float(xs_ov[0]), pts[0].value),
                    xytext=(8, 8),
                    textcoords="offset points",
                    color=styles.get("textColor") or styles.get("color") or "#fbbf24",
                    fontsize=8,
                    bbox={"boxstyle": "round,pad=0.25", "fc": "#111827", "ec": "#fbbf24", "alpha": 0.85},
                    zorder=6,
                )

    ax.set_title(title, color="#e2e8f0", fontsize=13, pad=10, loc="left")
    ax.tick_params(colors="#64748b", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#1e293b")
    ax.grid(color="#132033", linestyle="-", linewidth=0.4)
    ax.set_xlim(-1, len(shown) + 8)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def render_candles_b64(
    candles: list[OHLCV],
    title: str,
    overlays: Iterable[KlineOverlay] | None = None,
) -> str:
    png = render_candles_png(candles, title, overlays)
    return base64.b64encode(png).decode("ascii")
