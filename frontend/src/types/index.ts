/** 单条消息 */
export interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: number;
  citations?: Citation[];
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

/** 追踪信息（后端API返回） */
export interface Trace {
  iterations: number;
  tools_used: string[];
}

/** Agent 全局状态（后端API返回） */
export interface AgentState {
  memory: Array<{ id: number; type: string; content: string; timestamp?: string }>;
  tools: string[];
  rag_indexed: boolean;
  iteration_count: number;
}

/** API Chat 请求 */
export interface ChatRequest {
  query: string;
}

/** API Chat 响应 */
export interface ChatResponse {
  answer: string;
  sources: Source[];
  trace: Trace;
  actions: Array<{ tool: string; query: string }>;
}

/** WebSocket 消息 */
export interface WSMessage {
  type: 'plan_start' | 'plan_result' | 'tool_start' | 'tool_result'
      | 'answer' | 'reflection' | 'done' | 'error';
  payload: Record<string, unknown>;
}

/** 全局应用状态 */
export interface AppState {
  conversations: Conversation[];
  activeId: string;
  messages: Message[];
  isThinking: boolean;
  thinkingStatus: string;
  sources: Source[];
  trace: TraceStep[];
  agentState: AgentState | null;
}

/** Reducer Action 类型 */
export type AppAction =
  | { type: 'SET_THINKING'; payload: boolean }
  | { type: 'SET_THINKING_STATUS'; payload: string }
  | { type: 'ADD_MESSAGE'; payload: Message }
  | { type: 'UPDATE_LAST_AGENT_MESSAGE'; payload: string }
  | { type: 'SET_SOURCES'; payload: Source[] }
  | { type: 'ADD_TRACE_STEP'; payload: TraceStep }
  | { type: 'UPDATE_TRACE_STEP'; payload: { step: string; status: TraceStep['status']; detail?: string } }
  | { type: 'SET_AGENT_STATE'; payload: AgentState }
  | { type: 'NEW_CONVERSATION' }
  | { type: 'SWITCH_CONVERSATION'; payload: string }
  | { type: 'CLEAR_MESSAGES' };

/** 配置设置（API Key 脱敏显示） */
export interface ConfigSettings {
  llm_api_key: string;
  embedding_api_key: string;
  embedding_provider: 'qwen' | 'deepseek';
  serpapi_key: string;
  llamaparse_api_key: string;
  embedding_model: string;
  llm_model: string;
  llm_api_url: string;
  llm_temperature: number;
  llm_max_tokens: number;
}

/** 更新配置请求体 */
export interface UpdateConfigPayload {
  llm_api_key?: string;
  embedding_api_key?: string;
  embedding_provider?: 'qwen' | 'deepseek';
  serpapi_key?: string;
  llamaparse_api_key?: string;
  llm_model?: string;
  llm_api_url?: string;
  llm_temperature?: number;
  llm_max_tokens?: number;
}

/** PDF 上传响应 */
export interface PdfUploadResponse {
  status: 'success' | 'error';
  filename: string;
  chunks: number;
  message: string;
}

/** 数据集摘要 */
export interface DatasetSummary {
  name: string;
  total_samples: number;
  by_type: Record<string, number>;
  by_difficulty: Record<string, number>;
}

/** 评测运行请求 */
export interface EvalRunRequest {
  dataset_name: string;
  retrieval_mode: 'dense' | 'sparse' | 'hybrid';
  top_k: number;
  generate_answers: boolean;
}

/** 单条样本评测结果 */
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

/** 评测运行响应 */
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

/** 权重扫描请求 */
export interface WeightSweepRequest {
  dataset_name: string;
  top_k: number;
  generate_answers: boolean;
}
