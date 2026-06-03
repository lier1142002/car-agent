/** 单条消息 */
export interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: number;
  citations?: Citation[];
  /** 消息类型: 普通对话 / 车型对比 / 智能推荐 */
  msgType?: 'chat' | 'compare' | 'recommend';
  /** 结构化数据 (对比结果/推荐结果) */
  structuredData?: Record<string, unknown>;
}

/** 引用来源（前端展示用） */
export interface Citation {
  index: number;
  title: string;
  text: string;
  score: number;
  tool: string;
}

/** 对话 */
export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  /** v2: 后端会话 ID (Redis 隔离, 每个对话独立) */
  sessionId: string;
}

/** 引用来源（后端API返回） */
export interface Source {
  text: string;
  tool: string;
  score?: number;
  title?: string;
  url?: string;
}

/** 执行追踪步骤 */
export interface TraceStep {
  step: string;
  detail: string;
  status: 'pending' | 'running' | 'done' | 'error';
  timestamp?: number;
}

/** 旧版 Agent 全局状态 (保留兼容) */
export interface AgentState {
  memory: Array<{ id: number; type: string; content: string; timestamp?: string }>;
  tools: string[];
  rag_indexed: boolean;
  iteration_count: number;
}

/** ========== V2 API Types ========== */

/** 输入模式 */
export type InputMode = 'chat' | 'compare' | 'recommend';

/** 统一 API 响应 */
export interface ApiResponse<T = Record<string, unknown>> {
  request_id: string;
  session_id: string;
  status: 'success' | 'degraded' | 'error';
  data?: T;
  error?: string;
  degraded: boolean;
  latency_ms: number;
}

/** 车型查询请求 */
export interface VehicleQueryRequest {
  session_id: string;
  user_id: string;
  query: string;
}

/** 多车对比请求 */
export interface VehicleCompareRequest {
  session_id: string;
  user_id: string;
  vehicles: string[];
  aspects?: string[];
}

/** 智能推荐请求 */
export interface RecommendRequest {
  session_id: string;
  user_id: string;
  scenario?: string;
  budget?: string;
  preferences?: string[];
}

/** 会话关闭请求 */
export interface SessionCloseRequest {
  session_id: string;
  user_id: string;
}

/** 对比结果 */
export interface CompareResult {
  structured_params: Record<string, Record<string, string[]>>;
  llm_summary: string;
  vehicle_count: number;
}

/** 推荐结果 */
export interface RecommendResult {
  recommendations: Array<{
    vehicle: string;
    total_score: number;
    dimensions: Record<string, { score: number; reason: string; weight: number }>;
  }>;
}

/** 健康检查响应 */
export interface HealthResponse {
  status: string;
  redis: string;
  rabbitmq: string;
}

/** ========== Legacy (keep for settings/eval) ========== */

export interface ChatRequest {
  query: string;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
  trace: string[];
  actions: Array<{ tool: string; query: string }>;
}

export interface WSMessage {
  type: string;
  payload: Record<string, unknown>;
}

export interface ConfigSettings {
  llm_api_key: string;
  serpapi_key: string;
  llamaparse_api_key: string;
  embedding_model: string;
  llm_model: string;
  llm_api_url: string;
  llm_temperature: number;
  llm_max_tokens: number;
}

export interface UpdateConfigPayload {
  llm_api_key?: string;
  serpapi_key?: string;
  llamaparse_api_key?: string;
  llm_model?: string;
  llm_api_url?: string;
  llm_temperature?: number;
  llm_max_tokens?: number;
}

export interface PdfUploadResponse {
  status: 'success' | 'error';
  filename: string;
  chunks: number;
  message: string;
}

export interface DatasetSummary {
  name: string;
  total_samples: number;
  by_type: Record<string, number>;
  by_difficulty: Record<string, number>;
}

export interface EvalRunRequest {
  dataset_name: string;
  retrieval_mode: 'dense' | 'sparse' | 'hybrid';
  top_k: number;
  generate_answers: boolean;
}

export interface EvalSampleResult {
  query: string;
  ground_truth: string;
  context_relevance: number;
  context_recall: number;
  mrr: number;
  ndcg: number;
  faithfulness: number;
  hallucination_rate: number;
  answer_relevance: number;
  generated_answer: string;
  retrieval_latency_ms: number;
  generation_latency_ms: number;
}

export interface EvalRunResponse {
  dataset_name: string;
  total_samples: number;
  retrieval_mode: string;
  config: Record<string, unknown>;
  retrieval_quality: {
    context_relevance: number;
    context_recall: number;
    mrr: number;
    ndcg: number;
  };
  generation_quality: {
    faithfulness: number;
    hallucination_rate: number;
    answer_relevance: number;
  };
  performance: {
    avg_retrieval_latency_ms: number;
    avg_generation_latency_ms: number;
    p95_retrieval_latency_ms: number;
    p95_generation_latency_ms: number;
  };
  per_sample: EvalSampleResult[];
  failed_samples: string[];
}

export interface WeightSweepRequest {
  dataset_name: string;
  top_k: number;
  generate_answers: boolean;
}

/** ========== App State ========== */

export interface AppState {
  conversations: Conversation[];
  activeId: string;
  messages: Message[];
  isThinking: boolean;
  thinkingStatus: string;
  sources: Source[];
  trace: TraceStep[];
  agentState: AgentState | null;
  /** V2 新增 */
  userId: string;
  inputMode: InputMode;
}

export type AppAction =
  | { type: 'SET_THINKING'; payload: boolean }
  | { type: 'SET_THINKING_STATUS'; payload: string }
  | { type: 'ADD_MESSAGE'; payload: Message }
  | { type: 'UPDATE_LAST_AGENT_MESSAGE'; payload: string }
  | { type: 'SET_LAST_AGENT_MESSAGE'; payload: string }
  | { type: 'SET_SOURCES'; payload: Source[] }
  | { type: 'ADD_TRACE_STEP'; payload: TraceStep }
  | { type: 'UPDATE_TRACE_STEP'; payload: { step: string; status: TraceStep['status']; detail?: string } }
  | { type: 'SET_AGENT_STATE'; payload: AgentState }
  | { type: 'NEW_CONVERSATION' }
  | { type: 'SWITCH_CONVERSATION'; payload: string }
  | { type: 'CLEAR_MESSAGES' }
  | { type: 'SET_CONVERSATION_SESSION'; payload: { conversationId: string; sessionId: string } }
  | { type: 'SET_INPUT_MODE'; payload: InputMode };
