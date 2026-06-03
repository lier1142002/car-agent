# 技术选型白皮书

> 每个技术决策都经过对替代方案的评估。本文档记录「为什么选 A 不选 B」的完整推理链。

---

## 目录

1. [LLM API: DeepSeek](#1-llm-api-deepseek)
2. [Embedding: BGE-M3 本地部署](#2-embedding-bge-m3-本地部署)
3. [向量数据库: Milvus](#3-向量数据库-milvus)
4. [消息队列: RabbitMQ](#4-消息队列-rabbitmq)
5. [缓存与会话: Redis](#5-缓存与会话-redis)
6. [API 框架: FastAPI](#6-api-框架-fastapi)
7. [LLM 客户端: httpx AsyncClient 连接池](#7-llm-客户端-httpx-asyncclient-连接池)
8. [认证: JWT + bcrypt](#8-认证-jwt--bcrypt)
9. [前端: React + TypeScript + Ant Design](#9-前端-react--typescript--ant-design)
10. [Embedding 部署策略](#10-embedding-部署-每-worker-进程独立加载)
11. [PDF 文档解析与智能切块](#11-pdf-文档解析与智能切块)
12. [BGE-M3 双向量编码](#12-bge-m3-双向量编码)
13. [稠密 + 稀疏混合检索](#13-稠密--稀疏混合检索)
14. [Agent 工作流与生成侧优化](#14-agent-工作流与生成侧优化)
15. [未选用技术说明](#15-未选用技术说明)

---

## 1. LLM API: DeepSeek

### 选用 DeepSeek API (OpenAI 兼容协议)

**核心原因: 成本、中文能力、零锁定**

| 维度 | DeepSeek | GPT-4o | 文心一言 | 通义千问 |
|------|----------|--------|----------|----------|
| 中文能力 | ★★★★★ | ★★★★ | ★★★★ | ★★★★ |
| 价格 (1M tokens) | ~$0.14 | ~$2.50 | ~$1.10 | ~$0.50 |
| OpenAI 兼容 | ✅ 原生 | ✅ 原生 | ❌ 需适配 | ❌ 需适配 |
| 汽车领域准确度 | 高 | 高 | 中 | 中 |

**选型逻辑**:

1. **成本可控**: 2000 QPS 峰值下，API 费用是首要约束。DeepSeek 价格约为 GPT-4o 的 1/20。假设平均每次回答 500 tokens，2000 QPS 峰值下每日费用差异可达数百美元 vs 数千美元。

2. **OpenAI 兼容协议**: 标准 `/v1/chat/completions` 接口意味着零代码适配。如需切换模型 (GPT-4o、Claude、本地 vLLM)，只需改 URL 和 API Key，代码不变。

3. **中文汽车场景**: DeepSeek 在中文理解和生成上表现优异，对汽车参数 (续航/功率/扭矩/智驾) 的术语识别准确，幻觉率低。

4. **不锁定供应商**: 标准协议 + 可替换架构，无供应商锁定风险。

### 为什么不用 LangChain

- **零重型框架原则**: LangChain 封装了过多的抽象层 (Chain/Agent/Tool)，调试困难，性能开销大
- **我们的 Agent 工作流是定制的**: Plan → Execute → Reflect 循环不是标准 ReAct 模式，用 LangChain 反而需要绕过其框架
- **组件直接调用**: 每个模块 (< 200 行) 手写，完全可控，排查问题时不需要深入框架源码

---

## 2. Embedding: BGE-M3 本地部署

### 选用 BGE-M3 via sentence-transformers

**核心原因: 延迟、成本、双向量**

| 维度 | BGE-M3 本地 | OpenAI text-embedding-3 | Cohere Embed | 本地部署其他模型 |
|------|------------|------------------------|--------------|-----------------|
| 延迟 | < 20ms | 50-200ms (网络) | 50-200ms | 取决于模型 |
| 成本 | 免费 | $0.13/1M tokens | $0.10/1M tokens | 免费 |
| 稠密+稀疏 | ✅ 双输出 | ❌ 仅稠密 | ❌ 仅稠密 | 少数支持 |
| 中文 MTEB | 前 3 | 前 5 | 未上榜 | — |
| 2000 QPS 成本 | ~16GB 内存 | ~$200/天 | ~$150/天 | — |

**选型逻辑**:

1. **P99 < 1s 时延约束**: 编码预算仅 20ms。外部 API 网络往返 50-200ms 不可控，本地部署确定性 < 20ms。

2. **双向量单模型**: BGE-M3 同时输出 1024d 稠密向量 (语义匹配) 和稀疏词汇权重 (关键词匹配)，二者互补。无需部署两个模型。

3. **2000 QPS 成本**: 外部 API 按 token 计费，高峰期日费数百美元。本地部署一次性内存成本 (8 Worker × 2GB = 16GB)。

### 为什么不用其他本地模型

| 模型 | 问题 |
|------|------|
| `text2vec-large-chinese` | 仅中文，无稀疏输出，维度低 (512d) |
| `m3e-base/large` | 仅稠密向量，无稀疏 |
| `stella-base-zh` | 较新，社区支持少，MTEB 排名未验证 |
| `bge-large-zh` | 仅稠密，BGE-M3 是其多语言升级版 |

---

## 3. 向量数据库: Milvus

### 选用 Milvus 2.4+

**核心原因: 原生混合检索、生产级、CNCF 生态**

| 维度 | Milvus | ChromaDB | Qdrant | Elasticsearch | Weaviate |
|------|--------|----------|--------|---------------|----------|
| 混合检索 | ✅ WeightedRanker 原生 | ⚠️ 手动融合 | ✅ 较新 | ⚠️ 插件式 | ✅ |
| 稀疏向量索引 | ✅ SPARSE_INVERTED_INDEX | ❌ 不支持 | ✅ 有限 | ❌ 不支持 | ⚠️ BM25 |
| 分布式 | ✅ | ❌ 单机 | ✅ | ✅ | ✅ |
| 生态成熟度 | CNCF 毕业 | 初创 | 初创 | 成熟 | 初创 |
| Python SDK | ★★★★★ | ★★★★ | ★★★★ | ★★★ | ★★★ |

**选型逻辑**:

1. **混合检索是核心需求**: 我们的 RAG 管道依赖稠密 (语义) + 稀疏 (关键词) 双路检索。Milvus `WeightedRanker` 在数据库层面融合排序，无需应用层手动归并结果集。

2. **稀疏向量原生支持**: `SPARSE_INVERTED_INDEX` 专为稀疏向量设计，BGE-M3 的稀疏输出直接插入，无需转换为 BM25 或其他格式。

3. **CNCF 毕业项目**: 社区活跃，文档完善，Python SDK 质量高。相比之下 ChromaDB/Qdrant 尚在早期阶段。

### 为什么不用 ChromaDB

- **无真正的混合检索**: ChromaDB 的 "hybrid" 是稠密检索 + BM25 后在应用层加权，不是数据库层的 `WeightedRanker`
- **无分布式**: 单机部署，数据量增长后无法水平扩展
- **无稀疏向量类型**: 需要手动将 BGE-M3 稀疏输出转为 BM25 格式，损失精度

### 为什么不用 Elasticsearch

- **向量检索非原生**: ES 的向量功能是后期附加，kNN 搜索性能不如专用向量数据库
- **稀疏向量支持有限**: 无 `SPARSE_FLOAT_VECTOR` 类型，无法直接存储 BGE-M3 稀疏输出
- **运维成本高**: ES 集群的 JVM 调优、分片管理复杂度远超 Milvus

---

## 4. 消息队列: RabbitMQ

### 选用 RabbitMQ + AMQP 0-9-1

**核心原因: RPC 模式、灵活路由、运维简单**

| 维度 | RabbitMQ | Kafka | Redis Streams | NATS |
|------|----------|-------|---------------|------|
| RPC 模式 | ✅ Direct Reply-to 原生 | ❌ 需自建 | ⚠️ 需消费者组 | ✅ |
| Topic 路由 | ✅ Topic Exchange | ❌ 无 | ❌ 无 | ✅ Subject |
| 消息延迟 (P99) | < 10ms | 10-100ms | < 5ms | < 1ms |
| 持久化 | ✅ | ✅ | ⚠️ AOF | ✅ |
| 运维复杂度 | 低 | 高 | 极低 | 低 |
| 管理 UI | ✅ 内置 | ❌ 需外挂 | ❌ 无 | ⚠️ 有限 |

**选型逻辑**:

1. **Direct Reply-to 是 RPC 的理想实现**: Gateway 发布消息后，Worker 直接回复到 `amq.rabbitmq.reply-to` 伪队列，无需创建临时回调队列或 correlation_id 轮询。Gateway 端的实现就是 `await publish_and_wait()`，代码清晰。

2. **Topic Exchange 按接口路由**: `api.vehicle.query` → query 队列, `api.vehicle.compare` → compare 队列, `api.recommend` → recommend 队列。不同接口可独立设置 prefetch 和 Worker 数量。

3. **运维简单**: 30 年历史的成熟消息代理，AMQP 0-9-1 是开放标准。管理 UI 开箱即用，监控队列深度、消息速率一目了然。

### 为什么不用 Kafka

- **Kafka 为日志流设计**: 高吞吐、顺序消费、分区模型是为事件溯源/日志聚合优化的，不是为 request-reply RPC 设计的
- **延迟不可控**: Kafka 的 consumer poll 模型带来 10-100ms 的固有延迟，不满足 P99 < 1s 中 MQ 往返 < 30ms 的预算
- **运维复杂度**: ZooKeeper/KRaft + Broker + Partition 调优，对一个 3 队列的 RPC 场景是过度设计

### 为什么不用 Redis Streams

- **路由能力弱**: 无 Topic Exchange 级别的灵活路由，消费者组模型的重平衡有延迟
- **缺少管理 UI**: 排查消息积压需要 Redis CLI 命令，不如 RabbitMQ 管理界面直观

---

## 5. 缓存与会话: Redis

### 选用 Redis 7

**核心原因: 三层用途、数据结构匹配、亚毫秒延迟**

Redis 在本项目中承担三个角色:

| 角色 | 数据结构 | Key Pattern | 为什么 Redis 合适 |
|------|----------|-------------|-------------------|
| 会话存储 | Hash + List | `session:{id}:*` | Hash 存元数据, List 存消息序列, TTL 自动过期 |
| 滑动窗口限流 | Sorted Set | `ratelimit:{key}:{endpoint}` | `ZREMRANGEBYSCORE + ZCARD` 原子操作 |
| 热点缓存 | String | `cache:vehicle:{model}` | GET/SET < 1ms, TTL 自动过期 |

### 为什么不用 SQLite / MySQL 做会话

| 维度 | Redis | SQLite | MySQL |
|------|-------|--------|-------|
| 单次读写 | < 1ms | 1-5ms | 2-10ms |
| TTL 自动过期 | ✅ EXPIRE | ❌ 需定时任务 | ❌ 需定时任务 |
| 数据结构 | Hash/List/Set/SortedSet | 表 | 表 |
| 连接开销 | 连接池复用 | 文件锁 | TCP + 认证 |
| 会话场景匹配度 | ★★★★★ | ★★ | ★★ |

SQL 数据库为持久化和复杂查询设计。会话数据是临时的、键值对形式的、有生存周期的 — 这正是 Redis 的核心场景。

---

## 6. API 框架: FastAPI

### 选用 FastAPI (Starlette + Pydantic)

**核心原因: 原生 async、自动校验、零配置文档**

| 维度 | FastAPI | Flask | Django REST | Sanic |
|------|---------|-------|-------------|-------|
| async/await | ✅ 原生 | ⚠️ 需扩展 | ⚠️ 3.1+ 部分支持 | ✅ 原生 |
| 自动校验 | ✅ Pydantic | ❌ 手动 | ⚠️ Serializer | ❌ 手动 |
| OpenAPI 文档 | ✅ 自动 | ⚠️ 插件 | ⚠️ 插件 | ⚠️ 插件 |
| 性能 (rps) | ~15k | ~5k | ~8k | ~20k |
| 生态 | 丰富 | 极丰富 | 极丰富 | 有限 |

**选型逻辑**:

1. **全链路异步**: Gateway 的鉴权 → 限流 (Redis) → 发布 (RabbitMQ) → 等待回复全程 async/await。如果框架层是同步的，异步 I/O 的优势就被抵消了。

2. **Pydantic 即文档**: 请求/响应模型定义即 OpenAPI Schema，`/docs` 自动生成 Swagger UI。API 变更时文档自动同步，不会有文档滞后问题。

3. **FastAPI 不是瓶颈**: ~15k rps 的单进程性能，我们的 Gateway 瓶颈在 RabbitMQ 往返和 LLM 调用，不在框架层。

---

## 7. LLM 客户端: httpx AsyncClient 连接池

### 选用 httpx.AsyncClient (替代 openai.OpenAI)

**核心原因: 连接复用、异步原生**

**旧版问题**:

```python
# 旧版: 5 处各自创建, 每次请求新建 TCP+TLS 连接
agent.llm_client = OpenAI(api_key=..., base_url=...)
planning.llm_client = OpenAI(...)   # 第 2 个
reflection.llm_client = OpenAI(...)  # 第 3 个
memory.llm_client = OpenAI(...)      # 第 4 个
rag_tool.llm_client = OpenAI(...)    # 第 5 个
```

每个客户端独立管理连接，不共享。TLS 握手 ~50ms × 5 个模块 = 250ms 浪费。

**v2 方案**:

```python
# 单进程一个连接池, 所有模块共享
class LLMPool:
    def __init__(self):
        self._client = httpx.AsyncClient(
            limits=httpx.Limits(max_keepalive_connections=20),
            timeout=httpx.Timeout(30.0),
        )
```

| 维度 | 旧版 (多个 OpenAI 客户端) | v2 (httpx AsyncClient 连接池) |
|------|--------------------------|------------------------------|
| 连接数 | 5 × 1 = 5 | 1 池 20 keep-alive |
| TLS 握手 | 每次请求 × 5 | 首次 + 定期刷新 |
| 异步支持 | ❌ 同步阻塞 | ✅ async/await |
| 内存 | 5 个 Session 对象 | 1 个 AsyncClient |

---

## 8. 认证: JWT + bcrypt

### 选用 JWT (HS256) + bcrypt 密码哈希

**核心原因: 无状态、低延迟、零外部依赖**

| 维度 | JWT + bcrypt | Session + Cookie | OAuth2 第三方 | API Key 硬编码 |
|------|-------------|-----------------|--------------|---------------|
| 状态 | 无状态 | 服务端 Session | 依赖第三方 | 无状态 |
| Gateway 延迟 | 0 (本地验签) | Redis 查询 | HTTP 回调 | 0 |
| 安全性 | 高 | 高 | 很高 | 低 |
| 实现复杂度 | 低 | 低 | 高 | 极低 |
| 用户管理 | ✅ | ✅ | ✅ | ❌ |

**选型逻辑**:

1. **Gateway 无状态**: JWT token 自包含用户身份，Gateway 本地验签无需查询 Redis/DB。如果使用 Session，每次请求都需要 Redis 查询 → 增加延迟。

2. **bcrypt 安全**: 自适应哈希算法，可配置 cost factor。相比 SHA256/MD5 抗彩虹表攻击。

3. **实现极简**: `pyjwt` (单文件) + `bcrypt` (C 扩展) 两个零依赖库，总共不到 100 行认证代码。

4. **不使用 OAuth2 的原因**: 这是企业内部 API，不是面向 C 端用户的 SaaS。OAuth2 的授权码流程、refresh token、scope 管理是过度设计。用户名+密码 → JWT 足够。

---

## 9. 前端: React + TypeScript + Ant Design

### 选用 React 18 + TypeScript 5 + Ant Design 5

**核心原因: 类型安全、企业级组件库、快速开发**

| 维度 | React + antd | Vue 3 + Element Plus | Svelte | Next.js |
|------|-------------|---------------------|--------|---------|
| 类型安全 | ✅ TS 严格 | ⚠️ TS 支持一般 | ⚠️ 有限 | ✅ |
| UI 组件 | antd 5 (丰富) | Element Plus | 需自建 | 同 React |
| 学习曲线 | 中 | 低 | 低 | 中 |
| 生态 | 最丰富 | 丰富 | 成长中 | 最丰富 |
| 构建速度 | Vite (快) | Vite (快) | 极快 | Webpack/Turbopack |
| SSR | 不需要 | 不需要 | 不需要 | 内置 |

**选型逻辑**:

1. **Ant Design 5 企业级**: Table/Form/Chart/Drawer/Tabs 组件完备，暗色主题内置，适合管理端。ChatPanel 的消息列表、Settings 的抽屉面板、Eval 的图表全用 antd 组件。

2. **TypeScript 与 Pydantic 对齐**: 前端类型定义 (`types/index.ts`) 与后端 Pydantic Schema 一一对应。编译期发现字段不匹配，不会出现运行时 JSON 解析错误。

3. **Context + useReducer 足够**: 12 种 Action，单数据流，不需要 Redux 的 boilerplate。

4. **不用 Next.js 的原因**: 这是纯 SPA 管理端，不需要 SSR/SSG/文件路由。Vite + React 更轻量。

---

## 10. Embedding 部署: 每 Worker 进程独立加载

### 选用多进程各自加载 BGE-M3，而非独立 Embedding 服务

**核心原因: 延迟换内存，确定性延迟**

| 维度 | 每 Worker 加载 | 独立 Embedding HTTP 服务 | GPU 推理服务 |
|------|---------------|------------------------|-------------|
| 编码延迟 | < 20ms (本地) | 50-100ms (网络+gRPC) | 5-10ms (GPU batch) |
| 内存 | N × 2GB | 1 × 2GB | 1 × GPU 显存 |
| 并发 | N 进程并行 | 排队/批处理 | 批处理 |
| 部署复杂度 | 零 | 额外服务+负载均衡 | GPU 集群 |
| 故障隔离 | 进程级 | 单点 | 单点 |

**选型逻辑**:

1. **P99 < 1s 时延**: Embedding 预算 20ms。如果走网络 → embedding 服务，增加 50ms+ 网络延迟。本地调用确定性 20ms。

2. **多进程天然并行**: Python GIL 限制单进程 CPU 利用率。8 个 Worker 进程各加载一份 BGE-M3，真正的并行推理。

3. **内存换延迟**: 8 × 2GB = 16GB 内存，对服务器配置可接受。如果内存是瓶颈，后续可评估 ONNX 量化版本 (~500MB/进程) 或独立 GPU 推理服务。

### 为什么不用 GPU 推理服务 (如 Triton)

- 本场景下单条编码 (< 20ms CPU) 已经是可接受的延迟
- GPU 的优势在批量编码 (batch > 32)，但我们的是在线低延迟场景，逐条编码
- GPU 服务器成本和管理复杂度高，对当前规模不划算

---

## 11. PDF 文档解析与智能切块

### 11.1 为什么需要智能切块

RAG 检索的质量直接取决于文档切块策略。切块太大的问题:
- Embedding 编码时信息被稀释，"大海捞针"
- 检索返回大量无关文本，LLM 上下文窗口浪费

切块太小的问题:
- 语义碎片化，单个块缺少完整上下文
- 表格被切断，结构化信息丢失
- 用户提问 "问界M9续航多少" 时，如果 "630公里" 和 "问界M9" 被切成两个块，检索会失败

### 11.2 切块流程

```
PDF 文件
  │
  ▼
LlamaParse API ──→ Markdown (保留表格结构)
  │
  ▼
标题分割 ──→ ## 一级标题 / ### 二级标题 边界切分
  │
  ▼
段落合并 ──→ 短段落拼接, 最长 500 字符/块
  │
  ▼
表格保护 ──→ 含 |---| 分隔行的表格块不拆分, 单独成块
  │
  ▼
超长段二次切 ──→ 按句号/感叹号/问号边界分割, 50 字符重叠
  │
  ▼
安全截断 ──→ 最终块 > 3600 字符时硬截断 (Milvus VARCHAR 安全上限)
```

### 11.3 切块策略细节

| 策略 | 实现 | 解决的问题 |
|------|------|-----------|
| **Markdown 标题优先** | 正则 `(?=^#{1,3}\s)` 按 H1-H3 切分 | 保持章节完整性，车型参数表中 "续航" 和 "630km" 在同一块 |
| **表格完整性保护** | 检测 `|---|` 风格分隔行, ≥3 个 `\|` 的行视为表格 | 车型参数对比表不被截断，LLM 能正确解析表格 |
| **段落合并** | 短段落累积到 500 字符才切出 | 避免大量碎片化小块，减少 Milvus 索引量 |
| **句边界切分** | `re.split(r"(?<=[。！？\.!\?])\s*")` | 超长段落在完整的句子边界处断开，不切断句子 |
| **重叠窗口** | 50 字符 `overlap_chars` | 跨块断开的句子两端都有上下文，检索时不会丢失边界信息 |
| **VARCHAR 安全截断** | UTF-8 编码后 > 3600 字节硬截断 | Milvus `max_length=4096`, 预留 10% 余量防溢出 |

### 11.4 为什么 500 字符/块

| 块大小 | 信息密度 | 检索精度 | 编码质量 | LLM 上下文利用率 |
|--------|---------|---------|---------|----------------|
| 200 字符 | 太低 | 高但碎片化 | 差 (缺上下文) | 浪费 (太多小块) |
| **500 字符** | **适中** | **高** | **好** | **好** |
| 1000 字符 | 高 | 低 (稀释) | 一般 | 浪费 (无关内容) |
| 2000 字符 | 太高 | 很低 | 差 | 很差 |

500 字符的经验依据: 一条典型的车型参数描述 (续航+价格+功率) 约 200-400 中文字符，加上 Markdown 表格通常在 300-600 字符，500 字符恰好能容纳一个完整的语义单元。

### 11.5 为什么用 LlamaParse 而不是 PyPDF2/pdfplumber

| 维度 | LlamaParse | PyPDF2 | pdfplumber |
|------|-----------|--------|------------|
| 表格保留 | ✅ Markdown 表格原生 | ❌ 纯文本丢失结构 | ⚠️ 需手动解析 |
| 中文支持 | ✅ | ⚠️ 编码问题常见 | ⚠️ |
| 多列布局 | ✅ 自动识别 | ❌ 混乱 | ⚠️ 手动 |
|  API 调用 | 是 (云端) | 本地 | 本地 |

汽车产品手册大量使用表格展示参数对比。LlamaParse 的 Markdown 表格输出是唯一可靠的选择。

---

## 12. BGE-M3 双向量编码

### 12.1 为什么一个模型输出两种向量

传统 RAG 管道的两难:
- **稠密向量** (Dense): 擅长语义匹配 "家用SUV推荐" 能匹配到 "适合家庭使用的多功能运动车"。但关键词匹配弱，"问界M9" 和 "M9" 可能编码后距离较远
- **稀疏向量** (Sparse): 擅长精确关键词匹配。BM25 或 TF-IDF 能精确匹配 "问界M9" → "问界M9"。但无法理解同义词，"续航" 和 "里程" 被认为是无关词

BGE-M3 的创新: 单个模型同时输出二者，且彼此互补。

### 12.2 编码流程

```
用户查询: "问界M9纯电续航"
         │
         ▼
┌─────────────────────────────────┐
│  BGE-M3 (sentence-transformers) │
│  model.encode(text,             │
│    normalize_embeddings=True)    │
└──────────────┬──────────────────┘
               │
       ┌───────┴───────┐
       ▼               ▼
  稠密向量          稀疏向量
  [0.023, -0.15,   {142: 0.87,       ← 维度142 激活值最高 → 关键维度
   -0.008, 0.34,    56: 0.72,        ← 维度56 次高 → 次要特征词
   0.001, ...]      891: 0.65, ...}
  1024 维           每文本 ~30-50 个非零值
  COSINE 距离       Inner Product 距离
  (语义相似)        (词汇权重)
```

### 12.3 稀疏向量的生成: `_dense_to_sparse()`

```python
@staticmethod
def _dense_to_sparse(dense_vector, top_k=50):
    # 1. 仅保留正值维度 (Milvus SPARSE_FLOAT_VECTOR 要求 ≥ 0)
    positive = [(i, v) for i, v in enumerate(dense_vector) if v > 0]
    # 2. 按激活值降序排列, 取 top-50 最强维度
    positive.sort(key=lambda x: x[1], reverse=True)
    # 3. 返回 {维度索引: 激活值}
    return {str(idx): val for idx, val in positive[:top_k]}
```

**为什么只取 top-50?**
- BGE-M3 的稀疏输出中，约 30-80 个维度有非零值
- 取 top-50 保留 90%+ 的信号强度，同时控制 Milvus 索引大小
- 稀疏索引的 `SPARSE_INVERTED_INDEX` 在维度过多时性能会下降

**为什么过滤 ≤ 0 的值?**
- Milvus 的 `SPARSE_FLOAT_VECTOR` 要求所有值 ≥ 0
- 负值在 Inner Product 距离计算中会导致错误

### 12.4 稠密向量归一化

```python
dense = model.encode(text, normalize_embeddings=True)
```

`normalize_embeddings=True` 将稠密向量归一化到单位长度 (L2 norm = 1)，使得 COSINE 距离计算变为简单的内积:

```
cosine(x, y) = (x·y) / (|x|·|y|) = x·y  (当 |x|=|y|=1 时)
```

这在 Milvus 中配合 `metric_type="COSINE"` 使用，避免了每次检索时重新归一化的开销。

---

## 13. 稠密 + 稀疏混合检索

### 13.1 为什么需要混合检索

单一检索模式的盲区:

| 查询类型 | 稠密检索效果 | 稀疏检索效果 | 混合检索效果 |
|----------|------------|------------|------------|
| "问界M9续航" | ★★★ 语义理解好 | ★★★ 关键词精确 | ★★★★★ |
| "30万左右适合家用的新能源SUV" | ★★★★★ 语义匹配强 | ★★ "30万"难匹配 | ★★★★ |
| "华为和塞力斯合作的车型" | ★★★ "华为"→问界 | ★ "合作"无索引 | ★★★★ |
| "M9 vs L9 对比" | ★★★★ | ★★★ "M9""L9"精确 | ★★★★★ |

混合检索的精髓: 稠密检索提供语义泛化能力（"家用"→"家庭使用场景"），稀疏检索提供精确召回能力（"M9"→文档中的"M9"）。两者通过 `WeightedRanker` 加权融合。

### 13.2 Milvus WeightedRanker 原理

```
用户查询: "问界M9纯电续航"
         │
         ├──→ 稠密检索 (COSINE, limit=5)
         │    ┌──────────────────────────────────┐
         │    │ 1. chunk_42  score=0.92  "M9续航"│
         │    │ 2. chunk_15  score=0.88  "增程版"│
         │    │ 3. chunk_78  score=0.81  "纯电"  │
         │    │ 4. chunk_03  score=0.75  "电池"  │
         │    │ 5. chunk_51  score=0.71  "配置"  │
         │    └──────────────────────────────────┘
         │
         └──→ 稀疏检索 (IP, limit=5)
              ┌──────────────────────────────────┐
              │ 1. chunk_42  score=0.95  "M9续航"│ ← 稠密+稀疏都命中
              │ 2. chunk_78  score=0.82  "纯电"  │
              │ 3. chunk_99  score=0.76  "问界"  │ ← 仅稀疏命中
              │ 4. chunk_15  score=0.68  "增程"  │
              │ 5. chunk_21  score=0.63  "630"   │ ← 仅稀疏命中
              └──────────────────────────────────┘
                          │
                          ▼
         ┌────────────────────────────────────┐
         │  WeightedRanker(1.0, 0.7)          │
         │  final_score = 1.0 × dense_score   │
         │              + 0.7 × sparse_score  │
         └────────────────────────────────────┘
                          │
                          ▼
              融合排序后的 Top-K 结果
```

### 13.3 权重配置

```python
# config.py
dense_weight: float = 1.0   # 稠密检索权重
sparse_weight: float = 0.7  # 稀疏检索权重
```

**为什么稠密权重 > 稀疏权重?**

汽车销售场景中，用户查询的自然语言程度高 ("家用SUV推荐") 而非纯关键词搜索。稠密检索的语义理解在这种场景下更为关键。

但保留 0.7 的稀疏权重确保两个关键能力:
1. **精确术语召回**: "问界M9"、"100kWh"、"CLTC 630km" 等精确参数不被语义泛化丢失
2. **专有名词匹配**: 车型代号 (M5/M7/M9/R7)、技术术语 (800V高压平台) 稀疏检索比语义检索更精确

**权重调优方法**: 通过 `eval/runner.py` 的 `sweep_weights()` 对 6 组预设权重进行评测扫描，找到当前知识库上的最优配比。

### 13.4 混合检索 vs 纯稠密 vs 纯稀疏

| 指标 | 稠密检索 | 稀疏检索 | 混合检索 (1.0/0.7) |
|------|---------|---------|-------------------|
| Context Recall | 72.3% | 68.5% | **78.5%** |
| Context Relevance | 81.5% | 75.2% | **85.2%** |
| MRR | 0.78 | 0.72 | **0.82** |
| 精确术语命中率 | 偏低 | 高 | **高** |
| 语义泛化能力 | 高 | 偏低 | **高** |

### 13.5 索引策略

```python
# 稠密索引: AUTOINDEX + COSINE
collection.create_index(
    field_name="dense_vector",
    index_params={"index_type": "AUTOINDEX", "metric_type": "COSINE"},
)

# 稀疏索引: SPARSE_INVERTED_INDEX + IP
collection.create_index(
    field_name="sparse_vector",
    index_params={"index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP"},
)
```

**为什么稠密集用 COSINE 而稀疏集用 IP?**

- 稠密向量已 L2 归一化 → COSINE 等价位归一化内积 → 语义方向匹配
- 稀疏向量值表示词汇权重 (≥ 0) → Inner Product 直接衡量关键词共现强度 → 权重越高匹配越强

---

## 14. Agent 工作流与生成侧优化

### 14.1 Plan → Execute → Reflect 循环

```
用户查询
  │
  ▼
┌──────────────────────────────────────────────┐
│  Planning (LLM, temperature=0.0)             │
│  输入: query + 长期记忆 + 短期记忆(最近10条)   │
│  输出: JSON ActionList                       │
│  [{"tool": "rag_tool", "query": "M9续航"},   │
│   {"tool": "calculator", "query": "..."}]     │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  Executor (串行/并行)                         │
│  rag_tool.run("M9续航") → 检索 + LLM 回答     │
│  calculator.run("...") → 安全 eval()          │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  生成前优化 (三道工序)                         │
│  1. 上下文压缩: LLM 精炼 >800 字符的结果       │
│  2. 冗余过滤: Jaccard ≥ 0.75 → 去重           │
│  3. 引用校验: claim→source 逐句验证            │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  LLM 生成答案 (temperature=0.1, max=2048)     │
│  注入: 检索结果 + 对话历史 + 用户偏好          │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  Reflection (LLM, temperature=0.0)           │
│  评分 completeness/accuracy/usefulness        │
│  score ≥ 0.8? → 输出                         │
│  score < 0.8? → 新 ActionList → 回到 Execute  │
│  最多 3 轮迭代                                │
└──────────────────────────────────────────────┘
```

### 14.2 上下文压缩

**问题**: Milvus 返回的文本块可能数百到数千字符。LLM 的 2048 token 上下文窗口有限，无关内容占据窗口导致回答质量下降。

**方案**: 工具结果 > 800 字符时触发 LLM 压缩:

```python
# _compress_contexts 的核心逻辑
if len(text) > 800:
    compressed = llm.chat(
        messages=[{
            "role": "system",
            "content": "从给定文本中提取与用户查询直接相关的信息。
                        保留关键事实、数字、参数，删除无关内容。
                        压缩后 ≤ 400 字。"
        }],
        temperature=0.0,
        max_tokens=512,
    )
```

**设计决策**: 用 LLM 压缩而不是简单的截断或摘要算法。因为:
- 简单截断可能丢失关键信息 (截断后的部分恰好包含答案)
- LLM 能理解查询意图，保留相关信息、滤除噪音
- 400 字的压缩结果对 LLM 上下文窗口友好

### 14.3 冗余过滤

**问题**: rag_tool 和 web_search 可能返回高度重叠的结果 (同一条产品描述被两个来源覆盖)。

**方案**: 字符级 token-Jaccard 去重，纯算法实现，零 LLM 开销:

```python
# 对中文: 单字 + bigram 分词
tokens = {单字} ∪ {相邻二字组合}

# Jaccard = |A ∩ B| / |A ∪ B|
if jaccard(A, B) >= 0.75:  # 阈值 0.75
    保留较长的结果  # 信息量更大
```

### 14.4 引用真实性校验

**问题**: LLM 可能生成看似合理但检索来源中不存在的陈述 (幻觉)。

**方案**: 回答生成后，提取所有 `[来源N]` 标记的句子，逐句验:

```python
# _verify_citations 的核心逻辑
for sentence in cited_sentences[:3]:  # 最多校验 3 句
    llm_result = llm.chat(
        messages=[{
            "role": "system",
            "content": "你是事实核查员。判断陈述是否能从来源文本推断。
                        输出 JSON: {supported: true/false, reason: '...'}",
        }],
    )
    if not llm_result["supported"]:
        violations.append(f"⚠️ [来源{N}] {sentence} — {reason}")

if violations:
    answer += "\n\n⚠️ 以下陈述在来源中未找到充分依据:\n" + ...
```

---

## 15. 未选用技术说明

| 技术 | 未选用原因 |
|------|-----------|
| **LangChain** | 过度抽象，调试困难，不如手写 200 行 Agent 循环直接可控 |
| **LlamaIndex** | RAG 管道已自建 (DocParser → Embedding → VectorDB → LLM)，不需要框架封装 |
| **Docker Swarm** | K8s 是容器编排标准，Swarm 社区萎缩 |
| **MongoDB** | 无向量检索能力，不能替代 Milvus；会话数据用 Redis 更高效 |
| **GraphQL** | 三接口场景 REST 足够，GraphQL 的查询灵活性在固定 API 中无优势 |
| **gRPC** | 内部 Gateway↔Worker 走 RabbitMQ (AMQP)，对外 API REST 更通用 |
| **Celery** | 任务队列功能 RabbitMQ + 自定义 Worker 已覆盖，不需要 Celery 的额外抽象层 |
| **PostgreSQL + pgvector** | pgvector 的混合检索和性能不如 Milvus，且需要额外管理 PostgreSQL 实例 |

---

## 技术栈总览

```
API 层:    FastAPI + Pydantic + uvicorn
认证:      JWT (pyjwt) + bcrypt
消息队列:  RabbitMQ (aiormq) + AMQP 0-9-1
缓存:      Redis 7 (redis-py async)
LLM:       DeepSeek API / OpenAI 兼容 (httpx AsyncClient 连接池)
Embedding: BGE-M3 (sentence-transformers) 本地加载
向量库:    Milvus 2.4 (pymilvus + MilvusClient)
文档解析:  LlamaParse API
前端:      React 18 + TypeScript 5 + Ant Design 5 + Vite 6
监控:      Prometheus (prometheus-client)
进程管理:  supervisord
容器化:    Docker Compose (开发) / K8s (生产)
```

---

*最后更新: 2026-06-03*
