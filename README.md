# AutoSalesAgent — 高并发汽车销售 AI 平台

> **「组件化是核心，工作流是灵魂」** · v2 高并发架构

面向业务系统对接的企业级汽车销售 AI 平台。提供**车型查询 / 多车对比 / 智能推荐**三大 API 接口，采用 **Gateway + RabbitMQ + Worker Pool** 异步架构实现 500-2000 QPS 高吞吐，基于 **Redis 会话隔离** 支持多租户独立对话上下文，RAG 混合检索 + 规则引擎 + LLM 打分驱动场景化智能购车推荐。

---

## 架构概览

```
                     ┌─────────────────────────────┐
  业务系统 ──▶ Nginx ──▶ FastAPI Gateway (无状态)    │
                         │  · API Key 鉴权           │
                         │  · 滑动窗口限流 (Redis)    │
                         │  · POST /api/v1/vehicle/* │
                         ▼                          │
                     RabbitMQ (Topic Exchange)       │
                    ╱    │    ╲                     │
                   ▼     ▼     ▼                    │
             Worker  Worker  Worker  (多进程)        │
             · LLMPool 异步连接池                    │
             · BGE-M3 本地 Embedding                │
             · RAG 混合检索 + 规则引擎 + Scorer       │
             · Session 从 Redis 加载 / 保存          │
                         │                          │
                         ▼                          │
                    Milvus  +  Redis                 │
                 (向量检索)  (会话/缓存/限流)          │
```

### 数据流 (一次请求的完整生命周期)

```
Gateway 收到请求
  ├─ API Key 鉴权
  ├─ Redis 滑动窗口限流检查
  ├─ 封装消息 → RabbitMQ (routing_key + reply_to)
  │
Worker 消费消息
  ├─ Redis 加载 session:{id} 上下文
  ├─ 构建请求级 AgentForRequest 实例
  ├─ Plan → Execute (RAG/Web) → Generate → Reflect → Verify
  ├─ Redis 保存更新后的 session
  └─ 直接回复 Gateway → 返回业务系统
```

---

## 三大对外接口

| 接口 | 方法/路径 | 核心能力 | P99 目标 |
|------|-----------|----------|----------|
| 车型查询 | `POST /api/v1/vehicle/query` | RAG 混合检索 + LLM 结构化回答 | ≤ 500ms |
| 多车对比 | `POST /api/v1/vehicle/compare` | 并行 RAG × N → 规则引擎提取 → LLM 对比报告 | ≤ 800ms |
| 智能推荐 | `POST /api/v1/recommend` | 场景分析 → 规则初筛 → LLM 多维度打分排序 | ≤ 1000ms |

### 请求/响应格式

```json
// Request
POST /api/v1/vehicle/compare
{
  "session_id": "sess_xxx",
  "user_id": "user_001",
  "vehicles": ["问界M5", "理想L7", "特斯拉Model Y"],
  "aspects": ["价格", "续航", "智驾"]
}

// Response
{
  "request_id": "uuid",
  "session_id": "sess_xxx",
  "status": "success",
  "data": {
    "structured_params": { "问界M5": {"价格": ["24.98万"], ...}, ... },
    "llm_summary": "## 三车对比报告\n\n..."
  },
  "degraded": false,
  "latency_ms": 720
}
```

---

## 项目结构

```
agent_car/
├── config.py                    # 全局配置 (LLM/Redis/RabbitMQ/Milvus/限流)
├── docker-compose.yml           # 开发环境 (Redis+RabbitMQ, Milvus 可选)
├── Dockerfile                   # 容器化部署
├── supervisord.conf             # 多进程管理 (Gateway×2 + Worker×4)
├── requirements.txt
│
├── gateway/                     # 无状态 API 网关
│   ├── app.py                   # FastAPI 应用 + 三大路由 + 健康检查
│   ├── auth.py                  # API Key 鉴权
│   ├── rate_limit.py            # Redis Sorted Set 滑动窗口限流
│   ├── publisher.py             # RabbitMQ Direct Reply-to 发布者
│   └── schemas.py               # Pydantic 请求/响应模型
│
├── worker/                      # 任务消费者
│   ├── consumer.py              # aiormq 消费者主循环 + 队列绑定
│   ├── agent_factory.py         # 请求级 AgentForRequest 工厂 (共享 LLMPool)
│   └── session.py               # Redis 会话加载/保存管理器
│
├── agent/                       # Agent 核心 (请求级实例, 无全局状态)
│   ├── agent_core.py            # AutoSalesAgent (CLI) + AgentForRequest (v2)
│   ├── memory.py                # SessionMemory — Redis 后端会话隔离
│   ├── planning.py              # LLM 任务规划 → JSON ActionList
│   ├── reflection.py            # 质量评估 + 迭代控制
│   └── executor.py              # 工具调度 (支持并行组执行)
│
├── engine/                      # 业务规则引擎
│   ├── rule_engine.py           # 正则 + 关键字 → 标准化车型参数提取
│   ├── scorer.py                # LLM 多维度打分器 (性价比/安全/空间/智驾/售后/能耗)
│   └── comparator.py            # 多车型对比编排 (规则提取 + LLM 总结)
│
├── tools/                       # 工具组件
│   ├── base_tool.py             # 工具抽象基类
│   ├── rag_tool.py              # RAG 检索 (Milvus 混合检索 + LLM 回答)
│   ├── web_search_tool.py       # 联网搜索 (SerpAPI + 爬虫 + 语义重排)
│   └── calculator_tool.py       # 安全数学计算
│
├── infrastructure/              # 基础设施
│   ├── llm_pool.py              # httpx AsyncClient 异步 LLM 连接池
│   ├── embedding.py             # BGE-M3 本地 Embedding
│   ├── vector_db.py             # Milvus 向量库封装 (混合检索)
│   ├── metrics.py               # Prometheus 指标采集
│   └── doc_parser.py            # LlamaParse PDF 解析 + 切块
│
├── eval/                        # RAG 评测系统
│   ├── metrics.py               # 7 项评测指标
│   ├── dataset.py               # Golden Dataset 管理
│   ├── runner.py                # 批量评测 + 权重扫描
│   └── datasets/                # 评测数据集
│
├── frontend/                    # React 管理端
│   ├── backend/server.py        # 旧版 FastAPI (兼容 CLI 模式)
│   └── src/                     # TypeScript 前端 (三模式切换 + 设置 + 评测)
│
└── docs/superpowers/            # 设计文档和计划
    ├── specs/                   # 架构设计规格
    └── plans/                   # 实施计划
```

---

## 技术选型

### LLM 调用: DeepSeek API (OpenAI 兼容)

**为什么选择 DeepSeek?**
- **成本优势**: 价格约为 GPT-4 的 1/20，高并发场景下 API 费用可控
- **中文能力**: 在中文理解和生成上表现优异，汽车销售场景术语准确
- **OpenAI 兼容**: 标准 `/v1/chat/completions` 接口，零迁移成本，随时可切换为其他兼容服务

**v2 优化 — 异步连接池**:
- 旧版 5 处各自创建 `openai.OpenAI` 客户端，每次请求新建 TCP+TLS 连接
- v2 采用 `httpx.AsyncClient` 连接池 (默认 20 keep-alive 连接)，复用连接消除握手开销
- `LLMPool.chat()` 异步方法，Worker 事件循环内非阻塞调用

### Embedding: BGE-M3 本地模型

**为什么选择 BGE-M3?**
- **多语言 + 双向量**: 原生支持中英文，同时输出稠密向量 (1024d) 和稀疏词汇权重，单一模型完成两种检索
- **本地部署**: 无需调用外部 Embedding API，零网络延迟，无配额限制。2000 QPS 下调用外部 API 成本不可控
- **BGE 系列验证**: BGE-M3 在 MTEB 中文榜单上位居前列，BAAI 持续维护更新
- **每 Worker 独立加载**: 利用多进程天然并行，避免 GIL 限制

**为什么不用 OpenAI Embedding / Cohere?**
- 高并发下 API 调用费用线性增长
- 网络延迟不可控 (P99 可能高达 200ms+)
- 本地 BGE-M3 编码延迟 < 20ms，满足 P99 < 1s 时延预算

### 向量数据库: Milvus

**为什么选择 Milvus?**
- **混合检索原生支持**: `WeightedRanker` 同时融合稠密向量 (COSINE) 和稀疏向量 (IP) 的检索结果，无需应用层手动融合
- **多索引类型**: AUTOINDEX (稠密) + SPARSE_INVERTED_INDEX (稀疏)，覆盖两种向量类型
- **水平扩展**: 支持分布式部署，数据量增长时可通过增加节点扩展
- **生态成熟**: CNCF 毕业项目，文档完善，Python SDK 稳定

**为什么不用 ChromaDB / Qdrant / Elasticsearch?**
- ChromaDB 不支持真正的混合检索 (需手动融合)，缺乏生产级分布式能力
- Qdrant 混合检索晚于 Milvus，生态相对小
- Elasticsearch 向量检索为后期附加功能，非原生设计，稀疏向量支持有限

### 消息队列: RabbitMQ

**为什么选择 RabbitMQ?**
- **Direct Reply-to**: 天然支持 RPC 模式，Gateway 发布后直接等待 Worker 回复，无需额外回调队列或 correlation_id 轮询
- **Topic Exchange**: 按 `api.vehicle.query / api.vehicle.compare / api.recommend` 灵活路由，不同接口可独立扩缩消费能力
- **成熟可靠**: 30 年历史，AMQP 0-9-1 标准，管理 UI 完善，运维简单
- **持久化 + 死信**: `delivery_mode=persistent` 保证消息不丢失，`api.dlx` 死信队列统一处理超时/失败消息

**为什么不用 Kafka / Redis Streams?**
- Kafka 为高吞吐日志流设计，延迟在 10-100ms 级，RPC 模式的 request-reply 不是其设计场景
- Redis Streams 缺少 Topic Exchange 的灵活路由，消费者组模型重平衡有延迟
- RabbitMQ 的 RPC 模式在 P99 < 30ms (消息往返) 的时延预算下表现最优

### 缓存与会话: Redis

**为什么用 Redis 而不是仅靠 Worker 进程内存?**
- **多 Worker 共享状态**: Gateway 无状态 + 多 Worker 多进程，会话上下文必须在 Worker 间共享。Redis 是自然选择
- **Session TTL 自动过期**: 3600s 未活跃自动清除，无需手动 GC
- **滑动窗口限流**: Redis Sorted Set 天然支持 `ZREMRANGEBYSCORE + ZCARD` 组合，原子性保证计数准确
- **热点缓存**: 热门车型参数 (TTL 600s)、重复 RAG 查询结果 (TTL 300s) 缓存，减少 LLM 和 Milvus 调用

**为什么不用 SQLite / MySQL 做会话存储?**
- SQL 数据库为持久化设计，频繁的会话读写 (每请求 2 次) 不是其最优场景
- Redis 的 key-value 模式天然匹配会话生命周期，单次读写 < 1ms
- 长期记忆 (用户偏好) 实际持久层仍是 Milvus，Redis 为热读缓存

### API 框架: FastAPI + asyncio

**为什么选择 FastAPI?**
- **原生 async/await**: Gateway 的限流、发布、等待回复全链路异步，单进程可处理数千并发连接
- **Pydantic 集成**: 请求/响应自动校验和序列化，与 Python 类型系统无缝衔接
- **自动文档**: `/docs` (Swagger) 和 `/redoc` 零配置生成

**为什么不用 Flask / Django?**
- Flask 为同步 WSGI 框架，需要额外中间件 (如 gevent) 才能支持异步，且生态不如 asyncio 原生
- Django 过于重型，内置 ORM/模板/认证 本场景不需要，REST API 场景 FastAPI 更合适

### Embedding 模型部署: 每 Worker 进程独立加载

**为什么每进程加载一份 BGE-M3 (约 2GB/进程) 而不是单独部署 Embedding 服务?**
- **避免网络开销**: 本地直接调用 `sentence-transformers`，编码延迟 < 20ms。若独立部署为 HTTP 服务，增加网络往返 > 50ms
- **多进程天然并行**: Python GIL 限制单进程 CPU 利用率，多进程每进程独立模型副本可充分利用多核
- **权衡**: 内存换延迟。8 Worker × 2GB = 16GB 内存，对服务器配置可接受 (如需优化可评估 ONNX 量化版本 ~500MB)

### 前端: React + TypeScript + Ant Design

**为什么选择 React + Ant Design?**
- **Ant Design 5**: 企业级 UI 组件库，暗色主题，Table/Chart/Form 组件完备，适合管理端场景
- **TypeScript 严格模式**: API 类型与后端 Pydantic Schema 一一对应，编译期发现接口不一致
- **Vite 6 构建**: HMR 极速热更新，开发体验好
- **Context + useReducer**: 状态管理足够覆盖当前复杂度，无需引入 Redux

---

## 关键设计决策

### 会话隔离: Redis 三层 Memory

| 层 | 存储 | Key | 生命周期 |
|----|------|-----|----------|
| 短期记忆 | Redis List | `session:{id}:messages` (LTRIM 20) | TTL 3600s, 每次请求续期 |
| 长期记忆 | Milvus + Redis 缓存 | `user:{id}:prefs` | Milvus 永久, Redis 热缓存 |
| 请求上下文 | Worker 进程内存 | (局部变量) | 单次请求, 用完即弃 |

**设计理由**: 旧版全局单例 `get_agent()` 导致所有用户共享 `self.short_term`，多用户数据串扰。v2 改为请求级 `AgentForRequest` 实例 + Redis 持久化上下文，Worker 消费时加载、处理完保存，状态隔离且跨 Worker 可迁移。

### 请求级 Agent vs 全局单例

| 维度 | 旧版 AutoSalesAgent | v2 AgentForRequest |
|------|---------------------|-------------------|
| 实例生命周期 | 进程级全局单例 | 每请求创建/销毁 |
| 状态持有 | `self.memory.short_term` (进程内存) | Redis + 局部变量 |
| 并发安全 | 无保护，数据串扰 | 天然隔离 |
| LLM 客户端 | 独立 OpenAI 客户端 (TLS 每次握手) | 共享 LLMPool (keep-alive) |

### 异步解耦 Gateway ↔ Worker

Gateway 不直接执行 Agent 逻辑，而是通过 RabbitMQ 发布消息。这带来三个收益:
1. **Gateway 无状态秒级扩缩**: 纯鉴权+限流+发布，极其轻量
2. **Worker 故障隔离**: Worker OOM 或慢请求不阻塞 Gateway
3. **独立扩缩**: query 队列积压时只扩 Worker，不影响 Gateway

### 容错与降级

| 故障层 | 降级行为 | P99 影响 |
|--------|----------|----------|
| LLM API 超时/限流 | 返回 RAG 原始 + 规则引擎结果, `degraded=true` | +200ms |
| Milvus 不可用 | Redis 缓存兜底; 无缓存走 web_search | +100ms |
| Redis 不可用 | Worker 本地内存临时存储 | +50ms |
| RabbitMQ 不可用 | Gateway 返回 503 | 不可服务 |

---

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
cd agent_car
pip install -r requirements.txt

# 前端 (可选)
cd frontend && npm install
```

### 2. 基础设施

已有外部容器 (my-redis, my-rabbitmq1, milvus-standalone):
```bash
# 验证连通性
docker ps --filter "name=my-redis"
docker ps --filter "name=my-rabbitmq1"
# Milvus 端口
curl http://localhost:19530/healthz
```

从头启动 (Docker Compose):
```bash
# Redis + RabbitMQ
docker compose up -d

# Milvus 栈 (可选, 如已有 milvus-standalone 则跳过)
docker compose --profile milvus up -d
```

### 3. 配置

编辑 `.env`:

```env
LLM_API_KEY=sk-your-deepseek-api-key
LLM_API_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLAMAPARSE_API_KEY=llx-your-llamaparse-key
SERPAPI_API_KEY=your-serpapi-key
LOCAL_EMBEDDING_DEVICE=cuda

# 以下使用默认值即可
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
```

### 4. 启动

```bash
# 终端 1: Gateway
uvicorn gateway.app:app --host 0.0.0.0 --port 8000

# 终端 2: Worker
python -m worker.consumer

# 终端 3: 前端 (可选)
cd frontend && npm run dev
```

### 5. 索引知识库

```bash
# CLI 模式 (兼容旧版)
python main.py
> /index data/product.pdf
```

### 6. 调用示例

```bash
# 车型查询
curl -X POST http://localhost:8000/api/v1/vehicle/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ak_dev_001" \
  -d '{
    "session_id": "sess_001",
    "user_id": "user_001",
    "query": "问界M9的纯电续航是多少？"
  }'

# 多车对比
curl -X POST http://localhost:8000/api/v1/vehicle/compare \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ak_dev_001" \
  -d '{
    "session_id": "sess_001",
    "user_id": "user_001",
    "vehicles": ["问界M5", "理想L7", "特斯拉Model Y"],
    "aspects": ["价格", "续航", "智驾"]
  }'

# 智能推荐
curl -X POST http://localhost:8000/api/v1/recommend \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ak_dev_001" \
  -d '{
    "session_id": "sess_001",
    "user_id": "user_001",
    "scenario": "家用",
    "budget": "25-35万",
    "preferences": ["安全", "空间大", "省油"]
  }'
```

---

## API 接口

### v2 高并发接口 (Gateway)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 (含 Redis/RabbitMQ 状态) |
| `POST` | `/api/v1/vehicle/query` | 车型参数查询 |
| `POST` | `/api/v1/vehicle/compare` | 多车型横向对比 |
| `POST` | `/api/v1/recommend` | 场景化智能购车推荐 |
| `POST` | `/api/v1/session/close` | 关闭会话 (清除 Redis 会话数据) |

### 管理接口 (兼容旧版)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/config` | 获取配置 (API Key 脱敏) |
| `PUT` | `/api/config` | 运行时更新配置 |
| `POST` | `/api/upload-pdf` | 上传 PDF 并索引 |
| `GET` | `/api/eval/datasets` | 列出评测数据集 |
| `POST` | `/api/eval/run` | 运行 RAG 评测 |
| `POST` | `/api/eval/sweep` | 权重扫描评测 |

### 旧版 (deprecated)

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat` | [deprecated] 同步查询 |
| `WS` | `/ws/chat` | [deprecated] 流式查询 |

---

## 前端

管理端支持三种输入模式:

| 模式 | 说明 |
|------|------|
| 💬 车型查询 | 自然语言问题，RAG + LLM 回答 |
| 📊 多车对比 | 输入 2-5 个车型 + 可选对比维度，自动生成横向对比报告 |
| 🎯 智能推荐 | 输入场景/预算/偏好，规则筛选 + LLM 多维度打分排序 |

同时集成:
- **设置面板**: LLM/Embedding/API Key 可视化配置，PDF 拖拽上传
- **RAG 评测工作台**: 7 项指标雷达图 + 逐样本分析 + 权重扫描

---

## CLI 使用 (兼容旧版)

```bash
python main.py

你 > 问界M9的纯电续航里程是多少公里？
Agent > 问界M9纯电版搭载100kWh三元锂电池，CLTC工况纯电续航为630公里。增程版...

你 > 对比一下问界M9和理想L9
Agent > 基于产品资料，从空间、续航、价格、安全性四个维度对比...

你 > /state       # 查看 Agent 状态
你 > /history     # 查看对话历史
你 > /clear       # 清空会话
你 > /exit        # 退出
```

---

## 评测系统

7 项评测指标覆盖检索质量和生成质量，支持 Web 和 Python API 两种评测方式。

| 维度 | 指标 | 说明 |
|------|------|------|
| 检索 | Context Recall | 标注正样本被检索到的比例 |
| 检索 | Context Relevance | LLM 逐块判断检索内容相关性 |
| 检索 | MRR / NDCG@k | 排序质量 |
| 生成 | Faithfulness | LLM 蕴含判断 → claims 验证 |
| 生成 | Hallucination Rate | 1 - Faithfulness |
| 生成 | Answer Relevance | LLM 对答案-问题相关度评分 |

```python
from eval.runner import EvalRunner
from eval.dataset import GoldenDataset

ds = GoldenDataset.load("eval/datasets/auto_sales_eval_v1.0.json")
runner = EvalRunner(rag_tool, top_k=5)
report = runner.run(ds, retrieval_mode="hybrid", generate_answers=True)
print(f"Recall: {report.avg_context_recall:.2%}, MRR: {report.avg_mrr:.2%}")
```

---

## 资源估算

### 2000 QPS 峰值

| 组件 | 实例 | CPU/实例 | 内存/实例 |
|------|------|----------|-----------|
| Gateway | 2-4 | 0.5 | 256MB |
| Worker | 4-8 | 2 | 4GB (含 BGE-M3 ~2GB) |
| Redis | 1 | 2 | 4GB |
| RabbitMQ | 1 | 2 | 2GB |
| Milvus | 1 | 4 (GPU 推荐) | 8GB |

---

## 设计文档

- [高并发架构改造设计](docs/superpowers/specs/2026-06-03-high-concurrency-architecture-design.md)
- [高并发实施计划](docs/superpowers/plans/2026-06-03-high-concurrency-implementation-plan.md)
- [流式输出设计](docs/superpowers/specs/2026-05-22-streaming-output-design.md)
- [RAG 评测可视化设计](docs/superpowers/specs/2026-05-19-eval-visualization-phase2-design.md)

## License

MIT
