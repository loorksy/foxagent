from __future__ import annotations

import base64
import io
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from app.schemas import OHLCV, KlineOverlay


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

    xs = list(range(len(candles)))
    for i, c in enumerate(candles[-180:]):
        x = i
        color = "#22c55e" if c.close >= c.open else "#ef4444"
        ax.vlines(x, c.low, c.high, color=color, linewidth=0.8, zorder=2)
        body_low = min(c.open, c.close)
        body_h = max(abs(c.close - c.open), (c.high - c.low) * 0.04)
        ax.add_patch(
            Rectangle(
                (x - 0.32, body_low),
                0.64,
                body_h,
                facecolor=color,
                edgecolor=color,
                linewidth=0.4,
                zorder=3,
            )
        )

    shown = candles[-180:]
    ts_to_x = {c.timestamp: i for i, c in enumerate(shown)}

    if overlays:
        for ov in overlays:
            pts = ov.points
            if not pts:
                continue
            xs_ov = [ts_to_x.get(p.timestamp) for p in pts]
            if any(x is None for x in xs_ov):
                continue
            styles = ov.styles if isinstance(ov.styles, dict) else ov.styles.model_dump()
            if ov.name in {"rect"} and len(pts) >= 2:
                x0, x1 = xs_ov[0], xs_ov[1]
                y0, y1 = pts[0].value, pts[1].value
                ax.add_patch(
                    Rectangle(
                        (min(x0, x1), min(y0, y1)),
                        abs(x1 - x0) or 1,
                        abs(y1 - y0) or 1,
                        facecolor=_mpl_color(styles.get("fillColor"), (0.13, 0.77, 0.37, 0.28)),
                        edgecolor=_mpl_color(styles.get("borderColor"), "#22c55e"),
                        linewidth=1,
                        alpha=0.9,
                        zorder=1,
                    )
                )
            elif ov.name in {"trendLine", "segment"} and len(pts) >= 2:
                ax.plot(
                    xs_ov,
                    [p.value for p in pts],
                    color=styles.get("lineColor") or "#eab308",
                    linewidth=styles.get("lineWidth") or 1.5,
                    zorder=4,
                )
            elif ov.name == "priceLine":
                ax.axhline(
                    pts[0].value,
                    color=styles.get("lineColor") or "#f8fafc",
                    linewidth=0.8,
                    linestyle="--",
                    zorder=4,
                )

    ax.set_title(title, color="#e2e8f0", fontsize=13, pad=10, loc="left")
    ax.tick_params(colors="#64748b", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#1e293b")
    ax.grid(color="#132033", linestyle="-", linewidth=0.4)
    ax.set_xlim(-1, len(shown))
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def render_candles_b64(candles: list[OHLCV], title: str, overlays: Iterable[KlineOverlay] | None = None) -> str:
    png = render_candles_png(candles, title, overlays)
    return base64.b64encode(png).decode("ascii")
