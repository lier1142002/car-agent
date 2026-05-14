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
}

/** 更新配置请求体 */
export interface UpdateConfigPayload {
  llm_api_key?: string;
  embedding_api_key?: string;
  embedding_provider?: 'qwen' | 'deepseek';
  serpapi_key?: string;
  llamaparse_api_key?: string;
}

/** PDF 上传响应 */
export interface PdfUploadResponse {
  status: 'success' | 'error';
  filename: string;
  chunks: number;
  message: string;
}
