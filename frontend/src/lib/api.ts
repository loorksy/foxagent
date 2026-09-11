import type {
  AgentSession,
  Instrument,
  KLineBar,
  MemoryEntry,
  ModelOption,
  SettingsPayload,
  SettingsPublic,
  StructureScan,
  TradeRecommendation,
} from "./types";

const API = "";

function redirectToLogin() {
  if (typeof window === "undefined") return;
  if (window.location.pathname.startsWith("/login")) return;
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.href = `/login?next=${next}`;
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (res.status === 401) {
    redirectToLogin();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  login: (password: string) => http<{ ok: boolean }>("/api/auth/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => http<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  me: () => http<{ ok: boolean; operator?: boolean }>("/api/auth/me"),
  health: () =>
    http<{
      ok: boolean;
      dataMode: string;
      anthropic: boolean;
      anthropicConfigured?: boolean;
      anthropicKeyValid?: boolean;
      anthropicReady?: boolean;
      anthropicDetail?: string;
    }>("/api/health"),
  candles: (instrument: string, granularity: string, count = 400) =>
    http<{ candles: KLineBar[] }>(`/api/candles?instrument=${instrument}&granularity=${granularity}&count=${count}`),
  instruments: () => http<{ instruments: Instrument[] }>("/api/instruments"),
  models: () => http<{ models: ModelOption[] }>("/api/models"),
  structure: (instrument: string, granularity: string, count = 300) =>
    http<StructureScan>(`/api/structure?instrument=${instrument}&granularity=${granularity}&count=${count}`),
  memory: (symbol?: string) =>
    http<{ entries: MemoryEntry[] }>(`/api/memory${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ""}`),
  memoryContext: (symbol: string, query = "") =>
    http<{ symbol: string; context: string }>(
      `/api/memory/context?symbol=${encodeURIComponent(symbol)}&query=${encodeURIComponent(query)}`
    ),
  recommendations: () => http<{ recommendations: TradeRecommendation[] }>("/api/recommendations"),
  settings: () => http<SettingsPublic>("/api/settings"),
  saveSettings: (body: SettingsPayload) =>
    http<SettingsPublic>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  validateSettings: (body: Record<string, unknown>) =>
    http<{
      ok: boolean;
      detail: string;
      keyValid?: boolean;
      connected?: boolean;
      configured?: boolean;
      balance?: number | null;
      currency?: string;
    }>(
      "/api/settings/validate",
      { method: "POST", body: JSON.stringify(body) }
    ),
  mt5Status: () =>
    http<{
      connected: boolean;
      configured?: boolean;
      state?: string;
      accountName?: string;
      balance?: number | null;
      equity?: number | null;
      currency?: string;
      detail?: string;
    }>("/api/mt5/status"),
  prices: () => http<{ prices: import("./types").LivePrice[] }>("/api/prices"),
  sessions: () => http<{ sessions: AgentSession[] }>("/api/sessions"),
  createSession: (body?: { id?: string; symbol?: string; timeframe?: string; title?: string }) =>
    http<AgentSession>("/api/sessions", { method: "POST", body: JSON.stringify(body || {}) }),
  getSession: (id: string) => http<AgentSession>(`/api/sessions/${id}`),
  saveSession: (id: string, body: Partial<AgentSession>) =>
    http<AgentSession>(`/api/sessions/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteSession: (id: string) => http<{ ok: boolean }>(`/api/sessions/${id}`, { method: "DELETE" }),
  patchRecommendation: (id: string, patch: Record<string, unknown>) =>
    http<TradeRecommendation>(`/api/recommendations/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  cancelRun: (runId: string) =>
    http<{ ok: boolean; cancelled?: boolean }>("/api/agent/chat/stream/cancel", {
      method: "POST",
      body: JSON.stringify({ runId }),
    }),
  systemStatus: () => http<{ paused: boolean }>("/api/system/status"),
  pauseSystem: () => http<{ paused: boolean }>("/api/system/pause", { method: "POST" }),
  resumeSystem: () => http<{ paused: boolean }>("/api/system/resume", { method: "POST" }),
  economicCalendar: (hoursAhead = 24, minImpact = "medium") =>
    http<{ events: import("./types").EconomicEvent[]; source: string; cached: boolean; warning?: string }>(
      `/api/economic-calendar?hours_ahead=${hoursAhead}&min_impact=${minImpact}`
    ),
  economicCalendarUpcoming: () =>
    http<{ events: import("./types").EconomicEvent[]; source: string }>(`/api/economic-calendar/upcoming`),
  inbox: (tab?: string) =>
    http<import("./types").InboxSnapshot>(tab ? `/api/inbox?tab=${encodeURIComponent(tab)}` : "/api/inbox"),
  inboxSummary: () =>
    http<{ openCount: number; counts: import("./types").InboxCounts; desk: import("./types").DeskStatus }>(
      "/api/inbox/summary"
    ),
  inboxItem: (id: string) => http<import("./types").InboxItem>(`/api/inbox/${encodeURIComponent(id)}`),
  ackInbox: (id: string) => http<{ ok: boolean }>(`/api/inbox/${encodeURIComponent(id)}/ack`, { method: "POST" }),
  approveInbox: (id: string) =>
    http<{ ok: boolean; recommendation?: import("./types").TradeRecommendation }>(
      `/api/approvals/${encodeURIComponent(id)}/approve`,
      { method: "POST" }
    ),
  rejectInbox: (id: string, reason: string) =>
    http<{ ok: boolean; signal?: import("./types").BotSignal }>(`/api/approvals/${encodeURIComponent(id)}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  botPreflight: () => http<import("./types").PreflightReport>("/api/bot/preflight"),
  botStatus: () => http<import("./types").BotStatus>("/api/bot/status"),
  botStart: (force = false) =>
    http<import("./types").BotStatus & { preflight?: import("./types").PreflightReport }>(
      force ? "/api/bot/start?force=true" : "/api/bot/start",
      { method: "POST" }
    ),
  botStop: () => http<import("./types").BotStatus>("/api/bot/stop", { method: "POST" }),
  botSignals: () => http<{ signals: import("./types").BotSignal[] }>("/api/bot/signals"),
  botSignal: (id: string) => http<import("./types").BotSignal>(`/api/bot/signals/${id}`),
  patchBotSignal: (id: string, patch: Record<string, unknown>) =>
    http<import("./types").BotSignal>(`/api/bot/signals/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  promoteBotSignal: (id: string) =>
    http<{ ok: boolean; recommendation?: import("./types").TradeRecommendation }>(
      `/api/bot/signals/${id}/to-recommendation`,
      { method: "POST" }
    ),
  botPerformance: (agent?: string) =>
    http<{ performance: import("./types").StrategyPerf[] }>(
      agent ? `/api/bot/performance/${agent}` : "/api/bot/performance"
    ),
  runBacktest: (body: {
    timeframe: string;
    strategyId: string | null;
    days: number;
    riskPercent?: number;
    minRr?: number;
  }) =>
    http<import("./types").BacktestReport>("/api/backtest/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  backtestReports: () => http<{ reports: import("./types").BacktestReport[] }>("/api/backtest/reports"),
  backtestReport: (id: string) => http<import("./types").BacktestReport>(`/api/backtest/reports/${id}`),
  strategies: (status?: string) =>
    http<{ strategies: import("./types").StrategyRule[] }>(
      status ? `/api/strategies?status=${encodeURIComponent(status)}` : "/api/strategies"
    ),
  strategiesProposed: () => http<{ strategies: import("./types").StrategyRule[] }>("/api/strategies/proposed"),
  strategy: (id: string) => http<import("./types").StrategyRule>(`/api/strategies/${id}`),
  createStrategy: (body: Record<string, unknown>) =>
    http<{ ok: boolean; strategy?: import("./types").StrategyRule; detail?: string }>("/api/strategies", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  patchStrategy: (id: string, body: Record<string, unknown>) =>
    http<{ ok: boolean; strategy?: import("./types").StrategyRule; detail?: string }>(`/api/strategies/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteStrategy: (id: string) => http<{ ok: boolean; deleted?: string }>(`/api/strategies/${id}`, { method: "DELETE" }),
  lintStrategyCode: (code: string) =>
    http<{ ok: boolean; error?: string | null }>("/api/strategies/lint-code", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  validateStrategy: (id: string, body?: Record<string, unknown>) =>
    http<import("./types").StrategyValidation>(`/api/strategies/${id}/validate`, {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  approveStrategy: (id: string) =>
    http<{ ok: boolean; strategy?: import("./types").StrategyRule }>(`/api/strategies/${id}/approve`, { method: "POST" }),
  rejectStrategy: (id: string, reason = "") =>
    http<{ ok: boolean; strategy?: import("./types").StrategyRule }>(`/api/strategies/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  pinStrategy: (id: string) => http<{ ok: boolean; strategy?: import("./types").StrategyRule }>(`/api/strategies/${id}/pin`, { method: "POST" }),
  unpinStrategy: (id: string) =>
    http<{ ok: boolean; strategy?: import("./types").StrategyRule }>(`/api/strategies/${id}/unpin`, { method: "POST" }),
  botsRoom: () => http<Record<string, unknown>>("/api/bots"),
  botsNews: () => http<{ open: boolean; windows: Array<Record<string, unknown>> }>("/api/bots/news"),
  botScans: () => http<{ scans: Array<Record<string, unknown>> }>("/api/bot/scans"),
  botScan: (id: string) => http<Record<string, unknown>>(`/api/bot/scans/${id}`),
  haltStrategy: (id: string, reason = "") =>
    http<{ ok: boolean }>(`/api/bot/strategies/${id}/halt`, { method: "POST", body: JSON.stringify({ reason }) }),
  labLeaderboard: () => http<{ leaderboard: Array<Record<string, unknown>> }>("/api/lab/leaderboard"),
  labJobs: () => http<{ jobs: Array<Record<string, unknown>> }>("/api/lab/jobs"),
  labJob: (id: string) => http<Record<string, unknown>>(`/api/lab/jobs/${id}`),
  startExperiment: (body: Record<string, unknown>) =>
    http<{ ok: boolean; job?: Record<string, unknown> }>("/api/lab/experiments", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  briefing: () => http<Record<string, unknown>>("/api/briefing"),
  journal: () => http<{ entries: Array<Record<string, unknown>> }>("/api/journal"),
  postmortem: (id: string, body: Record<string, unknown>) =>
    http<{ ok: boolean }>(`/api/recommendations/${id}/postmortem`, { method: "PATCH", body: JSON.stringify(body) }),
  streamChat: async (
    body: { message: string; symbol: string; timeframe: string; model: string; sessionId?: string },
    onEvent: (event: { type: string; payload: Record<string, unknown> }) => void,
    signal?: AbortSignal
  ) => {
    const res = await fetch("/api/agent/chat/stream", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    if (res.status === 401) {
      redirectToLogin();
      throw new Error("Unauthorized");
    }
    if (!res.ok || !res.body) {
      throw new Error(await res.text());
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const chunks = buf.split("\n\n");
      buf = chunks.pop() || "";
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        try {
          onEvent(JSON.parse(line.slice(5).trim()));
        } catch {
          /* ignore malformed */
        }
      }
    }
  },
};

export function wsUrl(path: string) {
  if (typeof window === "undefined") return path;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const explicit = process.env.NEXT_PUBLIC_WS_URL;
  if (explicit) return `${explicit}${path}`;
  if (process.env.NEXT_PUBLIC_WS_SAME_ORIGIN === "1") {
    return `${proto}//${window.location.host}${path}`;
  }
  return `${proto}//${window.location.hostname}:8000${path}`;
}
