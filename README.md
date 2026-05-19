# AutoSalesAgent — 汽车销售培训 AI Agent

> **「组件化是核心，工作流是灵魂」**

面向汽车销售场景的企业级 AI Agent 系统。集成 RAG 知识库检索、联网搜索、数学计算等工具，通过 **规划 → 执行 → 反思迭代** 工作流生成专业回答。提供 CLI 命令行界面和 React Web 前端（可视化配置面板 + RAG 评测工作台）。

---

## 架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│                     main.py (CLI)  /  React SPA                   │
│   Settings Drawer ←── LLM/Embedding/API Key 可视化配置             │
│   Eval Panel ←── RAG 评测工作台（图表 + 权重扫描）                  │
│   PDF Upload ←── 拖拽上传自动入库                                 │
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
│   EmbeddingClient (DeepSeek / 千问)   VectorDB (Milvus 混合检索)    │
│   DocParser (LlamaParse)                                            │
└────────────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                     Eval Layer                                     │
│   EvalRunner (批量评测)   Metrics (6项指标)   LLM-as-a-Judge        │
│   DatasetGenerator     Weight Sweep     Report (JSON/CSV/Table)    │
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
├── config.py                          # 全局配置（LLM/Embedding/检索参数）
├── main.py                            # CLI 交互入口
├── requirements.txt                   # Python 依赖
│
├── infrastructure/                    # 基础设施层
│   ├── embedding.py                   # Embedding 工厂（DeepSeek / 千问 运行时切换）
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
├── eval/                              # RAG 评测模块
│   ├── metrics.py                     # 6 项评测指标（检索+生成质量）
│   ├── dataset.py                     # Golden Dataset 构建与自动生成
│   ├── runner.py                      # 批量评测运行器（含权重扫描）
│   ├── report.py                      # 结果报告输出（JSON/CSV/CLI Table）
│   ├── prompts.py                     # LLM-as-a-Judge 评测提示词模板
│   ├── datasets/                      # 评测数据集存放
│   └── reports/                       # 评测报告输出目录
│
├── data/                              # 产品文档存放
│   └── product.pdf                    # 示例产品手册
│
├── frontend/                          # React 前端
│   ├── backend/
│   │   └── server.py                  # FastAPI 服务端（REST 11端点 + WebSocket）
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
│       │   ├── Sidebar/               # 知识库状态、工具列表、对话历史、入口按钮
│       │   ├── Chat/                  # 聊天气泡、思考动画、输入框
│       │   ├── Trace/                 # 引用来源卡片、执行路径
│       │   └── Settings/              # 配置 + 评测面板
│       │       ├── SettingsDrawer.tsx  # 设置抽屉（Embedding + LLM + API Key + PDF）
│       │       ├── ApiKeyForm.tsx      # API Key 编辑表单
│       │       ├── LlmConfigForm.tsx   # LLM 配置（模型/URL/Temperature/MaxTokens）
│       │       ├── EmbeddingSelector.tsx # DeepSeek/千问 模型选择器
│       │       ├── PdfUploader.tsx     # PDF 拖拽上传组件
│       │       ├── EvalPanel.tsx       # 评测面板（Tab 容器）
│       │       ├── EvalOverviewTab.tsx # 雷达图 + 柱状图 + 性能
│       │       ├── EvalPerSampleTab.tsx # 散点图 + 逐样本明细
│       │       └── EvalSweepTab.tsx    # 权重扫描 + 对比柱状图
│       ├── pages/ChatPage.tsx         # 主聊天页面
│       ├── styles/                    # CSS Modules 暗色主题
│       └── utils/format.ts            # 格式化工具函数
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
└── docs/superpowers/                  # 设计文档和计划
    ├── specs/                         # 设计规格（4 篇）
    └── plans/                         # 实施计划（5 篇）
```

---

## 技术栈

### 后端 (Python ~5000 行)

| 组件 | 技术 | 说明 |
|------|------|------|
| LLM API | DeepSeek (OpenAI 兼容) | `deepseek-chat`，统一接口格式 |
| Embedding | DeepSeek Embedding / 千问 `text-embedding-v3` | 工厂模式，运行时切换，稠密+稀疏双向量 |
| 向量数据库 | Milvus 2.4+ | 稠密(COSINE) + 稀疏(IP) WeightedRanker 混合检索 |
| 文档解析 | LlamaParse API | PDF → Markdown，保留表格结构 |
| 联网搜索 | SerpAPI + BeautifulSoup + ChromaDB | 多线程爬虫(8线程) + 语义重排 |
| API 服务 | FastAPI + WebSocket | REST 11 端点 + WebSocket 8 种事件推送 |
| 数学计算 | Python `eval` | 受限命名空间安全执行 |

### 前端 (TypeScript + CSS ~3000 行)

| 组件 | 技术 | 说明 |
|------|------|------|
| 框架 | React 18 + TypeScript 5.6 | 严格类型覆盖 |
| 构建 | Vite 6 | 开发代理到 FastAPI |
| UI 库 | Ant Design 5 | 暗色主题 + 自定义 token |
| 图表 | Recharts | 雷达图、柱状图、散点图 |
| 样式 | CSS Modules | 组件级样式隔离 |
| 状态管理 | Context + useReducer | 12 种 Action，单数据流 |

### 核心原则

- **零重型框架**：不使用 LangChain，全部组件手写
- **统一 API 接口**：所有 LLM/Embedding 调用走 OpenAI 兼容格式
- **扁平化对外接口**：`AutoSalesAgent.run_query(str) -> str`
- **工厂模式 Embedding**：支持 DeepSeek/千问 运行时切换
- **可视化配置**：LLM 模型/参数、Embedding 提供商均可 Web 界面实时切换
- **RAG 评测闭环**：数据集 → 评测运行 → 指标可视化 → 权重调优

---

## 快速开始

### 1. 环境准备

```bash
cd AutoSalesAgent
pip install -r requirements.txt

cd frontend && npm install

# 启动 Milvus（二选一）
# 本地嵌入模式: 修改 config.py 中 milvus_uri = "./milvus.db"
# Docker 模式: docker run -d --name milvus -p 19530:19530 milvusdb/milvus
```

### 2. 启动服务

```bash
# 终端 1: 启动后端 API
python frontend/backend/server.py    # http://localhost:8000

# 终端 2: 启动前端开发服务器
cd frontend
npm run dev                          # http://localhost:3000
```

浏览器打开 `http://localhost:3000`。

### 3. 配置 API 密钥（Web 界面）

点击左侧 Sidebar **⚙ 设置**，在抽屉面板中：

- **Embedding 模型**：卡片式切换 DeepSeek / 千问
- **LLM 配置**：下拉选择模型、修改 API URL、调节 Temperature / Max Tokens
- **API 密钥**：填写 LLM / Embedding / SerpAPI / LlamaParse 密钥

保存后即时生效，无需重启。

### 4. 索引知识库

在设置面板底部拖拽上传 PDF，或使用 CLI：

```bash
python main.py
> /index data/product.pdf
```

### 5. 运行 RAG 评测

点击左侧 Sidebar **RAG 评测**，在评测面板中：

1. 选择数据集（自动扫描 `eval/datasets/`）
2. 配置检索模式、Top-K、是否生成回答
3. 点击"运行评测"
4. 查看结果：**总览**（雷达图 + 柱状图）、**逐样本**（散点图 + 明细）、**权重扫描**（多组对比）

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/config` | 获取当前配置（API Key 脱敏） |
| `PUT` | `/api/config` | 运行时更新配置（LLM/Embedding/密钥） |
| `GET` | `/api/state` | 获取 Agent 内部状态 |
| `POST` | `/api/chat` | 完整 Agent 查询（答案 + 来源 + 追踪） |
| `POST` | `/api/index` | 索引知识库 PDF（服务器路径） |
| `POST` | `/api/upload-pdf` | 上传 PDF 文件（multipart）并自动入库 |
| `POST` | `/api/clear` | 清空会话记忆 |
| `GET` | `/api/eval/datasets` | 列出可用评测数据集及摘要 |
| `POST` | `/api/eval/run` | 运行评测（返回聚合指标 + 逐样本结果） |
| `POST` | `/api/eval/sweep` | 运行权重扫描评测（6组 preset） |
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
你 > 星辰ES9的纯电续航里程是多少公里？
Agent > 星辰ES9 搭载 100kWh 三元锂电池，CLTC 工况纯电续航为 700 公里 [1]...

你 > 对比一下星辰ES9和特斯拉Model Y，哪个更适合家庭使用？
Agent > 基于产品资料和最新市场信息，从空间、续航、价格、安全性四个维度对比...
    [1] 星辰ES9产品手册  [2] 特斯拉官网  [3] 汽车之家评测

你 > 贷款买星辰ES9，首付30%分36期，月供大概多少？
Agent > 星辰ES9 售价 28.8 万元起，首付 30% 即 8.64 万...
    月供 = (288000 - 86400) / 36 ≈ 5600 元/月 [计算结果]
```

---

## 模块职责

### 后端核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| 配置中心 | `config.py` | 全局配置数据类，LLM/Embedding/检索参数，环境变量 + 运行时更新 |
| Embedding | `infrastructure/embedding.py` | 工厂模式：DeepSeek/千问 provider + 外观类 |
| 向量数据库 | `infrastructure/vector_db.py` | Milvus 连接管理、混合检索(WeightedRanker) |
| 文档解析 | `infrastructure/doc_parser.py` | LlamaParse 解析 + 4级智能切块策略 |
| RAG 工具 | `tools/rag_tool.py` | 文档索引、混合检索、LLM 回答生成 |
| 评测模块 | `eval/` | 6 项检索/生成指标、数据集构建、批量评测、权重扫描、多格式报告 |
| 规划模块 | `agent/planning.py` | LLM 生成 JSON ActionList + 意图分类 |
| 记忆模块 | `agent/memory.py` | 短期记忆列表 + LLM 压缩(阈值2000字符) |
| 执行器 | `agent/executor.py` | 工具注册表 + deque 任务队列调度 |
| 反思模块 | `agent/reflection.py` | 质量评分 + 补充 Action 生成(最多3轮) |
| API 服务 | `frontend/backend/server.py` | FastAPI: 11 REST 端点 + 1 WebSocket 端点 |

### 前端核心组件

| 组件 | 文件 | 说明 |
|------|------|------|
| AppLayout | `Layout/AppLayout.tsx` | 三栏布局 + SettingsDrawer + EvalPanel 集成 |
| Sidebar | `Sidebar/Sidebar.tsx` | 知识库状态、工具列表、对话历史、设置/RAG评测入口 |
| ChatPanel | `Chat/ChatPanel.tsx` | 对话容器：Header + Messages + Thinking + Input |
| TracePanel | `Trace/TracePanel.tsx` | 引用来源卡片 + 执行路径步骤 |
| SettingsDrawer | `Settings/SettingsDrawer.tsx` | 配置抽屉：Embedding选择 + LLM配置 + API Key + PDF上传 |
| ApiKeyForm | `Settings/ApiKeyForm.tsx` | API Key 可视化编辑（4个字段） |
| LlmConfigForm | `Settings/LlmConfigForm.tsx` | LLM 配置（模型下拉 + API URL + Temperature + MaxTokens） |
| EmbeddingSelector | `Settings/EmbeddingSelector.tsx` | DeepSeek/千问 模型卡片选择器 |
| PdfUploader | `Settings/PdfUploader.tsx` | PDF 拖拽上传 + 进度条 + 结果提示 |
| EvalPanel | `Settings/EvalPanel.tsx` | 评测面板 Tab 容器 |
| EvalOverviewTab | `Settings/EvalOverviewTab.tsx` | 雷达图 + 检索/生成柱状图 + 性能 |
| EvalPerSampleTab | `Settings/EvalPerSampleTab.tsx` | 散点图(Relevance×Faithfulness) + 逐样本明细 |
| EvalSweepTab | `Settings/EvalSweepTab.tsx` | 权重扫描运行 + 分组柱状对比图 |

---

## RAG 评测

`eval/` 模块提供完整的本地 RAG 评测方案，量化评估和优化检索与生成质量。支持 CLI (Python API) 和 Web 前端两种使用方式。

### 评测指标体系

| 维度 | 指标 | 计算方式 | 范围 |
|------|------|---------|------|
| 检索 | Context Relevance | LLM 逐块判断检索内容与 query 的相关性 | [0, 1] |
| 检索 | Context Recall | 标注正样本中被检索到的比例（Jaccard 模糊匹配） | [0, 1] |
| 检索 | MRR | 第一个相关文档排名倒数的均值 | [0, 1] |
| 检索 | NDCG@k | 归一化折损累计增益（二值标签） | [0, 1] |
| 生成 | Faithfulness | 提取 claims → LLM 蕴含判断 → supported/total | [0, 1] |
| 生成 | Hallucination Rate | 1 - Faithfulness，即无法验证的 claims 占比 | [0, 1] |
| 生成 | Answer Relevance | LLM 对回答-问题相关度 1-5 评分后归一化 | [0, 1] |

### CLI 使用方式

```python
from tools.rag_tool import RAGTool
from eval.dataset import GoldenDataset
from eval.runner import EvalRunner
from eval.report import print_report_table, save_report_json

# 1. 初始化并索引知识库
rag = RAGTool()
rag.index_documents("data/product.pdf")

# 2. 加载评测数据集
ds = GoldenDataset.load("eval/datasets/auto_sales_eval_v1.0.json")

# 3. 运行评测
runner = EvalRunner(rag, top_k=5)
report = runner.run(ds, retrieval_mode="hybrid", generate_answers=True)

# 4. 查看结果
print_report_table(report)       # CLI 表格
save_report_json(report)         # JSON 报告

# 5. 权重扫描
reports = runner.sweep_weights(ds)
print_weight_sweep_table(reports)
```

### Web 前端评测

点击 Sidebar **RAG 评测** 按钮打开评测面板：

- **总览 Tab**：雷达图总览所有指标 + 检索/生成质量柱状图 + 性能延迟统计
- **逐样本 Tab**：散点图展示样本分布 + 每样本指标详情（含标准答案和生成回答对比）
- **权重扫描 Tab**：一键运行 6 组预设权重对比，分组柱状图展示最优配比

### 数据集构建

1. **自动生成**：`DatasetGenerator` 基于 PDF 文本块调用 LLM 自动生成事实查询/对比分析/销售场景三类 QA 对
2. **手工标注**：按 `EvalSample` 数据结构手工编写 JSON
3. **混合模式**：自动生成 + 质量审核 + 人工补充修正

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
| 容器化 | 手动启动 | Docker Compose 一键部署 |

---

## 设计文档

- [前后端联调设计](docs/superpowers/specs/2026-05-14-frontend-design.md)
- [可视化配置 & PDF上传设计](docs/superpowers/specs/2026-05-14-config-pdf-upload-design.md)
- [LLM 配置前端化设计](docs/superpowers/specs/2026-05-19-llm-config-frontend-design.md)
- [RAG 评测前端化设计（一期）](docs/superpowers/specs/2026-05-19-eval-frontend-phase1-design.md)
- [RAG 评测可视化设计（二期）](docs/superpowers/specs/2026-05-19-eval-visualization-phase2-design.md)

## License

MIT
