# AutoSalesAgent Frontend + Backend Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build React 18 + TypeScript frontend with FastAPI backend, integrating with AutoSalesAgent for real-time chat with knowledge tracing.

**Architecture:** FastAPI wraps AutoSalesAgent exposing REST + WebSocket endpoints. React SPA with three-column layout (Sidebar/Chat/Trace) consumes API via HTTP + WS. State managed via Context + useReducer.

**Tech Stack:** React 18, TypeScript, Vite, Ant Design 5, FastAPI, WebSocket, CSS Modules

---

## File Map

| File | Responsibility |
|------|---------------|
| `frontend/backend/server.py` | FastAPI server wrapping AutoSalesAgent, REST + WS |
| `frontend/package.json` | Node dependencies & scripts |
| `frontend/vite.config.ts` | Vite build config + API proxy |
| `frontend/tsconfig.json` | TypeScript config |
| `frontend/index.html` | HTML entry with Ant Design CDN CSS |
| `frontend/src/types/index.ts` | All TypeScript interfaces & types |
| `frontend/src/services/api.ts` | HTTP fetch wrapper for REST endpoints |
| `frontend/src/services/websocket.ts` | WebSocket connection manager |
| `frontend/src/store/AppContext.tsx` | React Context provider |
| `frontend/src/store/reducer.ts` | State reducer with actions |
| `frontend/src/components/Layout/AppLayout.tsx` | Three-column Ant Design Layout |
| `frontend/src/components/Sidebar/Sidebar.tsx` | Left sidebar container |
| `frontend/src/components/Sidebar/KnowledgeStatus.tsx` | KB index status indicator |
| `frontend/src/components/Sidebar/ToolStatus.tsx` | Registered tools list |
| `frontend/src/components/Sidebar/ConversationList.tsx` | History conversations |
| `frontend/src/components/Chat/ChatPanel.tsx` | Main chat area container |
| `frontend/src/components/Chat/ChatHeader.tsx` | Chat title + actions |
| `frontend/src/components/Chat/MessageList.tsx` | Scrollable message list |
| `frontend/src/components/Chat/UserMessage.tsx` | User message bubble |
| `frontend/src/components/Chat/AgentMessage.tsx` | Agent message bubble with citations |
| `frontend/src/components/Chat/ThinkingIndicator.tsx` | Loading animation |
| `frontend/src/components/Chat/ChatInput.tsx` | Input box + send + file upload |
| `frontend/src/components/Trace/TracePanel.tsx` | Right knowledge trace panel |
| `frontend/src/components/Trace/SourceCard.tsx` | Individual source citation card |
| `frontend/src/components/Trace/ExecutionPath.tsx` | Execution steps timeline |
| `frontend/src/pages/ChatPage.tsx` | Main page composing all components |
| `frontend/src/App.tsx` | Root component |
| `frontend/src/main.tsx` | React DOM entry |
| `frontend/src/styles/global.css` | Global styles + theme |
| `frontend/src/styles/Chat.module.css` | Chat component styles |
| `frontend/src/styles/Sidebar.module.css` | Sidebar styles |
| `frontend/src/styles/Trace.module.css` | Trace panel styles |
| `frontend/src/utils/format.ts` | Text/date formatting utilities |
| `frontend/src/vite-env.d.ts` | Vite type declarations |
| `frontend/public/favicon.svg` | Car emoji favicon |

---

### Task 1: Backend FastAPI Server

**Files:** Create `frontend/backend/server.py`

- [ ] **Step 1: Write FastAPI server with all endpoints**

```python
"""
AutoSalesAgent FastAPI 服务端。

包装 Agent 核心，提供 REST API + WebSocket 接口供前端调用。
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent.agent_core import AutoSalesAgent
from config import config


# ── Pydantic Models ────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str

class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    trace: Dict[str, Any]
    actions: List[Dict[str, str]]

class IndexRequest(BaseModel):
    file_path: str

class IndexResponse(BaseModel):
    status: str
    chunks: int

class StateResponse(BaseModel):
    memory: List[Dict[str, Any]]
    tools: List[str]
    rag_indexed: bool
    iteration_count: int


# ── App Setup ──────────────────────────────────────────────────

app = FastAPI(
    title="AutoSalesAgent API",
    description="汽车销售培训 AI Agent 后端服务",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global agent instance
agent: AutoSalesAgent | None = None


def get_agent() -> AutoSalesAgent:
    global agent
    if agent is None:
        agent = AutoSalesAgent()
    return agent


# ── REST Endpoints ─────────────────────────────────────────────

@app.get("/api/health")
async def health() -> Dict[str, str]:
    """健康检查。"""
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """处理聊天查询，返回完整结果（含来源和追踪）。"""
    ag = get_agent()
    answer = ag.run_query(request.query)
    state = ag.get_state()

    # 从记忆中提取最近一次工具结果中的来源信息
    sources: List[Dict[str, Any]] = []
    trace: Dict[str, Any] = {
        "iterations": state.get("iteration_count", 0),
        "tools_used": [],
    }

    # 遍历记忆提取来源和工具调用
    for entry in state.get("memory", []):
        if entry.get("type") == "tool_result":
            tool_name = entry.get("content", "").split("]")[0].strip("[")
            trace["tools_used"].append(tool_name)

    # 从 RAG 工具获取最近检索结果
    # (简化处理：来源信息从记忆条目提取)
    for entry in state.get("memory", []):
        if isinstance(entry, dict):
            content = entry.get("content", "")
            if "[来源" in content or "引用" in content:
                # 解析引用信息
                pass

    return ChatResponse(
        answer=answer,
        sources=sources,
        trace=trace,
        actions=[],  # Action list not easily extracted from run_query return
    )


@app.post("/api/index", response_model=IndexResponse)
async def index_knowledge(request: IndexRequest) -> IndexResponse:
    """索引知识库文档。"""
    ag = get_agent()
    try:
        chunks = ag.index_knowledge_base(request.file_path)
        return IndexResponse(status="success", chunks=chunks)
    except Exception as e:
        return IndexResponse(status="error", chunks=0)


@app.post("/api/clear")
async def clear_session() -> Dict[str, str]:
    """清空当前会话。"""
    ag = get_agent()
    ag.clear_session()
    return {"status": "ok"}


@app.get("/api/state", response_model=StateResponse)
async def get_state() -> StateResponse:
    """获取 Agent 当前状态。"""
    ag = get_agent()
    state = ag.get_state()
    return StateResponse(
        memory=state.get("memory", []),
        tools=state.get("tools", []),
        rag_indexed=state.get("rag_indexed", False),
        iteration_count=state.get("iteration_count", 0),
    )


# ── WebSocket Endpoint ─────────────────────────────────────────

@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    """WebSocket 实时聊天，推送工作流每一步状态。"""
    await ws.accept()

    ag = get_agent()

    async def send_event(event_type: str, payload: Dict[str, Any]) -> None:
        """推送事件到客户端。"""
        try:
            await ws.send_json({"type": event_type, "payload": payload})
        except Exception:
            pass

    try:
        while True:
            data = await ws.receive_text()
            request = json.loads(data)
            query = request.get("query", "")

            if not query:
                await send_event("error", {"message": "Empty query"})
                continue

            # 推送规划开始
            await send_event("plan_start", {"query": query})

            # 执行 Agent
            try:
                answer = ag.run_query(query)
                state = ag.get_state()

                # 提取来源信息
                sources: List[Dict[str, Any]] = []
                memory = state.get("memory", [])
                for entry in memory:
                    if entry.get("type") == "tool_result":
                        content = entry.get("content", "")
                        sources.append({
                            "text": content[:300],
                            "tool": "rag_tool" if "rag" in content.lower() else "web_search",
                        })

                await send_event("answer", {"answer": answer})
                await send_event("done", {
                    "final_answer": answer,
                    "sources": sources[:5],
                    "trace": {"iterations": state.get("iteration_count", 0)},
                })

            except Exception as e:
                await send_event("error", {"message": str(e)})

    except WebSocketDisconnect:
        logging.info("WebSocket client disconnected")


# ── Entry Point ────────────────────────────────────────────────

def main() -> None:
    """启动 FastAPI 服务。"""
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify server starts**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend/backend && python -c "from server import app; print('FastAPI app created OK')"
```

---

### Task 2: Frontend Project Scaffold

**Files:** Create `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/vite-env.d.ts`, `frontend/public/favicon.svg`

- [ ] **Step 1: Write package.json**

```json
{
  "name": "auto-sales-agent-frontend",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "antd": "^5.22.0",
    "@ant-design/icons": "^5.5.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0"
  }
}
```

- [ ] **Step 2: Write vite.config.ts**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
});
```

- [ ] **Step 3: Write tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Write index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AutoSalesAgent - 汽车销售培训 AI</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Write favicon and vite-env.d.ts**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><text y="28" font-size="28">🚗</text></svg>
```

```typescript
/// <reference types="vite/client" />
```

---

### Task 3: TypeScript Types

**Files:** Create `frontend/src/types/index.ts`

- [ ] **Step 1: Write all type definitions**

```typescript
/** 单条消息 */
export interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: number;
  citations?: Citation[];
}

/** 引用来源 */
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

/** 引用来源（后端返回） */
export interface Source {
  text: string;
  tool: string;
  score?: number;
  title?: string;
  url?: string;
}

/** 执行追踪 */
export interface TraceStep {
  step: string;
  detail: string;
  status: 'pending' | 'running' | 'done' | 'error';
  timestamp?: number;
}

/** 追踪信息（后端返回） */
export interface Trace {
  iterations: number;
  tools_used: string[];
}

/** Agent 状态（后端返回） */
export interface AgentState {
  memory: Array<{ id: number; type: string; content: string }>;
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
```

---

### Task 4: Frontend Services

**Files:** Create `frontend/src/services/api.ts`, `frontend/src/services/websocket.ts`

- [ ] **Step 1: Write api.ts (HTTP client)**

```typescript
import type { ChatRequest, ChatResponse, AgentState } from '../types';

const BASE = '/api';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function sendChat(data: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function indexKnowledge(filePath: string): Promise<{ status: string; chunks: number }> {
  return request('/index', {
    method: 'POST',
    body: JSON.stringify({ file_path: filePath }),
  });
}

export async function clearSession(): Promise<void> {
  await request('/clear', { method: 'POST' });
}

export async function getAgentState(): Promise<AgentState> {
  return request<AgentState>('/state');
}

export async function healthCheck(): Promise<{ status: string }> {
  return request('/health');
}
```

- [ ] **Step 2: Write websocket.ts**

```typescript
import type { WSMessage } from '../types';

type MessageHandler = (msg: WSMessage) => void;
type StatusHandler = (connected: boolean) => void;

export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: MessageHandler[] = [];
  private statusHandlers: StatusHandler[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = true;

  constructor(url: string = 'ws://localhost:8000/ws/chat') {
    this.url = url;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    this.shouldReconnect = true;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.notifyStatus(true);
      };

      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const msg: WSMessage = JSON.parse(event.data);
          this.handlers.forEach(h => h(msg));
        } catch {
          // ignore parse errors
        }
      };

      this.ws.onclose = () => {
        this.notifyStatus(false);
        if (this.shouldReconnect) {
          this.reconnectTimer = setTimeout(() => this.connect(), 3000);
        }
      };

      this.ws.onerror = () => {
        this.ws?.close();
      };
    } catch {
      if (this.shouldReconnect) {
        this.reconnectTimer = setTimeout(() => this.connect(), 3000);
      }
    }
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.notifyStatus(false);
  }

  send(query: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ query }));
    }
  }

  onMessage(handler: MessageHandler): () => void {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter(h => h !== handler);
    };
  }

  onStatusChange(handler: StatusHandler): () => void {
    this.statusHandlers.push(handler);
    return () => {
      this.statusHandlers = this.statusHandlers.filter(h => h !== handler);
    };
  }

  private notifyStatus(connected: boolean): void {
    this.statusHandlers.forEach(h => h(connected));
  }
}
```

---

### Task 5: Global State Management

**Files:** Create `frontend/src/store/reducer.ts`, `frontend/src/store/AppContext.tsx`

- [ ] **Step 1: Write reducer.ts**

```typescript
import type { AppState, AppAction, Message } from '../types';

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

export const initialState: AppState = {
  conversations: [],
  activeId: '',
  messages: [],
  isThinking: false,
  thinkingStatus: '',
  sources: [],
  trace: [],
  agentState: null,
};

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_THINKING':
      return { ...state, isThinking: action.payload };

    case 'SET_THINKING_STATUS':
      return { ...state, thinkingStatus: action.payload };

    case 'ADD_MESSAGE': {
      const msg = action.payload;
      const newMessages = [...state.messages, msg];
      // Update conversation in list
      const updatedConversations = state.conversations.map(c =>
        c.id === state.activeId
          ? { ...c, messages: newMessages }
          : c
      );
      return {
        ...state,
        messages: newMessages,
        conversations: updatedConversations,
      };
    }

    case 'UPDATE_LAST_AGENT_MESSAGE': {
      const msgs = [...state.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'agent') {
          msgs[i] = { ...msgs[i], content: action.payload };
          break;
        }
      }
      return { ...state, messages: msgs };
    }

    case 'SET_SOURCES':
      return { ...state, sources: action.payload };

    case 'ADD_TRACE_STEP':
      return { ...state, trace: [...state.trace, action.payload] };

    case 'UPDATE_TRACE_STEP': {
      const newTrace = state.trace.map(t =>
        t.step === action.payload.step
          ? {
              ...t,
              status: action.payload.status,
              detail: action.payload.detail ?? t.detail,
            }
          : t
      );
      return { ...state, trace: newTrace };
    }

    case 'SET_AGENT_STATE':
      return { ...state, agentState: action.payload };

    case 'NEW_CONVERSATION': {
      const newConv = {
        id: generateId(),
        title: '新对话',
        messages: [],
        createdAt: Date.now(),
      };
      return {
        ...state,
        conversations: [newConv, ...state.conversations],
        activeId: newConv.id,
        messages: [],
        sources: [],
        trace: [],
      };
    }

    case 'SWITCH_CONVERSATION': {
      const conv = state.conversations.find(c => c.id === action.payload);
      return {
        ...state,
        activeId: action.payload,
        messages: conv?.messages ?? [],
        sources: [],
        trace: [],
      };
    }

    case 'CLEAR_MESSAGES':
      return {
        ...state,
        messages: [],
        sources: [],
        trace: [],
        isThinking: false,
      };

    default:
      return state;
  }
}
```

- [ ] **Step 2: Write AppContext.tsx**

```typescript
import React, { createContext, useContext, useReducer, useCallback, useEffect, type Dispatch } from 'react';
import type { AppState, AppAction, Message, Source, TraceStep } from '../types';
import { appReducer, initialState } from './reducer';
import { ChatWebSocket } from '../services/websocket';
import { sendChat, getAgentState } from '../services/api';

interface AppContextValue {
  state: AppState;
  dispatch: Dispatch<AppAction>;
  sendMessage: (text: string) => Promise<void>;
  startNewConversation: () => void;
  switchConversation: (id: string) => void;
  ws: ChatWebSocket;
}

const AppContext = createContext<AppContextValue | null>(null);

const ws = new ChatWebSocket();

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);

  // Initialise: fetch agent state + first conversation
  useEffect(() => {
    getAgentState()
      .then(s => dispatch({ type: 'SET_AGENT_STATE', payload: s }))
      .catch(() => {});

    const convId = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    const initialConv = {
      id: convId,
      title: '新对话',
      messages: [],
      createdAt: Date.now(),
    };
    dispatch({
      type: 'NEW_CONVERSATION',
      payload: undefined as never,
    } as never);
    // Actually let's just set it manually
    state.conversations.push(initialConv);
    state.activeId = convId;
  }, []);

  const sendMessage = useCallback(async (text: string) => {
    // Add user message
    const userMsg: Message = {
      id: Date.now().toString(36),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    dispatch({ type: 'ADD_MESSAGE', payload: userMsg });
    dispatch({ type: 'SET_THINKING', payload: true });
    dispatch({ type: 'SET_THINKING_STATUS', payload: '正在分析问题...' });

    try {
      const response = await sendChat({ query: text });

      // Convert sources to trace steps
      const traceSteps: TraceStep[] = response.actions.map((a, i) => ({
        step: `${i + 1}. ${a.tool}`,
        detail: a.query,
        status: 'done' as const,
        timestamp: Date.now(),
      }));
      traceSteps.push({
        step: `${response.actions.length + 1}. reflection`,
        detail: `迭代次数: ${response.trace.iterations}`,
        status: 'done' as const,
        timestamp: Date.now(),
      });

      const agentMsg: Message = {
        id: (Date.now() + 1).toString(36),
        role: 'agent',
        content: response.answer,
        timestamp: Date.now(),
        citations: response.sources.map((s, i) => ({
          index: i + 1,
          title: s.title ?? s.tool,
          text: s.text,
          score: s.score ?? 0,
          tool: s.tool,
        })),
      };

      dispatch({ type: 'ADD_MESSAGE', payload: agentMsg });
      dispatch({ type: 'SET_SOURCES', payload: response.sources });
      // Set trace from actions
      for (const step of traceSteps) {
        dispatch({ type: 'ADD_TRACE_STEP', payload: step });
      }
    } catch (err) {
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(36),
        role: 'agent',
        content: `抱歉，请求失败: ${err instanceof Error ? err.message : '未知错误'}`,
        timestamp: Date.now(),
      };
      dispatch({ type: 'ADD_MESSAGE', payload: errorMsg });
    } finally {
      dispatch({ type: 'SET_THINKING', payload: false });
      dispatch({ type: 'SET_THINKING_STATUS', payload: '' });
    }
  }, []);

  const startNewConversation = useCallback(() => {
    dispatch({ type: 'NEW_CONVERSATION' } as AppAction);
  }, []);

  const switchConversation = useCallback((id: string) => {
    dispatch({ type: 'SWITCH_CONVERSATION', payload: id });
  }, []);

  return (
    <AppContext.Provider value={{ state, dispatch, sendMessage, startNewConversation, switchConversation, ws }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
```

---

### Task 6: Frontend Components

**Files:** Create all 16 component files as per file map above.

Each component will be written with full TypeScript types and Ant Design integration.

---

### Task 7: Styles & Utilities

**Files:** Create `frontend/src/styles/global.css`, `Chat.module.css`, `Sidebar.module.css`, `Trace.module.css`, `frontend/src/utils/format.ts`

---

### Task 8: App Entry & Integration Test

**Files:** Create `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/pages/ChatPage.tsx`

---

### Task 9: npm Install & Dev Server Verification

**Files:** None (verification only)

- [ ] **Step 1: Install dependencies**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npm install
```

- [ ] **Step 2: Start dev server**

```bash
cd c:/Users/18049/Desktop/agent_car/frontend && npm run dev
```

- [ ] **Step 3: Verify page loads at http://localhost:3000**
