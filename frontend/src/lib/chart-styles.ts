export const DARK_CHART_STYLES = {
  grid: {
    show: true,
    horizontal: { show: true, color: "#152033", size: 1, style: "solid" },
    vertical: { show: true, color: "#152033", size: 1, style: "solid" },
  },
  candle: {
    type: "candle_solid",
    bar: {
      upColor: "#22c55e",
      downColor: "#ef4444",
      noChangeColor: "#64748b",
      upBorderColor: "#22c55e",
      downBorderColor: "#ef4444",
      noChangeBorderColor: "#64748b",
      upWickColor: "#22c55e",
      downWickColor: "#ef4444",
      noChangeWickColor: "#64748b",
    },
    tooltip: {
      showRule: "always",
      showType: "standard",
      text: { color: "#94a3b8", size: 12 },
    },
    priceMark: {
      show: true,
      high: { show: true, color: "#94a3b8", textSize: 10 },
      low: { show: true, color: "#94a3b8", textSize: 10 },
      last: {
        show: true,
        upColor: "#22c55e",
        downColor: "#ef4444",
        noChangeColor: "#e8c872",
        line: { show: true, style: "dashed" },
        text: { color: "#05070b" },
      },
    },
  },
  indicator: {
    ohlc: {
      upColor: "#22c55e",
      downColor: "#ef4444",
      noChangeColor: "#64748b",
    },
    bars: [
      { upColor: "rgba(34,197,94,0.55)", downColor: "rgba(239,68,68,0.55)", noChangeColor: "#64748b" },
    ],
    lines: [
      { color: "#e8c872" },
      { color: "#22d3ee" },
      { color: "#a78bfa" },
      { color: "#f97316" },
    ],
    tooltip: { text: { color: "#94a3b8" } },
  },
  xAxis: {
    axisLine: { color: "#1e293b" },
    tickLine: { color: "#1e293b" },
    tickText: { color: "#7c8ca8", size: 11 },
  },
  yAxis: {
    axisLine: { color: "#1e293b" },
    tickLine: { color: "#1e293b" },
    tickText: { color: "#7c8ca8", size: 11 },
  },
  separator: { color: "#1e293b" },
  crosshair: {
    show: true,
    horizontal: {
      line: { color: "#475569", style: "dashed" },
      text: { backgroundColor: "#c8a35a", color: "#05070b" },
    },
    vertical: {
      line: { color: "#475569", style: "dashed" },
      text: { backgroundColor: "#1e293b", color: "#e2e8f0" },
    },
  },
  overlay: {
    point: { color: "#e8c872", borderColor: "#e8c872" },
    line: { color: "#e8c872" },
    text: { color: "#e8c872" },
    rect: { color: "rgba(34,197,94,0.15)", borderColor: "#22c55e" },
  },
};
