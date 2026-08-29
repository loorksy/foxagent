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

export type StructureFvg = {
  direction: string;
  low: number;
  high: number;
  timestampStart: number;
  timestampEnd: number;
};

export type StructureScan = {
  bias?: string;
  lastBos?: string | null;
  fvgCount?: number;
  orderBlocks?: number;
  liquiditySweep?: string | null;
  asianHigh?: number;
  asianLow?: number;
  confluence?: string[];
  fvgs?: StructureFvg[];
};

export type MemoryEntry = {
  id: string;
  symbol: string;
  kind: string;
  status: string;
  decision: string;
  reflection?: string;
  rating?: string;
  recommendationId?: string;
  outcome?: string;
  pnl?: number;
  createdAt?: string | null;
};

export type RunThought = {
  agent: string;
  text: string;
  channel?: string;
};

export type RunTool = {
  id: string;
  agent: string;
  name: string;
  input?: unknown;
  output?: unknown;
};

export type DebateLine = {
  role: string;
  agent: string;
  text: string;
};

export type Artifact = {
  id: string;
  title: string;
  type: string;
  language?: string;
  agent?: string;
  body: string;
  createdAt?: string;
};

export type MemoryRecall = {
  instrument?: string;
  count?: number;
  text?: string;
  lessons?: string[];
};

export type AgentSession = {
  id: string;
  title: string;
  symbol: string;
  timeframe: string;
  state: {
    messages?: ChatMessage[];
    thoughts?: RunThought[];
    tools?: RunTool[];
    debate?: DebateLine[];
    artifacts?: Artifact[];
    overlays?: KlineOverlay[];
    recalls?: MemoryRecall[];
    recommendationId?: string | null;
  };
  createdAt?: string;
  updatedAt?: string;
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
  telegramBotTokenSet: boolean;
  telegramChatId: string;
  enableTelegramNotifications: boolean;
  telegramConfigured: boolean;
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
  telegramBotToken: string;
  telegramChatId: string;
  enableTelegramNotifications: boolean;
};
