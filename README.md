# AutoSalesAgent — 高并发汽车销售 AI 平台

> **「组件化是核心，工作流是灵魂」** · v2 高并发架构

面向业务系统对接的企业级汽车销售 AI 平台。提供**车型查询 / 多车对比 / 智能推荐**三大 API 接口，采用 **Gateway + RabbitMQ + Worker Pool** 异步架构实现高吞吐，基于 **Redis 会话隔离 + JWT 用户认证** 支持多租户独立对话上下文，RAG 混合检索 + 规则引擎 + LLM 打分驱动场景化智能购车推荐。

---

## 架构

```
业务系统 ──▶ Nginx ──▶ FastAPI Gateway (无状态)
                         │  JWT 认证 / 限流 (Redis)
                         │  POST /api/v1/vehicle/*
                         ▼
                     RabbitMQ (Topic Exchange)
                    ╱    │    ╲
                   ▼     ▼     ▼
             Worker  Worker  Worker  (多进程)
               LLMPool · BGE-M3 · RAG · Engine
                         │
                    Milvus  +  Redis
                   (向量检索)  (会话/缓存/限流/用户)
```

### 数据流

```
Gateway 收到请求
  ├─ JWT 解析 → 用户身份
  ├─ Redis 滑动窗口限流
  ├─ 封装消息 → RabbitMQ (Direct Reply-to)
  │
Worker 消费消息
  ├─ Redis 加载 session:{id} → AgentForRequest
  ├─ Plan → Execute (RAG) → Generate → Reflect
  ├─ Redis 保存 session
  └─ 直接回复 Gateway → 返回
```

---

## 快速开始

### 1. 环境

```bash
pip install -r requirements.txt
cd frontend && npm install
```

### 2. 基础设施

```bash
# 已有容器 (my-redis, my-rabbitmq1, milvus-standalone)
docker ps --filter "name=my-redis"
docker ps --filter "name=my-rabbitmq1"

# 或从头启动
docker compose up -d
```

### 3. 配置 `.env`

```env
LLM_API_KEY=sk-your-deepseek-api-key
LLM_API_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLAMAPARSE_API_KEY=llx-your-key
SERPAPI_API_KEY=your-key
LOCAL_EMBEDDING_DEVICE=cuda

# 以下默认值通常无需修改
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
JWT_SECRET=change-me-in-production
```

> 所有用户共享同一套 `.env` 中的 API Key。注册/登录后的会话隔离由 Redis + JWT 保证。

### 4. 启动

```bash
# Gateway
uvicorn gateway.app:app --host 0.0.0.0 --port 8000

# Worker
python -m worker.consumer

# 前端
cd frontend && npm run dev
```

### 5. 索引知识库

前端设置页拖拽上传 PDF，或 CLI:

```bash
python main.py
> /index data/product.pdf
```

### 6. 调用

```bash
# 注册
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "sales01", "password": "123456"}'

# 登录 → 获取 token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "sales01", "password": "123456"}'

# 车型查询
curl -X POST http://localhost:8000/api/v1/vehicle/query \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess_001", "user_id": "sales01", "query": "问界M9续航"}'

# 多车对比
curl -X POST http://localhost:8000/api/v1/vehicle/compare \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess_001", "user_id": "sales01", "vehicles": ["问界M5","理想L7"], "aspects": ["价格","续航"]}'

# 智能推荐
curl -X POST http://localhost:8000/api/v1/recommend \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess_001", "user_id": "sales01", "scenario": "家用", "budget": "25-35万"}'
```

---

## 项目结构

```
agent_car/
├── config.py                          # 全局配置 (.env 覆盖)
├── .env                               # API Key (所有用户共享)
├── docker-compose.yml                 # 开发环境
├── Dockerfile                         # 容器化
├── supervisord.conf                   # 多进程管理
│
├── gateway/                           # 无状态 API 网关
│   ├── app.py                         # FastAPI 应用 (21 端点)
│   ├── auth.py                        # JWT + bcrypt + UserStore (Redis)
│   ├── rate_limit.py                  # Redis 滑动窗口限流
│   ├── publisher.py                   # RabbitMQ Direct Reply-to
│   └── schemas.py                     # Pydantic 模型
│
├── worker/                            # 任务消费者
│   ├── consumer.py                    # aiormq 消费者主循环
│   ├── agent_factory.py              # AgentForRequest 工厂 (共享 LLMPool)
│   └── session.py                     # Redis 会话管理器
│
├── agent/                             # Agent 核心
│   ├── agent_core.py                  # AutoSalesAgent (CLI) + AgentForRequest (v2)
│   ├── memory.py                      # SessionMemory (Redis 后端)
│   ├── planning.py                    # LLM 任务规划
│   ├── reflection.py                  # 反思迭代
│   └── executor.py                    # 工具调度 + 并行执行
│
├── engine/                            # 业务引擎
│   ├── rule_engine.py                 # 车型参数正则提取
│   ├── scorer.py                      # LLM 多维度打分
│   └── comparator.py                  # 多车型对比编排
│
├── tools/                             # 工具组件
│   ├── rag_tool.py                    # Milvus 混合检索 + LLM 回答
│   ├── web_search_tool.py             # SerpAPI + 爬虫
│   └── calculator_tool.py             # 安全计算
│
├── infrastructure/                    # 基础设施
│   ├── llm_pool.py                    # httpx 异步连接池
│   ├── embedding.py                   # BGE-M3 本地
│   ├── vector_db.py                   # Milvus 封装
│   └── doc_parser.py                  # PDF 解析
│
├── eval/                              # RAG 评测
│
└── frontend/                          # React 管理端
    └── src/
        ├── components/
        │   ├── LoginPage.tsx           # 登录/注册
        │   ├── Chat/                   # ChatPanel · ChatInput (三模式) · ChatHeader
        │   ├── Settings/               # SettingsDrawer (账户 + PDF上传)
        │   ├── Sidebar/                # 对话列表 · 知识库状态
        │   └── Trace/                  # 来源引用
        ├── services/api.ts             # REST + JWT 管理
        ├── store/                      # Context + Reducer
        └── types/index.ts              # TypeScript 类型
```

---

## API 接口

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/register` | 注册 (username + password → JWT) |
| `POST` | `/api/auth/login` | 登录 (返回 JWT token) |

### 业务接口 (需 Authorization: Bearer)

| 方法 | 路径 | P99 目标 |
|------|------|----------|
| `POST` | `/api/v1/vehicle/query` | ≤ 500ms |
| `POST` | `/api/v1/vehicle/compare` | ≤ 800ms |
| `POST` | `/api/v1/recommend` | ≤ 1000ms |

### 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/session/create` | 创建新会话 |
| `GET` | `/api/v1/sessions` | 列出用户所有活跃会话 |
| `POST` | `/api/v1/session/close` | 关闭会话 |

### 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 (Redis/RabbitMQ) |
| `GET` | `/api/config` | 全局配置 (只读, .env 脱敏) |
| `GET` | `/api/state` | Agent 状态 |
| `POST` | `/api/upload-pdf` | PDF 上传索引 |
| `GET` | `/api/eval/datasets` | 评测数据集列表 |
| `POST` | `/api/eval/run` | 运行评测 |
| `POST` | `/api/eval/sweep` | 权重扫描 |

---

## 技术选型

### LLM: DeepSeek API (OpenAI 兼容)

成本约为 GPT-4 的 1/20，中文能力强，标准 `/v1/chat/completions` 接口可随时切换。v2 使用 `httpx.AsyncClient` 连接池 (20 keep-alive) 消除 TLS 握手开销。

### Embedding: BGE-M3 本地

中英文双向量 (稠密 1024d + 稀疏词汇权重)，单个模型完成混合检索。本地部署零网络延迟 (< 20ms)，2000 QPS 下无需外部 API 费用。

### 向量库: Milvus

`WeightedRanker` 原生混合检索 (稠密 COSINE + 稀疏 IP)，无需应用层融合。CNCF 毕业项目，支持分布式。

### 消息队列: RabbitMQ

`Direct Reply-to` 天然支持 RPC 模式，Topic Exchange 灵活路由，AMQP 0-9-1 标准，管理 UI 完善。

### 缓存/会话: Redis

三层用途 — 会话存储 (Hash/List, TTL 3600s)、滑动窗口限流 (Sorted Set)、热点数据缓存。每请求 < 1ms 延迟。

### 认证: JWT + bcrypt

无状态 JWT token (HS256, 24h 过期)，密码 bcrypt 哈希存 Redis。Gateway 解析 token 获取用户身份，所有请求无需服务端 session。

### API 框架: FastAPI

原生 async/await，Pydantic 集成自动校验，`/docs` 零配置生成。

### 前端: React + TypeScript + Ant Design

TypeScript 严格类型与 Pydantic Schema 对应。Context + useReducer 状态管理。三模式输入 (查询/对比/推荐)。

---

## 关键设计

### 会话隔离

| 层 | 存储 | Key | 生命周期 |
|----|------|-----|----------|
| 短期记忆 | Redis List | `session:{id}:messages` (LTRIM 20) | TTL 3600s |
| 长期记忆 | Milvus | `user_long_term_memory` | 永久 |
| 请求上下文 | Worker 内存 | 局部变量 | 单次请求 |

每用户可创建多个 session，每个 session 独立对话上下文。切换前端对话自动切换 session_id。

### 容错降级

| 故障 | 降级 | 影响 |
|------|------|------|
| LLM 超时 | 返回 RAG 原始结果, `degraded=true` | +200ms |
| Milvus 不可用 | Redis 缓存兜底 → web_search | +100ms |
| Redis 不可用 | Worker 内存临时存储 | +50ms |
| RabbitMQ 不可用 | Gateway 503 | 不可服务 |

### 资源估算 (2000 QPS)

| 组件 | 实例 | CPU | 内存 |
|------|------|-----|------|
| Gateway | 2-4 | 0.5 | 256MB |
| Worker | 4-8 | 2 | 4GB |
| Redis | 1 | 2 | 4GB |
| RabbitMQ | 1 | 2 | 2GB |
| Milvus | 1 | 4 | 8GB |

---

## 评测系统

7 项指标: Context Recall, Relevance, MRR, NDCG, Faithfulness, Hallucination Rate, Answer Relevance。支持 Web 和 Python API。

```python
from eval.runner import EvalRunner
from eval.dataset import GoldenDataset

ds = GoldenDataset.load("eval/datasets/auto_sales_eval_v1.0.json")
report = EvalRunner(rag_tool, top_k=5).run(ds, retrieval_mode="hybrid")
print(f"Recall: {report.avg_context_recall:.2%}, MRR: {report.avg_mrr:.2%}")
```

---

## 设计文档

- [高并发架构改造设计](docs/superpowers/specs/2026-06-03-high-concurrency-architecture-design.md)
- [高并发实施计划](docs/superpowers/plans/2026-06-03-high-concurrency-implementation-plan.md)

## License

MIT
