import type { KlineOverlay } from "./types";

export type ChartLike = {
  createOverlay: (opts: Record<string, unknown>) => string | null;
  removeOverlay: (opts?: Record<string, unknown>) => void;
  getDataList?: () => { timestamp: number }[];
  scrollToDataIndex?: (index: number, animationDuration?: number) => void;
};

const NAME_MAP: Record<string, string> = {
  trendLine: "segment",
  rect: "rect",
  fibonacci: "fibonacciLine",
  fibonacciLine: "fibonacciLine",
  priceLine: "priceLine",
  textAnnotation: "simpleAnnotation",
  simpleAnnotation: "simpleAnnotation",
  segment: "segment",
  rayLine: "rayLine",
  horizontalStraightLine: "horizontalStraightLine",
};

function overlayStyles(name: string, styles: KlineOverlay["styles"] = {}) {
  const lineColor = styles.lineColor || styles.color || "#eab308";
  if (name === "rect") {
    return {
      rect: {
        color: styles.fillColor || "rgba(34,197,94,0.18)",
        borderColor: styles.borderColor || "#22c55e",
        borderSize: 1,
        style: "stroke_fill",
      },
    };
  }
  if (name === "simpleAnnotation") {
    return {
      text: {
        color: styles.textColor || styles.color || "#e8c872",
        size: 12,
        family: "IBM Plex Sans",
        weight: 500,
      },
    };
  }
  if (name === "priceLine") {
    return {
      line: { color: lineColor, size: styles.lineWidth || 1, style: "dashed", dashedValue: [6, 4] },
    };
  }
  return {
    line: { color: lineColor, size: styles.lineWidth || 2 },
  };
}

export function clearOverlays(chart: ChartLike) {
  try {
    chart.removeOverlay();
  } catch {
    /* empty */
  }
}

export async function applyOverlays(
  chart: ChartLike,
  overlays: KlineOverlay[],
  animate = true
) {
  for (let i = 0; i < overlays.length; i += 1) {
    const ov = overlays[i];
    const name = NAME_MAP[ov.name] || ov.name;
    const extend =
      ov.extendData ??
      (name === "simpleAnnotation" ? ov.annotationText : ov.annotationText);
    try {
      chart.createOverlay({
        name,
        id: ov.id || `${ov.groupId || name}_${i}`,
        groupId: ov.groupId || "foxagent",
        lock: ov.lock ?? true,
        visible: ov.visible ?? true,
        zLevel: ov.zLevel ?? i,
        points: ov.points,
        extendData: extend,
        styles: overlayStyles(name, ov.styles),
      });
    } catch {
      /* overlay type may be missing */
    }
    if (animate) {
      await new Promise((r) => setTimeout(r, 140));
    }
  }
}

export function focusTimestamp(chart: ChartLike, timestamp?: number | null) {
  if (!timestamp || !chart.getDataList || !chart.scrollToDataIndex) return;
  const data = chart.getDataList();
  if (!data.length) return;
  let best = 0;
  let dist = Infinity;
  data.forEach((bar, i) => {
    const d = Math.abs(bar.timestamp - timestamp);
    if (d < dist) {
      dist = d;
      best = i;
    }
  });
  chart.scrollToDataIndex(best, 280);
}
