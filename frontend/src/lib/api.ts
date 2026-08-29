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
    http<{ ok: boolean; detail: string; keyValid?: boolean }>("/api/settings/validate", { method: "POST", body: JSON.stringify(body) }),
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
