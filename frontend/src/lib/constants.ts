import type { Instrument, ModelOption } from "./types";

export const PERIODS = [
  { multiplier: 1, timespan: "minute", text: "1m", granularity: "M1" },
  { multiplier: 5, timespan: "minute", text: "5m", granularity: "M5" },
  { multiplier: 15, timespan: "minute", text: "15m", granularity: "M15" },
  { multiplier: 30, timespan: "minute", text: "30m", granularity: "M30" },
  { multiplier: 1, timespan: "hour", text: "1H", granularity: "H1" },
  { multiplier: 4, timespan: "hour", text: "4H", granularity: "H4" },
  { multiplier: 1, timespan: "day", text: "1D", granularity: "D" },
] as const;

export const DEFAULT_INSTRUMENTS: Instrument[] = [
  { ticker: "XAU_USD", symbol: "XAU_USD", display: "XAU/USD", name: "Gold", pricePrecision: 2, pip: 0.1 },
  { ticker: "EUR_USD", symbol: "EUR_USD", display: "EUR/USD", name: "Euro", pricePrecision: 5, pip: 0.0001 },
  { ticker: "GBP_JPY", symbol: "GBP_JPY", display: "GBP/JPY", name: "Cable Yen", pricePrecision: 3, pip: 0.01 },
  { ticker: "GBP_USD", symbol: "GBP_USD", display: "GBP/USD", name: "Sterling", pricePrecision: 5, pip: 0.0001 },
  { ticker: "USD_JPY", symbol: "USD_JPY", display: "USD/JPY", name: "Dollar Yen", pricePrecision: 3, pip: 0.01 },
  { ticker: "AUD_USD", symbol: "AUD_USD", display: "AUD/USD", name: "Aussie", pricePrecision: 5, pip: 0.0001 },
  { ticker: "USD_CAD", symbol: "USD_CAD", display: "USD/CAD", name: "Loonie", pricePrecision: 5, pip: 0.0001 },
  { ticker: "EUR_JPY", symbol: "EUR_JPY", display: "EUR/JPY", name: "Euro Yen", pricePrecision: 3, pip: 0.01 },
];

export const MODELS: ModelOption[] = [
  { id: "claude-sonnet-4-5", label: "Claude Sonnet 4.5", badge: "Default" },
  { id: "claude-3-7-sonnet-latest", label: "Claude 3.7 Sonnet", badge: "Vision" },
  { id: "claude-3-5-sonnet-latest", label: "Claude 3.5 Sonnet", badge: "Stable" },
  { id: "claude-3-5-haiku-latest", label: "Claude 3.5 Haiku", badge: "Fast" },
  { id: "claude-opus-4-5", label: "Claude Opus 4.5", badge: "Max" },
];

export const QUICK_PROMPTS = [
  { id: "liquidity15m" as const, prompt: "Analyze 15m liquidity pools, session highs/lows, and any sweep. Map FVG and give a setup if R:R >= 1:2." },
  { id: "fvgScan" as const, prompt: "/scan" },
  { id: "setup" as const, prompt: "Generate a complete ICT trade setup with entry, SL, TP1, TP2 and klineOverlays for the current pair." },
];

export const SLASH_COMMANDS = [
  { cmd: "/scan", hintKey: "slash.scan" as const },
  { cmd: "/timeframe", hintKey: "slash.timeframe" as const },
  { cmd: "/model", hintKey: "slash.model" as const },
  { cmd: "/pair", hintKey: "slash.pair" as const },
  { cmd: "/overlay", hintKey: "slash.overlay" as const },
  { cmd: "/setup", hintKey: "slash.setup" as const },
];

export function displaySymbol(ticker: string) {
  return ticker.replace("_", "/");
}

export function parsePairShortcut(raw: string) {
  const compact = raw.replace(/[\/\s-]/g, "").toUpperCase();
  const known = DEFAULT_INSTRUMENTS.find(
    (i) => i.ticker.replace("_", "") === compact || i.ticker === compact || i.display.replace("/", "") === compact
  );
  return known?.ticker;
}
