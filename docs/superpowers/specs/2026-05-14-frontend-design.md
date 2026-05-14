# AutoSalesAgent 前后端联调设计文档

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│              Frontend (React 18 + TypeScript)            │
│   Sidebar │ ChatPanel │ TracePanel                       │
│   (状态/历史) │ (对话气泡) │ (引用追溯/执行路径)              │
└──────────────┬──────────────────────────────────────────┘
               │ HTTP REST + WebSocket
┌──────────────▼──────────────────────────────────────────┐
│            Backend API (FastAPI)                         │
│   /api/chat  /api/index  /api/state  /ws/chat            │
│                    │                                     │
│            AutoSalesAgent.run_query()                    │
└──────────────────────────────────────────────────────────┘
```

**技术栈:**
- 前端: React 18 + TypeScript + Vite + Ant Design 5 + CSS Modules
- 后端 API: FastAPI + WebSocket
- Agent: 已有 AutoSalesAgent (planning → exec → reflect 工作流)

---

## 后端 API 设计

### 新增文件: `frontend/backend/server.py`

FastAPI 服务，包装 AutoSalesAgent，提供 REST + WebSocket 接口。

**端点:**

| 方法 | 路径 | 请求体 | 响应体 | 说明 |
|------|------|--------|--------|------|
| POST | /api/chat | `{query: str}` | `{answer, sources, trace, actions}` | 完整 Agent 查询 |
| WebSocket | /ws/chat | `{query: str}` | stream: `{type, payload}` | 实时推送每一步 |
| POST | /api/index | `{file_path: str}` | `{status, chunks}` | 索引知识库 |
| POST | /api/clear | `{}` | `{status}` | 清空会话 |
| GET | /api/state | - | `{memory, tools, rag_indexed}` | Agent 状态 |
| GET | /api/health | - | `{status}` | 健康检查 |

**WebSocket 消息格式 (服务端推送):**
```json
{"type": "plan_start", "payload": {"query": "..."}}
{"type": "plan_result", "payload": {"actions": [{"tool": "rag_tool", "query": "..."}]}}
{"type": "tool_start", "payload": {"tool": "rag_tool", "query": "..."}}
{"type": "tool_result", "payload": {"tool": "rag_tool", "result": "...", "sources": [...]}}
{"type": "answer", "payload": {"answer": "..."}}
{"type": "reflection", "payload": {"score": 0.85, "needs_iteration": false}}
{"type": "done", "payload": {"final_answer": "...", "sources": [...], "trace": {...}}}
{"type": "error", "payload": {"message": "..."}}
```

---

## 前端组件树

```
App
├── Layout (Ant Design Layout 三栏)
│   ├── Sidebar (Sider, 220px)
│   │   ├── KnowledgeStatus       — 知识库索引状态指示灯
│   │   ├── ToolStatus            — 已注册工具列表
│   │   └── ConversationList      — 历史对话列表（可切换/新建）
│   ├── ChatPanel (Content, flex:1)
│   │   ├── ChatHeader            — 当前对话标题 + 清空按钮
│   │   ├── MessageList           — 消息列表（可滚动）
│   │   │   ├── UserMessage       — 用户消息气泡（右对齐，蓝色）
│   │   │   └── AgentMessage      — Agent 消息气泡（左对齐，含引用标记）
│   │   ├── ThinkingIndicator     — 思考动画（三点跳动 + 状态文本）
│   │   └── ChatInput             — 输入框 + 发送按钮 + 上传按钮
│   └── TracePanel (Sider, 300px, right)
│       ├── SourceCard ×N         — 引用来源卡片（标题/摘要/分数/工具标签）
│       └── ExecutionPath         — 检索执行路径步骤列表
```

---

## 前端数据流

### 状态管理 (React Context + useReducer)

```typescript
interface AppState {
  conversations: Conversation[];    // 所有对话
  activeId: string;                 // 当前对话 ID
  messages: Message[];              // 当前消息列表
  isThinking: boolean;              // Agent 是否在思考中
  thinkingStatus: string;           // 思考状态文本
  sources: Source[];                // 当前回答的引用来源
  trace: TraceStep[];               // 执行路径
  agentState: AgentState | null;    // Agent 后端状态
}
```

### 交互流程

1. 用户输入 → `POST /api/chat` → 等待完整响应 → 更新 messages + sources + trace
2. 或: 建立 WebSocket → 发送查询 → 实时接收 plan/tool/answer/reflection → 逐步渲染
3. 页面初始化 → `GET /api/state` → 更新 Sidebar 状态显示
4. 索引文档 → `POST /api/index` → 更新 KnowledgeStatus

---

## 文件结构

```
frontend/
├── backend/
│   └── server.py              # FastAPI 服务端
├── src/
│   ├── main.tsx               # React 入口
│   ├── App.tsx                # 根组件 + 路由
│   ├── vite-env.d.ts          # Vite 类型声明
│   ├── components/
│   │   ├── Layout/
│   │   │   └── AppLayout.tsx  # 三栏布局容器
│   │   ├── Sidebar/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── KnowledgeStatus.tsx
│   │   │   ├── ToolStatus.tsx
│   │   │   └── ConversationList.tsx
│   │   ├── Chat/
│   │   │   ├── ChatPanel.tsx
│   │   │   ├── ChatHeader.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── UserMessage.tsx
│   │   │   ├── AgentMessage.tsx
│   │   │   ├── ThinkingIndicator.tsx
│   │   │   └── ChatInput.tsx
│   │   └── Trace/
│   │       ├── TracePanel.tsx
│   │       ├── SourceCard.tsx
│   │       └── ExecutionPath.tsx
│   ├── pages/
│   │   └── ChatPage.tsx       # 主聊天页面
│   ├── services/
│   │   ├── api.ts             # HTTP 请求封装
│   │   └── websocket.ts       # WebSocket 连接管理
│   ├── store/
│   │   ├── AppContext.tsx      # 全局状态 Context
│   │   └── reducer.ts         # useReducer reducer
│   ├── styles/
│   │   ├── global.css         # 全局样式 + 主题变量
│   │   ├── Chat.module.css
│   │   ├── Sidebar.module.css
│   │   └── Trace.module.css
│   ├── types/
│   │   └── index.ts           # TypeScript 类型定义
│   └── utils/
│       └── format.ts          # 文本格式化工具
├── public/
│   └── favicon.svg
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

---

## 自审清单

1. **无占位符**: 所有接口、类型、文件路径均已明确定义
2. **内部一致**: 组件树与文件结构一一对应；API 端点与前端 services 对应；WebSocket 消息类型覆盖完整工作流
3. **范围合理**: 单个 spec 涵盖后端 API + 前端 UI，是完整的前后联调交付
4. **无歧义**: 所有消息格式使用 JSON 示例明确；组件职责单一清晰
