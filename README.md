# AutoSalesAgent — 汽车销售培训 AI Agent

> **「组件化是核心，工作流是灵魂」**

面向汽车销售场景的企业级 AI Agent 系统。集成 RAG 知识库检索、联网搜索、数学计算等工具，通过 **规划 → 执行 → 反思迭代** 工作流生成专业回答。提供 CLI 命令行界面和 React Web 前端（含可视化配置面板）。

---

## 架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│                     main.py (CLI)  /  React SPA                   │
│                     Settings Drawer ←── 可视化配置 API Key          │
│                     PDF Upload ←── 拖拽上传自动入库                │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                     Agent Core Layer                               │
│                                                                    │
│   Planning ──→ Executor ──→ (LLM 生成答案) ──→ Reflection         │
│      │            │              │                 │               │
│      │     ┌──────┴──────┐      │         需要补充? ──→ 循环 (≤3)  │
│      │     │  工具注册表   │      │              │                  │
│      │     ├─ rag_tool    │      │           不需要                 │
│      │     ├─ web_search  │      │              │                  │
│      │     └─ calculator  │      │         输出最终答案              │
│      │     └──────────────┘      │                                  │
│      │                           │                                  │
│   Memory ◄─── 短期存储 + LLM 压缩 ──────────────────────────────────│
└────────────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                   Infrastructure Layer                             │
│   EmbeddingClient (千问 / DeepSeek)   VectorDB (Milvus 混合检索)    │
│   DocParser (LlamaParse)                                            │
└────────────────────────────────────────────────────────────────────┘
```

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

## 项目结构

```
AutoSalesAgent/
├── config.py                          # 全局配置（API Key、模型选择、检索参数）
├── main.py                            # CLI 交互入口
├── requirements.txt                   # Python 依赖
│
├── infrastructure/                    # 基础设施层
│   ├── embedding.py                   # Embedding 工厂（千问 / DeepSeek 运行时切换）
│   ├── vector_db.py                   # Milvus 连接、索引管理、混合检索
│   └── doc_parser.py                  # LlamaParse PDF 解析 + 智能文本切块
│
├── tools/                             # 工具组件层
│   ├── base_tool.py                   # 工具抽象基类
│   ├── rag_tool.py                    # 本地知识库检索增强生成
│   ├── web_search_tool.py             # 联网搜索（SerpAPI + 爬虫 + ChromaDB）
│   └── calculator_tool.py             # 安全数学计算器
│
├── agent/                             # Agent 核心层
│   ├── planning.py                    # 任务规划（LLM 生成 JSON ActionList）
│   ├── memory.py                      # 短期/长期记忆管理（LLM 压缩）
│   ├── executor.py                    # 任务队列调度执行
│   ├── reflection.py                  # 质量评估与迭代控制（阈值 0.8）
│   └── agent_core.py                  # Agent 主循环（整合四大模块）
│
├── prompts/                           # 提示词模板
│   ├── plan_prompt.txt                # Few-shot 规划提示词
│   ├── reflection_prompt.txt          # 反思评估提示词
│   └── rag_prompt.txt                 # RAG 回答生成模板
│
├── data/                              # 产品文档存放
│   └── product.pdf                    # 示例产品手册
│
├── frontend/                          # React 前端
│   ├── backend/
│   │   └── server.py                  # FastAPI 服务端（REST + WebSocket，766 行）
│   └── src/
│       ├── types/index.ts             # TypeScript 类型定义
│       ├── services/
│       │   ├── api.ts                 # HTTP 请求封装
│       │   └── websocket.ts           # WebSocket 连接管理（自动重连）
│       ├── store/
│       │   ├── AppContext.tsx          # Context + useReducer 全局状态
│       │   └── reducer.ts             # 12 种 Action 纯函数 reducer
│       ├── components/
│       │   ├── Layout/                # AppLayout（三栏布局容器）
│       │   ├── Sidebar/               # 知识库状态、工具列表、对话历史、设置入口
│       │   ├── Chat/                  # 聊天气泡、思考动画、输入框
│       │   ├── Trace/                 # 引用来源卡片、执行路径
│       │   └── Settings/              # 可视化配置面板（新增）
│       │       ├── SettingsDrawer.tsx  # Drawer 容器
│       │       ├── ApiKeyForm.tsx      # API Key 编辑表单
│       │       ├── EmbeddingSelector.tsx # 千问/DeepSeek 模型选择器
│       │       └── PdfUploader.tsx     # PDF 拖拽上传组件
│       ├── pages/ChatPage.tsx         # 主聊天页面
│       ├── styles/                    # CSS Modules 暗色主题
│       └── utils/format.ts            # 格式化工具函数
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
└── docs/superpowers/                  # 设计文档和计划
    ├── specs/                         # 设计规格（2 篇）
    └── plans/                         # 实施计划（3 篇）
```

---

## 技术栈

### 后端 (Python ~3700 行)

| 组件 | 技术 | 说明 |
|------|------|------|
| LLM API | 阿里千问 (OpenAI 兼容) | `qwen-plus`，统一接口格式 |
| Embedding | 千问 `text-embedding-v3` / DeepSeek Embedding | 工厂模式，运行时切换，稠密+稀疏双向量 |
| 向量数据库 | Milvus 2.4+ | 稠密(COSINE) + 稀疏(IP) WeightedRanker 混合检索 |
| 文档解析 | LlamaParse API | PDF → Markdown，保留表格结构 |
| 联网搜索 | SerpAPI + BeautifulSoup + ChromaDB | 多线程爬虫(8线程) + 语义重排 |
| API 服务 | FastAPI + WebSocket | REST 8 端点 + WebSocket 8 种事件推送 |
| 数学计算 | Python `eval` | 受限命名空间安全执行 |

### 前端 (TypeScript + CSS ~2000 行)

| 组件 | 技术 | 说明 |
|------|------|------|
| 框架 | React 18 + TypeScript 5.6 | 严格类型覆盖 |
| 构建 | Vite 6 | 开发代理到 FastAPI |
| UI 库 | Ant Design 5 | 暗色主题 + 自定义 token |
| 样式 | CSS Modules | 组件级样式隔离 |
| 状态管理 | Context + useReducer | 12 种 Action，单数据流 |

### 核心原则

- **零重型框架**：不使用 LangChain，全部组件手写
- **统一 API 接口**：所有 LLM/Embedding 调用走 OpenAI 兼容格式
- **扁平化对外接口**：`AutoSalesAgent.run_query(str) -> str`
- **工厂模式 Embedding**：支持千问/DeepSeek 运行时切换

---

## 快速开始

### 1. 环境准备

```bash
cd AutoSalesAgent
pip install -r requirements.txt

# 启动 Milvus（二选一）
# 本地嵌入模式: 修改 config.py 中 milvus_uri = "./milvus.db"
# Docker 模式: docker run -d --name milvus -p 19530:19530 milvusdb/milvus
```

### 2. 配置 API 密钥

**方式一：Web 界面配置（推荐）**

启动服务后，点击左侧 Sidebar 底部 **⚙ 设置**，在抽屉面板中可视化配置所有 API Key，保存后即时生效，无需重启。

**方式二：编辑 config.py**

```python
llm_api_key: str = "sk-your-real-qwen-key"
embedding_api_key: str = "sk-your-real-qwen-key"
serpapi_key: str = "your-real-serpapi-key"          # 可选
llamaparse_api_key: str = "your-real-llamaparse-key" # 可选
```

**方式三：环境变量**

```bash
export LLM_API_KEY=sk-your-real-qwen-key
export EMBEDDING_API_KEY=sk-your-real-qwen-key
export EMBEDDING_PROVIDER=qwen    # 或 deepseek
```

### 3. 切换 Embedding 模型

通过设置面板的可视化选择器或直接调用 API 切换：

```bash
curl -X PUT http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{"embedding_provider": "deepseek"}'
```

支持 `qwen`（千问 text-embedding-v3, 1024维）和 `deepseek`（DeepSeek Embedding API, 1536维）。

### 4. 索引知识库

```bash
# CLI 方式
python main.py
> /index data/product.pdf

# API 方式（指定服务器路径）
curl -X POST http://localhost:8000/api/index \
  -H "Content-Type: application/json" \
  -d '{"file_path": "data/product.pdf"}'

# Web 上传方式
# 打开 Web 界面 → ⚙ 设置 → 拖拽 PDF 文件到上传区域即可
```

### 5. 启动服务

**方式一：CLI 交互**

```bash
python main.py
```

**方式二：前后端分离**

```bash
# 终端 1: 启动后端 API
python frontend/backend/server.py    # http://localhost:8000

# 终端 2: 启动前端开发服务器
cd frontend
npm install
npm run dev                          # http://localhost:3000
```

浏览器打开 `http://localhost:3000`，左侧输入问题，右侧查看引用追溯。

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/config` | 获取当前配置（API Key 脱敏） |
| `PUT` | `/api/config` | 运行时更新配置（Key / Embedding 提供商） |
| `GET` | `/api/state` | 获取 Agent 内部状态 |
| `POST` | `/api/chat` | 完整 Agent 查询（答案 + 来源 + 追踪） |
| `POST` | `/api/index` | 索引知识库 PDF（服务器路径） |
| `POST` | `/api/upload-pdf` | 上传 PDF 文件（multipart）并自动入库 |
| `POST` | `/api/clear` | 清空会话记忆 |
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

## 使用示例

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

## 模块职责

### 后端核心模块

| 模块 | 文件 | 行数 | 职责 |
|------|------|------|------|
| 配置中心 | `config.py` | 192 | 全局配置数据类，含环境变量和运行时更新 |
| Embedding | `infrastructure/embedding.py` | 159 | 工厂模式：千问/DeepSeek provider + 外观类 |
| 向量数据库 | `infrastructure/vector_db.py` | 343 | Milvus 连接管理、混合检索(WeightedRanker) |
| 文档解析 | `infrastructure/doc_parser.py` | 218 | LlamaParse 解析 + 4级智能切块策略 |
| RAG 工具 | `tools/rag_tool.py` | 235 | 文档索引、混合检索、LLM 回答生成 |
| 规划模块 | `agent/planning.py` | 174 | LLM 生成 JSON ActionList + 意图分类 |
| 记忆模块 | `agent/memory.py` | 192 | 短期记忆列表 + LLM 压缩(阈值2000字符) |
| 执行器 | `agent/executor.py` | 151 | 工具注册表 + deque 任务队列调度 |
| 反思模块 | `agent/reflection.py` | 201 | 质量评分 + 补充 Action 生成(最多3轮) |
| API 服务 | `frontend/backend/server.py` | 766 | FastAPI: 8 REST 端点 + 1 WebSocket 端点 |

### 前端核心组件

| 组件 | 文件 | 说明 |
|------|------|------|
| AppLayout | `Layout/AppLayout.tsx` | 三栏布局 + SettingsDrawer 集成 |
| Sidebar | `Sidebar/Sidebar.tsx` | 知识库状态、工具列表、对话历史、设置入口 |
| ChatPanel | `Chat/ChatPanel.tsx` | 对话容器：Header + Messages + Thinking + Input |
| TracePanel | `Trace/TracePanel.tsx` | 引用来源卡片 + 执行路径步骤 |
| SettingsDrawer | `Settings/SettingsDrawer.tsx` | 配置抽屉：Embedding选择 + API Key + PDF上传 |
| ApiKeyForm | `Settings/ApiKeyForm.tsx` | API Key 可视化编辑（4个字段） |
| EmbeddingSelector | `Settings/EmbeddingSelector.tsx` | 千问/DeepSeek 模型卡片选择器 |
| PdfUploader | `Settings/PdfUploader.tsx` | PDF 拖拽上传 + 进度条 + 结果提示 |

---

## 可优化方向

### 高优先级

| 方向 | 现状 | 优化建议 |
|------|------|---------|
| 流式回答 | `run_query` 同步阻塞返回，WebSocket 仅推送阶段节点 | 接入 streaming API，token 级流式输出 |
| 错误重试 | 工具执行失败只记录日志 | 指数退避重试机制 |
| 多轮对话 | Memory 支持但前端未展示历史注入 | 检索增强多轮对话（查询重写 + 历史片段注入） |
| 并发安全 | Agent 单例无锁保护 | 请求队列或 asyncio.Lock |

### 中优先级

| 方向 | 现状 | 优化建议 |
|------|------|---------|
| 知识库管理 | 索引时全量重建 Collection | 增量索引、文档删除、版本管理 |
| 向量化批处理 | `encode_batch` 逐条调用 API | 使用 batch embedding API 减少往返 |
| Web 搜索缓存 | 每次新建 ChromaDB 即删 | LRU 缓存层，复用近期结果 |
| 移动端适配 | 三栏布局窄屏拥挤 | 响应式布局：单栏 + 抽屉面板 |

### 低优先级

| 方向 | 现状 | 优化建议 |
|------|------|---------|
| 长期记忆 | Memory 预留接口未实现 | Milvus 持久化用户偏好 |
| 工具扩展 | 注册表已支持动态注册 | 车型对比图、金融方案计算器、试驾预约 |
| 可观测性 | 仅 logging 模块 | OpenTelemetry 全链路追踪 |
| 权限控制 | 无认证 | API Key 认证或 OAuth2 |
| 测试覆盖 | 无自动化测试 | 核心模块单元测试 + 集成测试 |
| 容器化 | 手动启动 | Docker Compose 一键部署 |

---

## 设计文档

- [前后端联调设计](docs/superpowers/specs/2026-05-14-frontend-design.md)
- [可视化配置 & PDF上传设计](docs/superpowers/specs/2026-05-14-config-pdf-upload-design.md)
- [后端实施计划](docs/superpowers/plans/2026-05-12-auto-sales-agent.md)
- [前端实施计划](docs/superpowers/plans/2026-05-14-frontend-plan.md)
- [配置 & PDF上传实施计划](docs/superpowers/plans/2026-05-14-config-pdf-upload-plan.md)

## License

MIT
