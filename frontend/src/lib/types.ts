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
  analysis?: {
    technical?: string;
    fundamental?: string;
    bull?: string;
    bear?: string;
    risk?: string;
  } | null;
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

export type StrategyStatus = "draft" | "validated" | "active" | "rejected" | "archived" | "experimenting";
export type StrategySource = "builtin" | "claude_proposed" | "manual";

export type StrategyRule = {
  id: string;
  name: string;
  description: string;
  timeframes: string[];
  timeframe?: string[];
  direction: "buy" | "sell" | "both";
  entry_conditions: Record<string, unknown>;
  sessions?: string[];
  dsl?: Record<string, unknown>;
  kind?: "dsl" | "python";
  code?: string;
  pinned?: boolean;
  stop_rule: string;
  tp1_r: number;
  tp2_r: number;
  max_holding_bars: number;
  source: StrategySource;
  created_by: string;
  status: StrategyStatus;
  validation_report_id?: string | null;
  rejection_reason?: string | null;
  created_at?: string;
  validated_at?: string | null;
};

export type StrategyValidation = {
  ok: boolean;
  passed?: boolean;
  paused?: boolean;
  reasons?: string[];
  strategy?: StrategyRule;
  report?: BacktestReport;
  detail?: string;
};

export type StrategyExperimentAttempt = {
  n: number;
  change: string;
  passed: boolean;
  reasons?: string[];
  strategy?: StrategyRule;
  report?: {
    winRate?: number | null;
    profitFactor?: number | null;
    maxDrawdownR?: number | null;
    totalTrades?: number | null;
  };
};

export type StrategyExperimentJob = {
  id: string;
  strategyId: string;
  status: string;
  attempts: StrategyExperimentAttempt[];
  maxAttempts: number;
  createdAt?: string;
  passed: boolean;
  best?: StrategyExperimentAttempt | null;
};

export type TokenUsage = {
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens?: number;
  cacheReadTokens?: number;
  totalTokens: number;
  estimatedUsd?: number;
  model?: string;
  agent?: string;
  path?: string;
  runId?: string;
  calls?: number;
};

export type ChatImage = {
  id: string;
  src: string;
  caption?: string;
};

export type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  createdAt: number;
  recommendationId?: string;
  streaming?: boolean;
  strategyProposal?: StrategyRule;
  strategyValidation?: StrategyValidation;
  strategyExperiment?: StrategyExperimentJob;
  usage?: TokenUsage;
  images?: ChatImage[];
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

export type RunStep = {
  kind: "thought" | "tool" | "debate" | "recall" | "intent";
  agent?: string;
  text?: string;
  channel?: string;
  toolId?: string;
  toolName?: string;
  toolLabel?: string;
  toolInput?: unknown;
  toolOutput?: unknown;
  role?: string;
  intent?: string;
  at: number;
};

export type RunTool = {
  id: string;
  agent: string;
  name: string;
  label?: string;
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
  metaapiTokenSet?: boolean;
  metaapiAccountId?: string;
  metaapiConfigured?: boolean;
  botEnabled?: boolean;
  botScanInterval?: number;
  botAgents?: string[];
  botActiveStrategies?: string[];
  botMaxRiskPercent?: number;
  botMinRr?: number;
  botAllowedSessions?: string[];
  economicCalendarProvider?: string;
  economicCalendarCacheTtl?: number;
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
  metaapiToken?: string;
  metaapiAccountId?: string;
  botEnabled?: boolean;
  botScanInterval?: number;
  botAgents?: string[];
  botActiveStrategies?: string[];
  botMaxRiskPercent?: number;
  botMinRr?: number;
  botAllowedSessions?: string[];
  economicCalendarProvider?: string;
  economicCalendarCacheTtl?: number;
};

export type EconomicEvent = {
  id: string;
  title: string;
  country: string;
  timestamp: string;
  impact: "low" | "medium" | "high" | "critical";
  forecast?: number | null;
  previous?: number | null;
  actual?: number | null;
  unit?: string;
  source?: string;
  gold_impact?: "positive" | "negative" | "neutral";
};

export type BotSignal = {
  id: string;
  agentType: string;
  strategyId: string;
  instrument: string;
  timeframe: string;
  signalType: string;
  entryPrice: number;
  stopLoss: number;
  takeProfit1: number;
  takeProfit2: number;
  confidence: number;
  riskReward: number;
  status: string;
  pnl?: number;
  recommendationId?: string;
  createdAt?: string | null;
};

export type BotStatus = {
  running: boolean;
  enabled?: boolean;
  paused?: boolean;
  uptimeSeconds?: number;
  signalsToday?: number;
  lastError?: string;
};

export type BotInstanceType = "strategy" | "quant" | "alerts" | "execution";

export type BotInstanceStats = {
  cycles: number;
  lastError: string;
  lastSignalAt: string | null;
};

export type BotInstance = {
  id: string;
  name: string;
  type: BotInstanceType;
  enabled: boolean;
  scanIntervalSeconds: number;
  agents: string[];
  strategyIds: string[];
  minRr: number;
  maxRiskPercent: number;
  allowedSessions: string[];
  autoExecute: boolean;
  orderVolume: number;
  createdAt: string;
  stats: BotInstanceStats;
  isDefault?: boolean;
  running?: boolean;
};

export type BotInstanceCreatePayload = {
  name: string;
  type: BotInstanceType;
  scanIntervalSeconds: number;
  agents?: string[];
  strategyIds?: string[];
  minRr?: number;
  maxRiskPercent?: number;
  allowedSessions?: string[];
  autoExecute?: boolean;
  orderVolume?: number;
};

export type BacktestTrade = {
  strategyId: string;
  timeframe: string;
  entryTime: string;
  exitTime: string;
  direction: "buy" | "sell";
  entryPrice: number;
  stopLoss: number;
  takeProfit1: number;
  takeProfit2: number;
  exitPrice: number;
  pnlR: number;
  pnlPercent: number;
  exitReason: string;
};

export type BacktestBucket = {
  trades: number;
  wins: number;
  losses: number;
  winRate: number;
  totalR: number;
  averageR?: number;
};

export type BacktestReport = {
  id?: string;
  symbol: string;
  timeframe: string;
  strategyId?: string | null;
  days: number;
  candlesTested: number;
  totalTrades: number;
  wins: number;
  losses: number;
  winRate: number;
  averageR: number;
  totalR: number;
  profitFactor: number;
  maxDrawdownR: number;
  trades: BacktestTrade[];
  byStrategy: Record<string, BacktestBucket>;
  bySession: Record<string, BacktestBucket>;
  byMonth: Record<string, BacktestBucket>;
  textReport?: string;
  createdAt?: string | null;
};

export type StrategyPerf = {
  strategyId: string;
  agentType: string;
  totalSignals: number;
  wins: number;
  losses: number;
  winRate: number;
  averageWin?: number;
  averageLoss?: number;
  profitFactor?: number;
};

export type InboxTab = "inbox" | "approvals" | "alerts";

export type InboxItem = {
  id: string;
  tab: InboxTab;
  kind: "signal" | "recommendation" | "warehouse" | "news" | "bot";
  title: string;
  summary: string;
  severity: "high" | "medium" | "low";
  href: string;
  sourceHref: string;
  createdAt?: string | null;
  payload?: {
    signal?: BotSignal;
    recommendation?: TradeRecommendation;
    rejectionReason?: string;
    event?: EconomicEvent;
    minutes?: number;
    timeframes?: string[];
  };
};

export type InboxCounts = {
  open: number;
  inbox: number;
  approvals: number;
  alerts: number;
};

export type DeskStatus = {
  paused: boolean;
  botRunning: boolean;
  botEnabled?: boolean;
  warehouseStale: boolean;
  nextEventTitle?: string | null;
  nextEventMinutes?: number | null;
  openCount: number;
  lastError?: string;
};

export type InboxSnapshot = {
  items: InboxItem[];
  counts: InboxCounts;
  desk: DeskStatus;
};

export type PreflightCheck = {
  id: string;
  ok: boolean;
  blocking: boolean;
  label: string;
  detail: string;
};

export type PreflightReport = {
  ok: boolean;
  blocking: boolean;
  paused?: boolean;
  botRunning?: boolean;
  checks: PreflightCheck[];
};
