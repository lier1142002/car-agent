# AutoSalesAgent — 汽车销售培训 AI Agent

> **「组件化是核心，工作流是灵魂」**

面向汽车销售场景的企业级 AI Agent 系统。集成 RAG 知识库检索、联网搜索、数学计算等工具，通过 **规划 → 执行 → 反思迭代** 工作流生成专业回答。提供 CLI 命令行界面和 React Web 前端。

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    main.py (CLI)  /  React SPA              │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    Agent Core Layer                          │
│                                                              │
│   Planning ──→ Executor ──→ (LLM 生成答案) ──→ Reflection   │
│      │            │              │                 │         │
│      │     ┌──────┴──────┐      │         需要补充? ──→ 循环 │
│      │     │  工具注册表   │      │              │            │
│      │     ├─ rag_tool    │      │           不需要           │
│      │     ├─ web_search  │      │              │            │
│      │     └─ calculator  │      │         输出最终答案        │
│      │     └──────────────┘      │                            │
│      │                           │                            │
│   Memory ◄─── 短期存储 + LLM 压缩 ──────────────────────────── │
└──────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   Infrastructure Layer                       │
│   EmbeddingClient (千问 API)   VectorDB (Milvus)              │
│   DocParser (LlamaParse)                                      │
└──────────────────────────────────────────────────────────────┘
```

### 后端分层

| 层 | 模块 | 职责 |
|---|------|------|
| **基础设施** | `embedding.py` `vector_db.py` `doc_parser.py` | 向量化、Milvus 混合检索、PDF 解析+智能切块 |
| **工具层** | `rag_tool.py` `web_search_tool.py` `calculator_tool.py` | 知识库检索、联网搜索(SerpAPI+多线程爬虫)、安全计算 |
| **Agent 核心** | `planning.py` `memory.py` `executor.py` `reflection.py` | LLM 规划、短期记忆+压缩、任务调度、质量评估+迭代控制 |
| **API 服务** | `server.py` (FastAPI) | REST + WebSocket 端点 |

### 前端分层 (React 18 + TypeScript + Ant Design 5)

| 层 | 路径 | 说明 |
|---|------|------|
| **类型定义** | `src/types/index.ts` | 完整 TS 接口和 Action 类型 |
| **服务层** | `src/services/` | HTTP 封装 (`api.ts`) + WebSocket 管理 (`websocket.ts`) |
| **状态管理** | `src/store/` | Context + useReducer (12 种 Action) |
| **组件层** | `src/components/` | 三栏布局: Sidebar / ChatPanel / TracePanel |
| **样式** | `src/styles/` | CSS Modules 暗色主题 |

### 数据流

```
用户输入 → Planning(LLM 生成 JSON ActionList) → Executor(调度工具)
                                                    ↓
              Reflection(质量评分) ← 初步答案 ← LLM 综合生成
                    ↓ 需补充
              新 ActionList → Executor → ... (最多3次迭代)
                    ↓ 达标
              最终答案 (含引用来源和检索路径)
```

---

## 技术栈

### 后端
- **Python** 3.10+
- **Milvus** 2.4+ — 稠密+稀疏双向量混合检索 (WeightedRanker)
- **BGE-M3** — 通过阿里千问 Embedding API 调用，不本地加载模型
- **LlamaParse** — PDF 文档解析为 Markdown
- **FastAPI** — REST + WebSocket API 服务
- **ChromaDB** — Web 搜索结果临时语义检索
- **BeautifulSoup + ThreadPoolExecutor** — 多线程网页爬取

### 前端
- **React 18** + **TypeScript** 5.6
- **Vite** 6 — 构建工具，开发代理到 FastAPI
- **Ant Design** 5 — 企业级 UI 组件库 (暗色主题)
- **CSS Modules** — 组件级样式隔离

### 核心原则
- 零重型框架：不使用 LangChain 等，全部组件手写
- 统一 API 接口：所有 LLM/Embedding 调用走 OpenAI 兼容格式
- 扁平化对外接口：`AutoSalesAgent.run_query(str) -> str`

---

## 项目结构

```
AutoSalesAgent/
├── config.py                     # 全局配置（API密钥、模型参数、检索参数）
├── main.py                       # CLI 交互入口
├── requirements.txt              # Python 依赖
│
├── infrastructure/               # 基础设施层
│   ├── embedding.py              # Embedding 客户端（千问 API，稠密+稀疏向量）
│   ├── vector_db.py              # Milvus 连接、索引管理、混合检索
│   └── doc_parser.py             # LlamaParse PDF 解析 + 智能文本切块
│
├── tools/                        # 工具组件层
│   ├── base_tool.py              # 工具抽象基类
│   ├── rag_tool.py               # 本地知识库检索增强生成
│   ├── web_search_tool.py        # 联网搜索（SerpAPI + 爬虫 + ChromaDB）
│   └── calculator_tool.py        # 安全数学计算器
│
├── agent/                        # Agent 核心层
│   ├── planning.py               # 任务规划（LLM 生成 JSON ActionList）
│   ├── memory.py                 # 短期/长期记忆管理
│   ├── executor.py               # 任务队列调度执行
│   ├── reflection.py             # 质量评估与迭代控制
│   └── agent_core.py             # Agent 主循环（整合四大模块）
│
├── prompts/                      # 提示词模板
│   ├── plan_prompt.txt           # Few-shot 规划提示词
│   ├── reflection_prompt.txt     # 反思评估提示词
│   └── rag_prompt.txt            # RAG 回答生成模板
│
├── data/                         # 产品文档存放
│   └── product.pdf               # 示例：星辰电动ES9 产品手册
│
├── frontend/                     # React 前端
│   ├── backend/
│   │   └── server.py             # FastAPI 服务端（REST + WebSocket）
│   ├── src/
│   │   ├── types/index.ts        # TypeScript 类型定义
│   │   ├── services/             # API 和 WebSocket 封装
│   │   ├── store/                # Context + Reducer 状态管理
│   │   ├── components/
│   │   │   ├── Layout/           # 三栏布局容器
│   │   │   ├── Sidebar/          # 知识库状态、工具、对话列表
│   │   │   ├── Chat/             # 聊天气泡、思考动画、输入框
│   │   │   └── Trace/            # 引用来源卡片、执行路径
│   │   ├── pages/                # 页面组件
│   │   ├── styles/               # CSS Modules 暗色主题
│   │   └── utils/                # 格式化工具函数
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
└── docs/superpowers/             # 设计文档和计划
    ├── specs/                    # 设计规格
    └── plans/                    # 实施计划
```

---

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
cd AutoSalesAgent

# 安装 Python 依赖
pip install -r requirements.txt

# 启动 Milvus（本地模式或 Docker）
# 本地模式: 修改 config.py 中 milvus_uri = "./milvus.db"
# Docker 模式: docker run -d --name milvus -p 19530:19530 milvusdb/milvus
```

### 2. 配置 API 密钥

编辑 `config.py`，填入真实的 API 密钥：

```python
llm_api_key: str = "sk-your-real-qwen-key"       # 千问 API Key
serpapi_key: str = "your-real-serpapi-key"       # SerpAPI Key（可选）
llamaparse_api_key: str = "your-real-llamaparse-key"  # LlamaParse Key（可选）
```

### 3. 索引知识库

```bash
# CLI 模式
python main.py
> /index data/product.pdf

# 或通过 API
curl -X POST http://localhost:8000/api/index \
  -H "Content-Type: application/json" \
  -d '{"file_path": "data/product.pdf"}'
```

### 4. 启动服务

**方式一：CLI 交互**

```bash
python main.py
```

**方式二：前后端分离**

```bash
# 终端 1: 启动后端 API
cd frontend/backend
python server.py                    # http://localhost:8000

# 终端 2: 启动前端开发服务器
cd frontend
npm install
npm run dev                         # http://localhost:3000
```

浏览器打开 `http://localhkost:3000`，即可使用三栏布局 Web 界面。

### 5. 使用示例

```
🧑 你 > 星辰ES9的纯电续航里程是多少公里？
🤖 Agent > 星辰ES9 搭载 100kWh 三元锂电池，CLTC 工况纯电续航为 700 公里 [1]...

🧑 你 > 对比一下星辰ES9和特斯拉Model Y，哪个更适合家庭使用？
🤖 Agent > 基于产品资料和最新市场信息，从空间、续航、价格、安全性四个维度对比...
    [1] 星辰ES9产品手册  [2] 特斯拉官网  [3] 汽车之家评测

🧑 你 > 贷款买星辰ES9，首付30%分36期，月供大概多少？
🤖 Agent > 星辰ES9 售价 28.8 万元起，首付 30% 即 8.64 万...
    月供 = (288000 - 86400) / 36 ≈ 5600 元/月 [计算结果]
```

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/chat` | 完整 Agent 查询（返回答案 + 来源 + 追踪） |
| `POST` | `/api/index` | 索引知识库 PDF 文档 |
| `POST` | `/api/clear` | 清空会话记忆 |
| `GET` | `/api/state` | 获取 Agent 内部状态 |
| `WS` | `/ws/chat` | 实时流式查询（逐阶段推送进度事件） |

### WebSocket 消息类型

```json
{"type": "plan_start",  "payload": {"query": "..."}}
{"type": "plan_result", "payload": {"actions": [...]}}
{"type": "tool_start",  "payload": {"tool": "rag_tool", "query": "..."}}
{"type": "tool_result", "payload": {"tool": "rag_tool", "result": "...", "sources": [...]}}
{"type": "answer",      "payload": {"answer": "..."}}
{"type": "reflection",  "payload": {"score": 0.85, "needs_iteration": false}}
{"type": "done",        "payload": {"final_answer": "...", "sources": [...], "trace": {...}}}
{"type": "error",       "payload": {"message": "..."}}
```

---

## 可优化方向

### 高优先级

| 方向 | 现状 | 优化建议 |
|------|------|---------|
| **流式回答** | 当前 `run_query` 为同步阻塞返回完整结果，WebSocket 仅推送阶段节点 | 接入千问 streaming API，实现 token 级别流式输出到前端，提升交互体验 |
| **错误重试** | 工具执行失败只记录日志，不自动重试 | 添加指数退避重试机制，对网络异常和 API 限流自动恢复 |
| **多轮对话** | Memory 支持但未在前端展示历史注入效果 | 实现检索增强的多轮对话（查询重写 + 历史相关片段注入） |
| **并发安全** | Agent 单例全局共享，无锁保护 | 添加请求队列或 asyncio.Lock，支持并发请求串行化 |

### 中优先级

| 方向 | 现状 | 优化建议 |
|------|------|---------|
| **知识库管理** | 索引时全量重建 Collection | 支持增量索引、文档删除、版本管理 |
| **向量化批处理** | `encode_batch` 逐条调用 API | 使用千问 batch embedding API 减少网络往返 |
| **Web 搜索缓存** | 每次搜索新建 ChromaDB 集合并立即删除 | 实现 LRU 缓存层，对相同查询复用近期结果 |
| **前端离线状态** | WebSocket 断开后自动重连，但无离线队列 | 添加消息队列，重连后自动重发 |
| **移动端适配** | 三栏布局在窄屏上拥挤 | 实现响应式布局：窄屏切换为单栏 + 抽屉式面板 |

### 低优先级

| 方向 | 现状 | 优化建议 |
|------|------|---------|
| **长期记忆** | `Memory` 中预留接口但未实现 | 接入 Milvus 持久化用户偏好和历史知识 |
| **工具扩展** | 工具注册表已支持动态注册 | 添加更多工具：车型对比图生成、金融方案计算器、试驾预约 |
| **可观测性** | 仅 `logging` 模块记录日志 | 接入 OpenTelemetry，追踪每个请求的完整调用链 |
| **权限控制** | 无认证机制 | 添加 API Key 认证或 OAuth2，保护生产环境 |
| **测试覆盖** | 当前无自动化测试 | 为核心模块添加单元测试和集成测试 |
| **国际化** | 仅支持中文 | 提示词模板多语言化，支持英文销售场景 |
| **容器化部署** | 手动启动前后端 | 编写 Docker Compose 一键部署（含 Milvus + Embedding 代理） |

---

## 设计文档

- [前后端联调设计规格](docs/superpowers/specs/2026-05-14-frontend-design.md)
- [后端实施计划](docs/superpowers/plans/2026-05-12-auto-sales-agent.md)
- [前端实施计划](docs/superpowers/plans/2026-05-14-frontend-plan.md)

## License

MIT
