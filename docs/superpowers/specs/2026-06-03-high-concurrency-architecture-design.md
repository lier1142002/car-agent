# AutoSalesAgent 高并发架构改造设计

> 状态: 已确认 | 日期: 2026-06-03 | 目标: 500-2000 QPS, P99 < 1s

---

## 1. 背景与目标

### 1.1 当前架构问题

AutoSalesAgent 当前是单用户/低并发架构，存在以下致命瓶颈：

| # | 瓶颈 | 严重度 | 影响 |
|---|------|--------|------|
| 1 | 全局 Agent 单例 (`get_agent()` 返回唯一实例) | 🔴 致命 | 多用户数据串扰，不可并发 |
| 2 | 同步阻塞 LLM 调用 (FastAPI async 端点内 `time.sleep` 等效阻塞) | 🔴 致命 | 阻塞事件循环 |
| 3 | 短期记忆存于进程内存 (`self.short_term: list`) | 🔴 致命 | 进程重启丢失，无法跨 Worker 共享 |
| 4 | 无连接池 (5 处各自创建 `OpenAI` 客户端) | 🟠 高 | TCP 连接浪费，TLS 握手开销 |
| 5 | BGE-M3 Embedding 全局单实例 | 🟠 高 | 无法并行编码，GPU 利用率低 |
| 6 | Milvus 全局连接 (`connections.connect`) | 🟠 高 | 非线程安全 |
| 7 | Executor 串行执行 Action | 🟡 中 | 独立工具调用无法并行 |
| 8 | 无速率限制/背压/会话隔离 | 🔴 致命 | 无法对外开放 API |

### 1.2 目标架构

```
业务系统 → Nginx → FastAPI Gateway (无状态) → RabbitMQ → Worker Pool → Milvus/Redis
```

- **三大对外接口**: 车型查询 / 多车对比 / 智能推荐
- **会话隔离**: Redis 持久化，每 session_id 独立上下文
- **异步解耦**: RabbitMQ Topic Exchange + Direct Reply-to
- **水平扩展**: Gateway/Worker 独立扩缩，无状态 Gateway 秒级扩容

### 1.3 新增基础设施

| 组件 | 用途 | 替代方案 |
|------|------|----------|
| Redis | 会话存储 / 热点缓存 / 滑动窗口限流 | — |
| RabbitMQ | 异步任务队列，Gateway↔Worker 解耦 | — |
| Nginx | 反向代理，TLS 终止，连接限流 | — |

---

## 2. 架构总览

### 2.1 三层架构

```
┌──────────────┐
│   Nginx LB   │  TLS 终止, rate_limit, proxy_pass
└──────┬───────┘
       │
  ┌────┴────────────────────┐
  │  FastAPI Gateway × N    │  无状态, async/await
  │  · 鉴权 (API Key)       │  · 参数校验 (Pydantic)
  │  · 限流 (Redis Sliding)  │  · publish → RabbitMQ
  └────────────┬────────────┘
               │
  ┌────────────┴────────────┐
  │       RabbitMQ          │  Topic Exchange: api.requests
  │  ┌────────┬──────────┐  │  3 队列: query / compare / recommend
  │  │ query  │ compare  │  │  Direct Reply-to 回复模式
  │  │ queue  │  queue   │  │
  │  └────┬───┴────┬─────┘  │
  │       │   recommend      │
  │       │    queue         │
  └───────┼────────┼─────────┘
          │
  ┌───────┴────────┴─────────┐
  │    Worker Pool × M       │  多进程, 每进程内嵌 BGE-M3
  │  · LLM 异步连接池        │  · RAG + Embedding
  │  · 规则引擎 + 打分       │  · Session 从 Redis 加载/保存
  └───────────┬──────────────┘
              │
  ┌───────────┴──────────────┐
  │  Milvus        Redis     │
  │  · 向量检索    · Session │
  │  · 知识库      · Cache   │
  │               · 限流     │
  └──────────────────────────┘
```

### 2.2 三大 API 接口

| 接口 | 方法/路径 | 核心流程 | P99 目标 |
|------|-----------|----------|----------|
| 车型查询 | `POST /api/v1/vehicle/query` | RAG 检索 → LLM 生成 | ≤ 500ms |
| 多车对比 | `POST /api/v1/vehicle/compare` | 并行 RAG × N → 规则引擎 → LLM 对比 | ≤ 800ms |
| 智能推荐 | `POST /api/v1/recommend` | 规则初筛 → 并行 RAG → LLM 多维打分 | ≤ 1000ms |

---

## 3. 会话隔离设计

### 3.1 核心思路

从「全局单例共享状态」改为「请求级 Agent 实例 + Redis 持久化上下文」。

```
Worker 消费消息:
  1. 从 Redis 加载 session:{id} 上下文
  2. 构建请求级 AgentForRequest(memory, session_id)
  3. 执行 Plan → Execute → Generate → Reflect
  4. 将更新后的 memory 写回 Redis
  5. 释放 AgentForRequest 实例
```

### 3.2 Memory 三层拆分

| 层 | 存储 | 数据结构 | 生命周期 |
|----|------|----------|----------|
| 短期记忆 | Redis | `session:{id}:messages` (List, LTRIM 20) | TTL 3600s, 每次请求续期 |
| 长期记忆 | Milvus + Redis 缓存 | Milvus 持久化向量, Redis Hash `user:{id}:prefs` | Milvus 永久, Redis 热缓存 |
| 请求上下文 | Worker 进程内存 | Python dict (局部变量) | 单次请求, 用完即弃 |

### 3.3 session_id 与 user_id 关系

- `session_id`: 单次对话会话标识 (短期, TTL 3600s)。业务系统可以为同一用户创建多个独立会话 (如不同购车场景)
- `user_id`: 用户唯一标识 (长期, 关联长期记忆)。session 创建时绑定 user_id, Worker 加载 session 后通过 `user:{id}:prefs` 读取用户偏好
- 一个 user_id 可有多个 session_id; 一个 session_id 严格绑定一个 user_id

### 3.4 会话生命周期

1. **创建**: 业务系统调用时传入 `session_id` + `user_id` (或由 Gateway 生成 UUID 返回)
2. **活跃**: 每次请求续期 Redis TTL (+3600s)
3. **隔离**: Worker 按 `session_id` 加载独立上下文, 不跨 session 访问
4. **过期**: TTL 到期自动清除; 支持主动 `POST /api/v1/session/close`

---

## 4. Redis Schema

| Key Pattern | 类型 | 字段/说明 | TTL |
|-------------|------|-----------|-----|
| `session:{id}` | Hash | created_at, last_access, user_id, preferences_json, message_count | 3600s |
| `session:{id}:messages` | List | 每项: `{role, content, tool_results, timestamp}` (LTRIM 20) | 3600s |
| `session:{id}:state` | Hash | iteration_count, last_actions(JSON), rag_queries(JSON) | 3600s |
| `user:{id}:prefs` | Hash | `preference:{type}` → value, 如 `preference:budget` → "35万" | 永久 |
| `ratelimit:{api_key}:{endpoint}` | Sorted Set | 滑动窗口时间戳 (score=timestamp, member=uuid) | 窗口时长 |
| `cache:vehicle:{model}` | String (JSON) | 车型参数/报价 JSON | 600s |
| `cache:rag:{query_hash}` | String (JSON) | RAG 检索结果快照 | 300s |

---

## 5. RabbitMQ Topology

### 5.1 Exchange & Queue

```
Exchange: api.requests  (type=topic, durable=true)

绑定:
  api.vehicle.query   → vehicle.query.queue
  api.vehicle.compare → vehicle.compare.queue
  api.recommend       → recommend.queue

死信: api.dlx (type=direct) — 超时/拒绝消息统一处理
```

### 5.2 队列参数

| 参数 | query | compare | recommend |
|------|-------|---------|-----------|
| prefetch_count | 20 | 10 | 10 |
| max_length | 10000 | 5000 | 5000 |
| message_ttl | 30s | 60s | 60s |
| delivery_mode | persistent | persistent | persistent |

### 5.3 消息格式

**Request** (Gateway → Worker):
```json
{
  "request_id": "uuid",
  "session_id": "sess_xxx",
  "api_key": "ak_xxx",
  "endpoint": "vehicle/compare",
  "payload": { "vehicles": ["M5","L7","Y"], "aspects": ["价格","续航"] },
  "timestamp": "2026-06-03T10:00:00Z",
  "reply_to": "amq.rabbitmq.reply-to"
}
```

**Response** (Worker → Gateway):
```json
{
  "request_id": "uuid",
  "session_id": "sess_xxx",
  "status": "success",
  "data": { "comparisons": [...], "summary": "...", "sources": [...] },
  "latency_ms": 850,
  "worker_id": "worker-3"
}
```

---

## 6. 模块重构

### 6.1 新模块结构

```
agent_car/
├── gateway/                    # 新增: FastAPI Gateway (无状态)
│   ├── __init__.py
│   ├── app.py                  # FastAPI 应用, 路由注册
│   ├── auth.py                 # API Key 鉴权
│   ├── rate_limit.py           # 滑动窗口限流
│   ├── publisher.py            # RabbitMQ 发布客户端
│   └── schemas.py              # 请求/响应 Pydantic 模型
│
├── worker/                     # 新增: Worker 消费者
│   ├── __init__.py
│   ├── consumer.py             # aiormq 消费者主循环
│   ├── agent_factory.py        # 请求级 Agent 实例工厂
│   ├── session.py              # Redis 会话加载/保存
│   └── health.py               # Worker 健康检查
│
├── agent/                      # 重构: 去全局单例
│   ├── agent_core.py           # AutoSalesAgent → AgentForRequest
│   ├── memory.py               # Memory → SessionMemory (Redis 后端)
│   ├── planning.py             # 保持核心逻辑, 移除独立 OpenAI 客户端
│   ├── reflection.py           # 保持核心逻辑
│   └── executor.py             # 保持核心逻辑, 支持并行执行
│
├── tools/                      # 重构: 共享连接池
│   ├── rag_tool.py             # RAG + Milvus (异步客户端)
│   ├── web_search_tool.py      # Web Search
│   ├── calculator_tool.py      # Calculator
│   └── base_tool.py            # BaseTool (异步接口)
│
├── infrastructure/             # 重构: 异步 + 连接池
│   ├── embedding.py            # BGE-M3 (每 Worker 进程独立实例)
│   ├── vector_db.py            # Milvus 异步客户端
│   ├── llm_pool.py             # 新增: LLM 异步连接池
│   └── doc_parser.py           # 保持
│
├── engine/                     # 新增: 规则引擎 + 打分
│   ├── __init__.py
│   ├── rule_engine.py          # 车型参数标准化提取
│   ├── scorer.py               # 多维度 LLM 打分
│   └── comparator.py           # 多车型对比编排
│
├── config.py                   # 扩展: Redis/RabbitMQ 配置
└── docker-compose.yml          # 新增: 一键部署
```

### 6.2 核心类重构

**AgentForRequest** (替代 AutoSalesAgent 单例):
```python
class AgentForRequest:
    """请求级 Agent — 无全局状态, 每次请求独立创建/销毁."""
    def __init__(self, session: SessionContext, llm_pool: LLMPool):
        self.session = session          # 从 Redis 加载的会话上下文
        self.memory = session.memory    # SessionMemory (Redis 后端)
        self.planning = PlanningModule(llm_client=llm_pool.acquire())
        self.reflection = ReflectionModule(llm_client=llm_pool.acquire())
        ...
```

**SessionMemory** (替代 Memory):
```python
class SessionMemory:
    """Redis 支持的会话记忆 — 加载/保存到 Redis."""
    def __init__(self, redis: Redis, session_id: str):
        self.redis = redis
        self.session_id = session_id
        self.short_term: list = []     # 从 Redis 加载
    
    @classmethod
    async def load(cls, redis, session_id) -> "SessionMemory": ...
    
    async def save(self) -> None: ...  # 写回 Redis
```

**LLMPool** (新增):
```python
class LLMPool:
    """异步 LLM 连接池 (httpx AsyncClient)."""
    def __init__(self, api_url: str, api_key: str, pool_size: int = 20):
        self.client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=pool_size),
            timeout=httpx.Timeout(30.0),
        )
    
    async def chat(self, messages, **kwargs) -> str: ...
```

---

## 7. 时延预算

### 7.1 车辆查询 (目标 ≤ 500ms)

| 阶段 | 操作 | 预算 |
|------|------|------|
| Gateway | 鉴权 + 校验 | ≤ 20ms |
| RabbitMQ | 发布 + 消费 | ≤ 30ms |
| Redis | 加载 Session | ≤ 10ms |
| Embedding | 编码 (或缓存命中) | ≤ 20ms |
| Milvus | 混合检索 | ≤ 50ms |
| LLM | 生成答案 | ≤ 300ms |
| Redis | 保存 Session | ≤ 10ms |
| 缓冲 | — | ≤ 60ms |

### 7.2 多车对比 (目标 ≤ 800ms)

| 阶段 | 操作 | 预算 |
|------|------|------|
| 并行 | Embedding × 3~5 | ≤ 60ms |
| 并行 | Milvus 检索 × 3~5 | ≤ 100ms |
| 规则引擎 | 参数提取 + 标准化 | ≤ 50ms |
| LLM | 对比生成 | ≤ 500ms |
| 缓冲 | — | ≤ 90ms |

### 7.3 智能推荐 (目标 ≤ 1000ms)

| 阶段 | 操作 | 预算 |
|------|------|------|
| 规则引擎 | 初筛 (Redis 车型缓存) | ≤ 20ms |
| 并行 | RAG × N 候选 | ≤ 150ms |
| LLM | 多维度打分 | ≤ 700ms |
| 缓冲 | — | ≤ 130ms |

---

## 8. 容错与降级

| 故障层 | 降级行为 | 恢复 | P99 影响 |
|--------|----------|------|----------|
| LLM API 超时/限流 | 返回 RAG 原始 + 规则引擎结果, 标记 `degraded=true` | 指数退避重试 (最多 2 次) | +200ms |
| Milvus 不可用 | Redis 缓存兜底; 无缓存走 web_search | 连接池自动重连 | +100ms (命中缓存) |
| Redis 不可用 | Worker 本地内存临时存储 (标记 volatile) | Sentinel 自动故障转移 | +50ms |
| RabbitMQ 不可用 | Gateway 返回 503, 业务系统重试 | Mirrored Queue + 快速重启 | 不可服务 |
| Embedding 模型 OOM | Worker 健康检查失败, Supervisor 重启进程 | Supervisor 自动重启 | +2000ms (冷重启) |

---

## 9. 可观测性

- **结构化日志**: JSON 格式, `trace_id` 从 Gateway → RabbitMQ header → Worker 全链路
- **Prometheus Metrics**: QPS, P50/P90/P99 延迟, 错误率 (4xx/5xx), 队列深度, LLM 调用耗时
- **健康检查**: Gateway `/health` (ready/live), Worker Supervisor 心跳, Milvus/Redis/RabbitMQ 连接状态

---

## 10. 部署方案

### 10.1 开发环境 (Docker Compose)

```yaml
services:
  nginx:       # 负载均衡
  gateway:     # FastAPI × 2
  rabbitmq:    # 消息代理
  redis:       # 会话/缓存/限流
  worker:      # Python 多进程
  milvus:      # 向量数据库 (standalone)
```

### 10.2 生产环境 (K8s)

- **Gateway**: Deployment × 2~4 replicas, HPA (CPU > 70%)
- **Worker**: Deployment × 4~8 replicas, HPA (队列深度)
- **Redis**: Sentinel 高可用 (1 Master + 2 Slave)
- **RabbitMQ**: Mirrored Queue, PersistentVolume
- **Milvus**: Standalone + GPU Node

### 10.3 资源估算 (2000 QPS 峰值)

| 组件 | Replicas | CPU/实例 | 内存/实例 |
|------|----------|----------|-----------|
| Gateway | 2~4 | 0.5 | 256MB |
| Worker | 4~8 | 2 | 4GB (含 BGE-M3) |
| Redis | 3 (Sentinel) | 2 | 4GB |
| RabbitMQ | 1 | 2 | 2GB |
| Milvus | 1 | 4 (GPU 推荐) | 8GB |

---

## 11. 实施分阶段计划

### Phase 1: 基础设施搭建 (Week 1)
- Docker Compose 环境 (Redis + RabbitMQ + Milvus)
- Redis Session Schema 实现
- RabbitMQ Topic Exchange + 队列创建

### Phase 2: Gateway 层 (Week 2)
- FastAPI 路由 + Pydantic Schemas
- API Key 鉴权 + 滑动窗口限流
- RabbitMQ Publisher (Direct Reply-to)

### Phase 3: Worker + Agent 重构 (Week 2-3)
- AgentForRequest 去单例化
- SessionMemory (Redis 后端)
- LLMPool 异步连接池
- Worker 消费者主循环 + Supervisor

### Phase 4: 业务逻辑 (Week 3-4)
- 车型查询 + RAG 管道
- 多车对比 + 规则引擎
- 智能推荐 + LLM 打分器
- 降级策略实现

### Phase 5: 验证上线 (Week 4-5)
- 压力测试 (Locust/k6) 验证 2000 QPS
- Prometheus + Grafana 监控面板
- 灰度发布 → 全量

---

## 12. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| LLM API 速率限制 | 2000 QPS 可能超过 DeepSeek 配额 | LLM 缓存命中率优化, 规则引擎直接返回占比提升 |
| Embedding 内存占用 | BGE-M3 每进程 ~2GB, 8 Worker = 16GB | 评估 onnx 量化版本 (~500MB) |
| RabbitMQ 单点 | 消息代理挂掉全链路不可用 | 生产环境 Quorum Queue + 集群 |
| 冷启动延迟 | Worker 重启后模型加载 ~5s | 预热脚本 + Graceful shutdown |

---

*设计确认: 2026-06-03 | 准备进入 implementation planning*
