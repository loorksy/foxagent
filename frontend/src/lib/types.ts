export type ViewMode = "split" | "chart" | "chat";

export type OverlayPoint = {
  timestamp: number;
  value: number;
  dataIndex?: number;
};

export type OverlayStyles = {
  fillColor?: string;
  borderColor?: string;
  lineColor?: string;
  lineWidth?: number;
  color?: string;
  textColor?: string;
  backgroundColor?: string;
  [key: string]: unknown;
};

export type KlineOverlay = {
  name: string;
  groupId?: string;
  id?: string;
  points: OverlayPoint[];
  styles?: OverlayStyles;
  annotationText?: string;
  extendData?: unknown;
  lock?: boolean;
  visible?: boolean;
  zLevel?: number;
};

export type TakeProfitLevel = {
  level: number;
  price: number;
  ratio: string;
};

export type TradeSetup = {
  action: "BUY" | "SELL";
  orderType: string;
  entryPrice: number;
  stopLoss: number;
  takeProfitLevels: TakeProfitLevel[];
  riskRewardRatio: number;
};

export type TradeRecommendation = {
  id: string;
  timestamp: string;
  symbol: string;
  timeframe: string;
  sentiment: "BULLISH" | "BEARISH" | "NEUTRAL";
  tradeSetup: TradeSetup;
  rationale: string;
  confluence: string[];
  klineOverlays: KlineOverlay[];
  status: string;
  pnlPips?: number | null;
  pnlPercent?: number | null;
  model?: string | null;
  visionNotes?: string | null;
  focusTimestamp?: number | null;
};

export type KLineBar = {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type Instrument = {
  ticker: string;
  symbol: string;
  display: string;
  name: string;
  pricePrecision: number;
  pip: number;
};

export type ChatRole = "user" | "assistant" | "system";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  createdAt: number;
  recommendationId?: string;
  streaming?: boolean;
};

export type AgentPhase = {
  id: number;
  name: string;
  detail: string;
  status: "pending" | "active" | "complete" | "error";
};

export type LivePrice = {
  instrument: string;
  bid: number;
  ask: number;
  mid: number;
  time: string;
  spread: number;
  source: string;
};

export type ModelOption = {
  id: string;
  label: string;
  badge?: string;
};

export type SettingsPublic = {
  anthropicApiKeySet: boolean;
  oandaApiTokenSet: boolean;
  oandaAccountId: string;
  oandaEnvironment: string;
  defaultClaudeModel: string;
  maxRiskPercent: number;
  minRiskReward: number;
  allowedSessions: string[];
  oandaConfigured: boolean;
  anthropicConfigured: boolean;
  dataMode: "oanda" | "simulator";
};

export type SettingsPayload = {
  anthropicApiKey: string;
  oandaApiToken: string;
  oandaAccountId: string;
  oandaEnvironment: "practice" | "live";
  defaultClaudeModel: string;
  maxRiskPercent: number;
  minRiskReward: number;
  allowedSessions: string[];
};
