# 高并发架构改造 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AutoSalesAgent 从单用户同步单体改造为 500-2000 QPS、P99 < 1s 的多租户高并发 API 平台（异步 Gateway + RabbitMQ + Worker Pool + Redis 会话隔离）。

**Architecture:** Nginx → FastAPI Gateway (无状态) → RabbitMQ (Topic Exchange) → Worker Pool (多进程, 每进程内嵌 BGE-M3) → Milvus/Redis。核心思路：Gateway 只做鉴权/限流/发布，Worker 消费消息时从 Redis 加载独立会话上下文，构建请求级 Agent 实例，处理完写回 Redis 并直接回复 Gateway。

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, httpx, aiormq, redis-py, pymilvus, sentence-transformers (BGE-M3), openai, Docker Compose, supervisord, Prometheus client

**Spec:** [docs/superpowers/specs/2026-06-03-high-concurrency-architecture-design.md](../specs/2026-06-03-high-concurrency-architecture-design.md)

---

## File Structure

```
agent_car/
├── config.py                          # 扩展: Redis + RabbitMQ + LLM Pool 配置
├── docker-compose.yml                 # 新增: 一键开发环境
├── supervisord.conf                   # 新增: Worker 进程管理
│
├── gateway/                           # 新增: 无状态 API 网关
│   ├── __init__.py
│   ├── app.py                         # FastAPI 应用 + 路由 + 生命周期
│   ├── auth.py                        # API Key 鉴权中间件
│   ├── rate_limit.py                  # 滑动窗口限流
│   ├── publisher.py                   # RabbitMQ 发布客户端
│   └── schemas.py                     # 请求/响应 Pydantic 模型
│
├── worker/                            # 新增: 任务消费者
│   ├── __init__.py
│   ├── consumer.py                    # aiormq 消费者主循环
│   ├── agent_factory.py              # AgentForRequest 工厂
│   └── session.py                     # Redis 会话加载/保存
│
├── agent/                             # 重构: 去全局单例
│   ├── agent_core.py                  # AutoSalesAgent → AgentForRequest
│   ├── memory.py                      # Memory → SessionMemory
│   ├── planning.py                    # 注入 llm_client (不再自建)
│   ├── reflection.py                  # 注入 llm_client
│   └── executor.py                    # 支持并行 Action 执行
│
├── infrastructure/                    # 重构: 连接池 + 异步
│   ├── llm_pool.py                    # 新增: httpx 异步 LLM 连接池
│   ├── embedding.py                   # 保持, 每 Worker 进程独立加载
│   ├── vector_db.py                   # 保持现有 Milvus 逻辑
│   └── doc_parser.py                  # 保持不变
│
├── engine/                            # 新增: 业务规则引擎
│   ├── __init__.py
│   ├── rule_engine.py                 # 车型参数标准化提取
│   ├── scorer.py                      # 多维度 LLM 打分
│   └── comparator.py                  # 多车型对比编排
│
└── tools/                             # 最小改动
    ├── base_tool.py                   # 保持接口不变
    ├── rag_tool.py                    # 注入 llm_client + embedding
    ├── web_search_tool.py             # 保持
    └── calculator_tool.py             # 保持
```

---

## Phase 1: 基础设施搭建

### Task 1.1: 扩展 config.py — Redis + RabbitMQ + LLM Pool 配置

**Files:**
- Modify: `config.py:1-170`

- [ ] **Step 1: 添加新配置字段到 Config 数据类**

打开 `config.py`，在 `Config` 类中添加以下字段（紧接在 `log_format` 字段之后）：

```python
# =========================================================================
# Redis 配置
# =========================================================================
redis_url: str = field(
    default_factory=lambda: os.getenv(
        "REDIS_URL",
        "redis://localhost:6379/0",
    )
)
redis_session_ttl: int = 3600
redis_cache_ttl_vehicle: int = 600
redis_cache_ttl_rag: int = 300

# =========================================================================
# RabbitMQ 配置
# =========================================================================
rabbitmq_url: str = field(
    default_factory=lambda: os.getenv(
        "RABBITMQ_URL",
        "amqp://guest:guest@localhost:5672/",
    )
)
rabbitmq_exchange: str = "api.requests"
rabbitmq_queues: dict = field(default_factory=lambda: {
    "vehicle.query": {
        "prefetch_count": 20,
        "max_length": 10000,
        "message_ttl": 30000,
    },
    "vehicle.compare": {
        "prefetch_count": 10,
        "max_length": 5000,
        "message_ttl": 60000,
    },
    "recommend": {
        "prefetch_count": 10,
        "max_length": 5000,
        "message_ttl": 60000,
    },
})

# =========================================================================
# LLM 连接池配置
# =========================================================================
llm_pool_size: int = 20
llm_pool_timeout: float = 30.0

# =========================================================================
# 限流配置
# =========================================================================
rate_limit_default_rps: int = 100        # 每 API Key 默认每秒请求数
rate_limit_window_seconds: int = 1       # 滑动窗口大小
```

- [ ] **Step 2: 扩展 allowed_keys**

在 `update_from_dict` 方法中，将 `allowed_keys` 集合扩展：

```python
allowed_keys = {
    "llm_api_key", "llm_api_url", "llm_model",
    "llm_temperature", "llm_max_tokens",
    "local_embedding_model", "local_embedding_device",
    "serpapi_key", "llamaparse_api_key",
    "redis_url", "rabbitmq_url",               # 新增
    "llm_pool_size", "llm_pool_timeout",       # 新增
}
```

- [ ] **Step 3: 验证配置加载**

```bash
cd c:/Users/18049/Desktop/agent_car && python -c "from config import config; print(config.redis_url); print(config.rabbitmq_url); print(config.llm_pool_size)"
```
Expected: 打印默认 Redis/RabbitMQ URL 和 pool_size=20

- [ ] **Step 4: Commit**

```bash
git add config.py
git commit -m "feat(config): add Redis, RabbitMQ, LLM pool, rate limit config fields

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 1.2: requirements.txt — 添加新依赖

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 添加新依赖**

在 `requirements.txt` 末尾追加：

```
httpx>=0.27.0
aiormq>=6.8.0
redis>=5.0.0
prometheus-client>=0.20.0
python-json-logger>=2.0.0
supervisor>=4.2.0
```

- [ ] **Step 2: 安装依赖**

```bash
cd c:/Users/18049/Desktop/agent_car && pip install httpx aiormq redis prometheus-client python-json-logger supervisor
```

- [ ] **Step 3: 验证导入**

```bash
python -c "import httpx; import aiormq; import redis; import prometheus_client; print('All imports OK')"
```
Expected: `All imports OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat(deps): add httpx, aiormq, redis, prometheus-client, python-json-logger

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 1.3: docker-compose.yml — 开发环境一键部署

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: 创建 docker-compose.yml**

```yaml
version: "3.8"

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s

  rabbitmq:
    image: rabbitmq:3-management-alpine
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: guest
      RABBITMQ_DEFAULT_PASS: guest
    healthcheck:
      test: ["CMD", "rabbitmqctl", "status"]
      interval: 10s

  milvus:
    image: milvusdb/milvus:v2.4.0
    ports:
      - "19530:19530"
      - "9091:9091"
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    depends_on:
      - etcd
      - minio

  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision
      ETCD_AUTO_COMPACTION_RETENTION: "1000"
      ETCD_QUOTA_BACKEND_BYTES: "4294967296"
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379

  minio:
    image: minio/minio:latest
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    command: minio server /data

volumes:
  redis_data:
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(infra): add Docker Compose for Redis + RabbitMQ + Milvus dev stack

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Phase 2: Gateway 层

### Task 2.1: gateway/schemas.py — 请求/响应 Pydantic 模型

**Files:**
- Create: `gateway/__init__.py`
- Create: `gateway/schemas.py`

- [ ] **Step 1: 创建 gateway/__init__.py**

```python
"""Gateway 包 — 无状态 FastAPI API 网关."""
```

- [ ] **Step 2: 创建 gateway/schemas.py**

```python
"""Gateway 请求/响应 Pydantic 模型."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VehicleQueryRequest(BaseModel):
    """车型查询请求."""
    session_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1, description="自然语言查询")


class VehicleCompareRequest(BaseModel):
    """多车对比请求."""
    session_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    vehicles: List[str] = Field(..., min_length=2, max_length=5, description="车型列表")
    aspects: Optional[List[str]] = Field(None, description="对比维度")


class RecommendRequest(BaseModel):
    """智能推荐请求."""
    session_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    scenario: Optional[str] = Field(None, description="使用场景")
    budget: Optional[str] = Field(None, description="预算范围")
    preferences: Optional[List[str]] = Field(None, description="偏好标签")


class SessionCloseRequest(BaseModel):
    """关闭会话请求."""
    session_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)


class ApiResponse(BaseModel):
    """统一 API 响应."""
    request_id: str
    session_id: str
    status: str  # "success" | "degraded" | "error"
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    degraded: bool = False
    latency_ms: int = 0


class HealthResponse(BaseModel):
    """健康检查响应."""
    status: str
    redis: str
    rabbitmq: str
```

- [ ] **Step 3: Commit**

```bash
git add gateway/__init__.py gateway/schemas.py
git commit -m "feat(gateway): add request/response Pydantic schemas for three APIs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2.2: gateway/auth.py — API Key 鉴权

**Files:**
- Create: `gateway/auth.py`

- [ ] **Step 1: 创建 gateway/auth.py**

```python
"""API Key 鉴权模块."""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

# 开发阶段硬编码 API Keys（生产应从数据库/配置中心加载）
_VALID_API_KEYS: dict[str, dict] = {
    "ak_dev_001": {
        "user_id": "dev_user",
        "rate_limit_rps": 100,
        "enabled": True,
    },
}


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> dict:
    """验证 API Key 并返回上下文."""
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    key_info = _VALID_API_KEYS.get(x_api_key)
    if key_info is None or not key_info.get("enabled", False):
        raise HTTPException(status_code=403, detail="Invalid or disabled API Key")

    return key_info
```

- [ ] **Step 2: Commit**

```bash
git add gateway/auth.py
git commit -m "feat(gateway): add API Key authentication with hardcoded dev keys

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2.3: gateway/rate_limit.py — 滑动窗口限流

**Files:**
- Create: `gateway/rate_limit.py`

- [ ] **Step 1: 创建 gateway/rate_limit.py**

```python
"""滑动窗口限流 — 基于 Redis Sorted Set."""

from __future__ import annotations

import time
import uuid
import logging
from typing import Optional

import redis.asyncio as redis

from config import config

logger = logging.getLogger(__name__)


class RateLimiter:
    """Redis 滑动窗口限流器."""

    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client
        self._window = config.rate_limit_window_seconds

    async def check_and_increment(
        self,
        api_key: str,
        endpoint: str,
        max_rps: int = 100,
    ) -> bool:
        """检查是否允许通过. 返回 True = 允许, False = 限流."""
        key = f"ratelimit:{api_key}:{endpoint}"
        now_ms = int(time.time() * 1000)
        window_start = now_ms - self._window * 1000

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            results = await pipe.execute()

        current_count: int = results[1]  # type: ignore[index]
        if current_count >= max_rps:
            logger.warning("限流触发: key=%s count=%d max=%d", key, current_count, max_rps)
            return False

        await self._redis.zadd(key, {str(uuid.uuid4()): now_ms})
        await self._redis.expire(key, self._window * 2)
        return True
```

- [ ] **Step 2: Commit**

```bash
git add gateway/rate_limit.py
git commit -m "feat(gateway): add Redis sliding-window rate limiter

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2.4: gateway/publisher.py — RabbitMQ 发布客户端

**Files:**
- Create: `gateway/publisher.py`

- [ ] **Step 1: 创建 gateway/publisher.py**

```python
"""RabbitMQ 发布客户端 — 支持 Direct Reply-to 模式."""

from __future__ import annotations

import json
import uuid
import asyncio
import logging
from typing import Any, Dict, Optional

import aiormq
from aiormq import Channel, Connection

from config import config

logger = logging.getLogger(__name__)

_RESPONSE_TIMEOUT = 30.0  # 等待 Worker 回复的超时


class RabbitMQPublisher:
    """发布消息到 RabbitMQ 并等待 Worker 直接回复."""

    def __init__(self) -> None:
        self._connection: Optional[Connection] = None
        self._channel: Optional[Channel] = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._consumer_tag: Optional[str] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """建立连接并声明 Exchange + Direct Reply 消费者."""
        self._connection = await aiormq.connect(config.rabbitmq_url)
        self._channel = await self._connection.channel()

        # 声明 Topic Exchange
        await self._channel.exchange_declare(
            exchange=config.rabbitmq_exchange,
            exchange_type="topic",
            durable=True,
        )

        # 设置 Direct Reply-to 消费者
        reply_queue = await self._channel.queue_declare(
            queue="amq.rabbitmq.reply-to",
            auto_delete=False,
        )
        self._consumer_tag = await self._channel.basic_consume(
            queue=reply_queue.queue,
            consumer_callback=self._on_reply,
            no_ack=True,
        )
        logger.info("RabbitMQPublisher 已连接")

    async def close(self) -> None:
        """关闭连接."""
        if self._channel and self._consumer_tag:
            await self._channel.basic_cancel(self._consumer_tag)
        if self._connection:
            await self._connection.close()
        logger.info("RabbitMQPublisher 已断开")

    async def publish_and_wait(
        self,
        routing_key: str,
        payload: Dict[str, Any],
        session_id: str,
        timeout: float = _RESPONSE_TIMEOUT,
    ) -> Dict[str, Any]:
        """发布消息并阻塞等待 Worker 回复."""
        request_id = str(uuid.uuid4())
        message = {
            "request_id": request_id,
            "session_id": session_id,
            "endpoint": routing_key,
            "payload": payload,
            "reply_to": "amq.rabbitmq.reply-to",
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        try:
            async with self._lock:
                await self._channel.basic_publish(
                    body=json.dumps(message, ensure_ascii=False).encode(),
                    exchange=config.rabbitmq_exchange,
                    routing_key=f"api.{routing_key}",
                    properties={
                        "reply_to": "amq.rabbitmq.reply-to",
                        "message_id": request_id,
                        "content_type": "application/json",
                    },
                )
            logger.debug("消息已发布: routing_key=%s request_id=%s", routing_key, request_id)

            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.error("请求超时: request_id=%s timeout=%.1fs", request_id, timeout)
            self._pending.pop(request_id, None)
            return {"status": "error", "error": "gateway_timeout", "request_id": request_id}
        except Exception:
            self._pending.pop(request_id, None)
            raise

    async def _on_reply(self, message: aiormq.abc.DeliveredMessage) -> None:
        """处理 Direct Reply 消息."""
        body = json.loads(message.body.decode())
        request_id = body.get("request_id", "")
        future = self._pending.pop(request_id, None)
        if future and not future.done():
            future.set_result(body)
```

- [ ] **Step 2: Commit**

```bash
git add gateway/publisher.py
git commit -m "feat(gateway): add RabbitMQ publisher with Direct Reply-to support

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2.5: gateway/app.py — FastAPI 应用组装

**Files:**
- Create: `gateway/app.py`

- [ ] **Step 1: 创建 gateway/app.py**

```python
"""FastAPI Gateway 应用 — 路由 + 生命周期."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Dict

import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import config
from gateway.auth import verify_api_key
from gateway.publisher import RabbitMQPublisher
from gateway.rate_limit import RateLimiter
from gateway.schemas import (
    ApiResponse,
    HealthResponse,
    RecommendRequest,
    SessionCloseRequest,
    VehicleCompareRequest,
    VehicleQueryRequest,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 全局组件 (应用生命周期内)
# ---------------------------------------------------------------------------
_publisher: RabbitMQPublisher
_rate_limiter: RateLimiter
_redis: redis.Redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭钩子."""
    global _publisher, _rate_limiter, _redis

    logger.info("Gateway 启动中...")
    _redis = redis.from_url(config.redis_url, decode_responses=True)
    _rate_limiter = RateLimiter(_redis)
    _publisher = RabbitMQPublisher()
    await _publisher.connect()
    logger.info("Gateway 启动完成")

    yield

    logger.info("Gateway 关闭中...")
    await _publisher.close()
    await _redis.aclose()
    logger.info("Gateway 已关闭")


app = FastAPI(
    title="AutoSalesAgent High-Concurrency API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 辅助: 通用请求处理
# ---------------------------------------------------------------------------
async def _handle_request(
    routing_key: str,
    payload: dict,
    session_id: str,
    api_key_info: dict,
    endpoint: str,
) -> ApiResponse:
    """通用请求处理: 限流 → 发布 → 等待回复."""
    # 限流
    allowed = await _rate_limiter.check_and_increment(
        api_key=api_key_info.get("user_id", "unknown"),
        endpoint=endpoint,
        max_rps=api_key_info.get("rate_limit_rps", config.rate_limit_default_rps),
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    t0 = time.perf_counter()
    result = await _publisher.publish_and_wait(
        routing_key=routing_key,
        payload=payload,
        session_id=session_id,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    return ApiResponse(
        request_id=result.get("request_id", ""),
        session_id=session_id,
        status=result.get("status", "error"),
        data=result.get("data"),
        error=result.get("error"),
        degraded=result.get("degraded", False),
        latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    redis_ok = "ok"
    rabbitmq_ok = "ok"
    try:
        await _redis.ping()
    except Exception:
        redis_ok = "unhealthy"
    return HealthResponse(
        status="ok" if redis_ok == "ok" else "degraded",
        redis=redis_ok,
        rabbitmq=rabbitmq_ok,
    )


# ---------------------------------------------------------------------------
# API v1 路由
# ---------------------------------------------------------------------------
@app.post("/api/v1/vehicle/query", response_model=ApiResponse)
async def vehicle_query(
    req: VehicleQueryRequest,
    api_key_info: dict = Depends(verify_api_key),
) -> ApiResponse:
    return await _handle_request(
        routing_key="vehicle.query",
        payload={"query": req.query},
        session_id=req.session_id,
        api_key_info=api_key_info,
        endpoint="vehicle.query",
    )


@app.post("/api/v1/vehicle/compare", response_model=ApiResponse)
async def vehicle_compare(
    req: VehicleCompareRequest,
    api_key_info: dict = Depends(verify_api_key),
) -> ApiResponse:
    return await _handle_request(
        routing_key="vehicle.compare",
        payload={"vehicles": req.vehicles, "aspects": req.aspects},
        session_id=req.session_id,
        api_key_info=api_key_info,
        endpoint="vehicle.compare",
    )


@app.post("/api/v1/recommend", response_model=ApiResponse)
async def recommend(
    req: RecommendRequest,
    api_key_info: dict = Depends(verify_api_key),
) -> ApiResponse:
    return await _handle_request(
        routing_key="recommend",
        payload={
            "scenario": req.scenario,
            "budget": req.budget,
            "preferences": req.preferences,
        },
        session_id=req.session_id,
        api_key_info=api_key_info,
        endpoint="recommend",
    )


@app.post("/api/v1/session/close", response_model=ApiResponse)
async def session_close(
    req: SessionCloseRequest,
    api_key_info: dict = Depends(verify_api_key),
) -> ApiResponse:
    await _redis.delete(
        f"session:{req.session_id}",
        f"session:{req.session_id}:messages",
        f"session:{req.session_id}:state",
    )
    logger.info("会话已关闭: session_id=%s", req.session_id)
    return ApiResponse(
        request_id="",
        session_id=req.session_id,
        status="success",
    )
```

- [ ] **Step 2: 验证 Gateway 可以启动**

```bash
cd c:/Users/18049/Desktop/agent_car && python -c "from gateway.app import app; print('Gateway app created:', app.title)"
```
Expected: `Gateway app created: AutoSalesAgent High-Concurrency API`

- [ ] **Step 3: Commit**

```bash
git add gateway/app.py
git commit -m "feat(gateway): add FastAPI app with three API routes, health check, session close

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Phase 3: Worker + Agent 重构

### Task 3.1: infrastructure/llm_pool.py — 异步 LLM 连接池

**Files:**
- Create: `infrastructure/llm_pool.py`

- [ ] **Step 1: 创建 infrastructure/llm_pool.py**

```python
"""异步 LLM 连接池 — 基于 httpx AsyncClient."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from config import config

logger = logging.getLogger(__name__)


class LLMPool:
    """httpx 异步 LLM 连接池.

    单进程内复用同一个 AsyncClient，利用 HTTP/1.1 keep-alive
    避免每次请求都重新建立 TCP+TLS 连接。
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        pool_size: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._api_url = (api_url or config.llm_api_url).rstrip("/")
        self._api_key = api_key or config.llm_api_key
        pool_size = pool_size or config.llm_pool_size
        timeout = timeout or config.llm_pool_timeout

        self._client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=pool_size,
                max_connections=pool_size,
            ),
            timeout=httpx.Timeout(timeout),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        logger.info("LLMPool 已初始化: url=%s pool=%d", self._api_url, pool_size)

    async def close(self) -> None:
        """关闭连接池."""
        await self._client.aclose()
        logger.info("LLMPool 已关闭")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> str:
        """发送 chat completion 请求, 返回文本响应."""
        url = f"{self._api_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": model or config.llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"] or ""

    async def chat_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """发送请求并以 JSON 解析响应."""
        import json as _json
        import re

        text = await self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        try:
            return _json.loads(text.strip())
        except _json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    return _json.loads(m.group(0))
                except _json.JSONDecodeError:
                    pass
            return {}
```

- [ ] **Step 2: 验证 LLMPool 可导入**

```bash
cd c:/Users/18049/Desktop/agent_car && python -c "from infrastructure.llm_pool import LLMPool; print('LLMPool import OK')"
```
Expected: `LLMPool import OK`

- [ ] **Step 3: Commit**

```bash
git add infrastructure/llm_pool.py
git commit -m "feat(infra): add async LLM connection pool via httpx AsyncClient

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3.2: agent/memory.py — Memory → SessionMemory (Redis 后端)

**Files:**
- Modify: `agent/memory.py`

- [ ] **Step 1: 重命名类并添加 Redis 后端**

将原 `class Memory` 重命名为保留短期记忆核心逻辑，新增 `SessionMemory` 类。**替换整个文件内容**：

```python
"""
记忆管理模块 — Redis 后端会话隔离版本。

短期记忆: Redis List 持久化 (每 session 独立)
长期记忆: Milvus 向量库 + Redis 热缓存
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from pymilvus import MilvusClient

from config import config
from infrastructure.embedding import EmbeddingClient

logger = logging.getLogger(__name__)

LONG_TERM_TEXT_MAX = 4096


class SessionMemory:
    """Redis 支持的会话记忆 — 每 session_id 独立隔离.

    加载/保存短期记忆到 Redis, 长期记忆读 Milvus + Redis 缓存.

    Attributes:
        redis: Redis 客户端.
        session_id: 会话标识.
        user_id: 用户标识.
        short_term: 当前会话的短期记忆列表.
        embedding: Embedding 客户端 (进程内共享).
        milvus: MilvusClient (进程内共享).
    """

    def __init__(
        self,
        redis: Any,
        session_id: str,
        user_id: str = "default_user",
        embedding: Optional[EmbeddingClient] = None,
        milvus: Optional[MilvusClient] = None,
    ) -> None:
        self.redis = redis
        self.session_id = session_id
        self.user_id = user_id
        self.short_term: List[Dict[str, Any]] = []
        self._step_counter: int = 0
        self._embedding = embedding or EmbeddingClient()
        self._milvus = milvus or MilvusClient(uri=config.milvus_uri)
        self._lt_collection = config.long_term_memory_collection_name

    @classmethod
    async def load(
        cls,
        redis: Any,
        session_id: str,
        embedding: Optional[EmbeddingClient] = None,
        milvus: Optional[MilvusClient] = None,
    ) -> "SessionMemory":
        """从 Redis 加载会话上下文创建 SessionMemory 实例."""
        instance = cls(redis, session_id, embedding=embedding, milvus=milvus)

        # 加载会话元数据
        meta = await redis.hgetall(f"session:{session_id}")
        if meta:
            instance.user_id = meta.get("user_id", "default_user")
            instance._step_counter = int(meta.get("message_count", 0))

        # 加载对话历史
        messages_raw = await redis.lrange(f"session:{session_id}:messages", 0, -1)
        for msg_json in messages_raw:
            try:
                instance.short_term.append(json.loads(msg_json))
            except json.JSONDecodeError:
                logger.warning("跳过损坏的消息条目: session=%s", session_id)

        # 加载 Agent 状态
        state_raw = await redis.hgetall(f"session:{session_id}:state")
        instance._state = {
            "iteration_count": int(state_raw.get("iteration_count", 0)),
            "last_actions": state_raw.get("last_actions", "[]"),
            "rag_queries": state_raw.get("rag_queries", "[]"),
        }

        logger.info(
            "Session 已加载: session=%s user=%s messages=%d",
            session_id, instance.user_id, len(instance.short_term),
        )
        return instance

    async def save(self) -> None:
        """将当前状态写回 Redis."""
        ttl = config.redis_session_ttl

        # 保存会话元数据
        await self.redis.hset(
            f"session:{self.session_id}",
            mapping={
                "user_id": self.user_id,
                "last_access": datetime.datetime.now().isoformat(),
                "message_count": str(self._step_counter),
            },
        )
        await self.redis.expire(f"session:{self.session_id}", ttl)

        # 保存对话历史 (最近20条)
        pipe = self.redis.pipeline()
        for entry in self.short_term[-20:]:
            pipe.rpush(
                f"session:{self.session_id}:messages",
                json.dumps(entry, ensure_ascii=False, default=str),
            )
        pipe.ltrim(f"session:{self.session_id}:messages", -20, -1)
        pipe.expire(f"session:{self.session_id}:messages", ttl)
        await pipe.execute()

        # 保存 Agent 状态
        await self.redis.hset(
            f"session:{self.session_id}:state",
            mapping={
                "iteration_count": str(self._state.get("iteration_count", 0)),
                "last_actions": self._state.get("last_actions", "[]"),
                "rag_queries": self._state.get("rag_queries", "[]"),
            },
        )
        await self.redis.expire(f"session:{self.session_id}:state", ttl)

        logger.debug("Session 已保存: session=%s messages=%d", self.session_id, len(self.short_term))

    # ------------------------------------------------------------------
    # 短期记忆操作
    # ------------------------------------------------------------------

    def add(self, content: str, content_type: str = "step") -> None:
        """向短期记忆添加记录."""
        self._step_counter += 1
        entry: Dict[str, Any] = {
            "id": self._step_counter,
            "type": content_type,
            "content": content,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        self.short_term.append(entry)

    def get_context(self, max_entries: Optional[int] = None) -> str:
        """获取格式化的短期记忆上下文."""
        entries = self.short_term
        if max_entries is not None:
            entries = entries[-max_entries:]

        if not entries:
            return "（暂无历史记录）"

        lines: List[str] = []
        for entry in entries:
            etype = entry.get("type", "step")
            content_preview = entry["content"][:500]
            if len(entry["content"]) > 500:
                content_preview += "..."
            lines.append(f"[{entry['id']}] ({etype}) {content_preview}")

        return "\n".join(lines)

    def get_recent_dialogue_pairs(self, max_pairs: int = 3) -> str:
        """从短期记忆中提取最近的用户-助手对话对."""
        pairs: List[Tuple[str, str]] = []
        current_user: Optional[str] = None

        for entry in self.short_term:
            if entry.get("type") == "user_query":
                current_user = entry.get("content", "")
            elif entry.get("type") == "final_answer" and current_user is not None:
                answer = entry.get("content", "")[:300]
                pairs.append((current_user, answer))
                current_user = None

        if not pairs:
            return ""

        pairs = pairs[-max_pairs:]
        lines: List[str] = []
        for user_q, agent_a in pairs:
            lines.append(f"用户: {user_q}")
            lines.append(f"助手: {agent_a}")

        return "\n".join(lines)

    def get_dialogue_for_answer_context(self, max_pairs: int = 2) -> str:
        """获取对话历史用于答案生成的上下文注入."""
        return self.get_recent_dialogue_pairs(max_pairs=max_pairs)

    # ------------------------------------------------------------------
    # 长期记忆操作
    # ------------------------------------------------------------------

    def search_long_term(self, query: str, top_k: Optional[int] = None) -> List[str]:
        """搜索长期记忆 — Milvus 语义搜索 + Redis 缓存."""
        top_k = top_k or config.long_term_memory_top_k
        try:
            dense, _sparse = self._embedding.encode_text(query)
            results = self._milvus.search(
                collection_name=self._lt_collection,
                data=[dense],
                limit=top_k,
                output_fields=["content", "memory_type"],
            )
            if not results or not results[0]:
                return []

            memories: List[str] = []
            for hit in results[0]:
                entity = hit.get("entity", {})
                content = entity.get("content", "")
                mtype = entity.get("memory_type", "")
                if content:
                    memories.append(f"[{mtype}] {content}")
            logger.info("长期记忆检索: query='%s', 命中=%d", query[:50], len(memories))
            return memories
        except Exception as e:
            logger.error("长期记忆搜索失败: %s", e)
            return []

    def save_to_long_term(self, key: str, content: str) -> bool:
        """保存内容到长期记忆."""
        if not content.strip():
            return False
        memory_type = key.split(":", 1)[0] if ":" in key else "general"
        try:
            dense, sparse = self._embedding.encode_text(content)
            data = [{
                "user_id": self.user_id,
                "content": content[:LONG_TERM_TEXT_MAX],
                "memory_type": memory_type,
                "dense_vector": dense,
                "sparse_vector": {str(k): float(v) for k, v in sparse.items() if float(v) > 0},
                "created_at": datetime.datetime.now().isoformat(),
            }]
            self._milvus.insert(collection_name=self._lt_collection, data=data)
            logger.info("长期记忆已保存: key=%s, type=%s", key, memory_type)
            return True
        except Exception as e:
            logger.error("长期记忆保存失败: %s", e)
            return False
```

- [ ] **Step 2: 验证 SessionMemory 导入**

```bash
cd c:/Users/18049/Desktop/agent_car && python -c "from agent.memory import SessionMemory; print('SessionMemory import OK')"
```
Expected: `SessionMemory import OK`

- [ ] **Step 3: Commit**

```bash
git add agent/memory.py
git commit -m "refactor(memory): replace Memory singleton with Redis-backed SessionMemory

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3.3: agent/planning.py — 注入 llm_client (解耦)

**Files:**
- Modify: `agent/planning.py:39-45`

- [ ] **Step 1: 修改 PlanningModule.__init__ 接受外部 llm_client**

编辑 `agent/planning.py`，替换 `__init__` 方法：

```python
def __init__(self, llm_client: Optional[Any] = None) -> None:
    """初始化规划模块.

    Args:
        llm_client: 异步 LLM 调用接口 (如 LLMPool). 若为 None 则创建同步 OpenAI 客户端 (向后兼容).
    """
    self.llm_client = llm_client
    if self.llm_client is None:
        from openai import OpenAI
        self.llm_client = OpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_api_url,
        )
    self.system_prompt = self._load_plan_prompt()
    logger.info("PlanningModule 已初始化")
```

- [ ] **Step 2: 验证**

```bash
cd c:/Users/18049/Desktop/agent_car && python -c "from agent.planning import PlanningModule; p = PlanningModule(); print('PlanningModule OK')"
```
Expected: `PlanningModule OK`

- [ ] **Step 3: Commit**

```bash
git add agent/planning.py
git commit -m "refactor(planning): accept optional external llm_client to break singleton dependency

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3.4: agent/reflection.py — 注入 llm_client (解耦)

**Files:**
- Modify: `agent/reflection.py:42-56`

- [ ] **Step 1: 修改 ReflectionModule.__init__ 接受外部 llm_client**

编辑 `agent/reflection.py`，替换 `__init__` 方法：

```python
def __init__(self, llm_client: Optional[Any] = None) -> None:
    """初始化反思模块.

    Args:
        llm_client: 异步 LLM 调用接口 (如 LLMPool). 若为 None 则创建同步 OpenAI 客户端.
    """
    self.llm_client = llm_client
    if self.llm_client is None:
        from openai import OpenAI
        self.llm_client = OpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_api_url,
        )
    self.system_prompt = self._load_reflection_prompt()
    self.max_iterations = config.reflection_max_iterations
    self.quality_threshold = config.reflection_quality_threshold
    self.iteration_count: int = 0
    logger.info(
        "ReflectionModule 已初始化: max_iter=%d, threshold=%.1f",
        self.max_iterations,
        self.quality_threshold,
    )
```

- [ ] **Step 2: 验证**

```bash
cd c:/Users/18049/Desktop/agent_car && python -c "from agent.reflection import ReflectionModule; r = ReflectionModule(); print('ReflectionModule OK')"
```
Expected: `ReflectionModule OK`

- [ ] **Step 3: Commit**

```bash
git add agent/reflection.py
git commit -m "refactor(reflection): accept optional external llm_client to break singleton dependency

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3.5: agent/executor.py — 支持并行 Action 执行

**Files:**
- Modify: `agent/executor.py`

- [ ] **Step 1: 添加并行执行方法**

在 `Executor` 类中添加 `execute_parallel` 方法，追加在 `get_tool_names` 之前：

```python
def execute_parallel(
    self,
    action_groups: List[List[Dict[str, str]]],
) -> List[List[Dict[str, Any]]]:
    """并行执行多组 Action List.

    每组内的 Actions 串行执行，组间并行.
    依赖 asyncio 并发模型.

    Args:
        action_groups: 多组 Action 列表.

    Returns:
        List[List[Dict]]: 每组的结果列表.
    """
    import asyncio

    async def _run_group(actions: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        return self.execute(actions)

    async def _run_all():
        tasks = [_run_group(group) for group in action_groups]
        return await asyncio.gather(*tasks)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(_run_all())
```

- [ ] **Step 2: 验证**

```bash
cd c:/Users/18049/Desktop/agent_car && python -c "from agent.executor import Executor; e = Executor(); print('execute_parallel' in dir(e))"
```
Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add agent/executor.py
git commit -m "feat(executor): add execute_parallel for concurrent multi-group action execution

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3.6: agent/agent_core.py — AutoSalesAgent → AgentForRequest

**Files:**
- Modify: `agent/agent_core.py`

- [ ] **Step 1: 创建 AgentForRequest 类**

在 `agent/agent_core.py` 中保留 `AutoSalesAgent` (向后兼容 CLI)，追加新类 `AgentForRequest`。在文件末尾（第687行之后）追加：

```python
class AgentForRequest:
    """请求级 Agent — 无全局状态, 每次请求独立创建/销毁.

    使用外部注入的 LLMPool (异步连接池) 和 SessionMemory (Redis 后端),
    避免 AutoSalesAgent 的全局单例问题.

    Attributes:
        session: SessionMemory (从 Redis 加载).
        llm_pool: 异步 LLM 连接池.
        planning: 规划模块.
        reflection: 反思模块.
        executor: 执行器.
    """

    def __init__(
        self,
        session: "SessionMemory",       # type: ignore[name-defined] # noqa: F821
        llm_pool: "LLMPool",            # type: ignore[name-defined] # noqa: F821
        rag_tool: Any = None,
        web_search: Any = None,
        calculator: Any = None,
    ) -> None:
        import sys
        from agent.memory import SessionMemory
        from infrastructure.llm_pool import LLMPool

        self.session = session
        self.llm_pool = llm_pool
        self.memory = session  # 统一接口别名

        # 核心模块 — 共享 LLMPool
        self.planning = PlanningModule(llm_client=llm_pool)
        self.executor = Executor()
        self.reflection = ReflectionModule(llm_client=llm_pool)

        # 工具
        self.rag_tool = rag_tool
        self.web_search = web_search
        self.calculator = calculator

        if self.rag_tool and self.web_search and self.calculator:
            self.executor.register_tools([
                self.rag_tool, self.web_search, self.calculator,
            ])

    async def run_query(self, user_input: str) -> str:
        """异步执行完整 Agent 工作流."""
        logger.info("=" * 60)
        logger.info("[AgentForRequest] session=%s query=%s", self.session.session_id, user_input[:80])

        # 1. 存储用户查询
        self.session.add(user_input, content_type="user_query")

        # 2. 检索长期记忆
        long_term_context = self.session.search_long_term(user_input)

        # 3. 规划
        memory_ctx = self.session.get_context(max_entries=10)
        if long_term_context:
            lt_text = "长期记忆:\n" + "\n".join(f"- {m}" for m in long_term_context)
            memory_ctx = lt_text + "\n\n" + memory_ctx
        actions = self.planning.generate_action_plan(user_input, memory_ctx)

        if not actions:
            reply = await self._chat_reply(user_input)
            self.session.add(reply, content_type="final_answer")
            return reply

        # 4. 执行
        exec_results = self.executor.execute(actions)
        for result in exec_results:
            self.session.add(
                f"[{result['tool']}] {result['result'][:500]}",
                content_type="tool_result",
            )

        # 5. 生成答案
        filtered_results = self._filter_redundant_results(
            self._compress_contexts(user_input, exec_results)
        )
        current_answer = await self._generate_answer(
            user_input, filtered_results,
            dialogue_context=self.session.get_dialogue_for_answer_context(),
            long_term_context=long_term_context,
        )

        # 6. 反思迭代
        self.reflection.reset()
        for _ in range(config.reflection_max_iterations):
            should_continue, new_actions = self.reflection.evaluate_and_refine(
                query=user_input,
                current_answer=current_answer,
                memory_context=self.session.get_context(),
            )
            if not should_continue or not new_actions:
                break

            supplement_results = self.executor.execute(new_actions)
            for result in supplement_results:
                self.session.add(
                    f"[补充-{result['tool']}] {result['result'][:500]}",
                    content_type="tool_result",
                )
            all_results = exec_results + supplement_results
            filtered_all = self._filter_redundant_results(
                self._compress_contexts(user_input, all_results)
            )
            current_answer = await self._generate_answer(
                user_input, filtered_all,
                dialogue_context=self.session.get_dialogue_for_answer_context(),
                long_term_context=long_term_context,
            )

        # 7. 保存
        self.session.add(current_answer, content_type="final_answer")
        return current_answer

    async def _generate_answer(
        self,
        query: str,
        exec_results: List[Dict[str, Any]],
        dialogue_context: str = "",
        long_term_context: Optional[List[str]] = None,
    ) -> str:
        """异步生成答案 (使用 LLMPool)."""
        context_parts: List[str] = []
        for i, result in enumerate(exec_results, start=1):
            tool_name = result.get("tool", "unknown")
            tool_result = result.get("result", "")
            if tool_result:
                context_parts.append(f"[来源{i} - {tool_name}]\n{tool_result}")

        context_text = "\n\n".join(context_parts) if context_parts else "无参考信息"

        system_prompt = (
            "你是一位专业的汽车销售培训顾问。请基于提供的参考信息回答用户问题。"
            "要求:\n"
            "1. 综合所有来源信息给出完整回答\n"
            "2. 使用 [来源N] 标注信息出处\n"
            "3. 专业、准确、有销售指导价值\n"
            "4. 无法确认的信息请明确说明\n"
            "5. 如果是多轮对话，自然引用前文提到的信息"
        )
        if dialogue_context:
            system_prompt += f"\n\n近期对话历史:\n{dialogue_context}"
        if long_term_context:
            lt_text = "\n".join(f"- {m}" for m in long_term_context)
            system_prompt += f"\n\n已知用户偏好:\n{lt_text}"

        try:
            answer = await self.llm_pool.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"参考信息:\n{context_text}\n\n"
                            f"用户问题: {query}\n\n"
                            "请生成专业回答:"
                        ),
                    },
                ],
                temperature=config.llm_temperature,
                max_tokens=config.llm_max_tokens,
            )
            return answer
        except Exception as e:
            logger.error("答案生成失败: %s", e)
            return f"（LLM 调用失败，以下为检索到的原始信息）\n\n{context_text}"

    async def _chat_reply(self, user_input: str) -> str:
        """闲聊回复."""
        try:
            return await self.llm_pool.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位友好的汽车销售培训助手。",
                    },
                    {"role": "user", "content": user_input},
                ],
                temperature=0.7,
                max_tokens=512,
            )
        except Exception:
            return "您好！我是汽车销售培训助手，请问有什么可以帮您的？"

    # 复用 AutoSalesAgent 的静态/辅助方法
    _compress_contexts = AutoSalesAgent._compress_contexts
    _filter_redundant_results = AutoSalesAgent._filter_redundant_results
    _verify_citations = AutoSalesAgent._verify_citations
    _parse_json = AutoSalesAgent._parse_json
```

- [ ] **Step 2: 验证 AgentForRequest 可导入**

```bash
cd c:/Users/18049/Desktop/agent_car && python -c "from agent.agent_core import AgentForRequest; print('AgentForRequest import OK')"
```
Expected: `AgentForRequest import OK`

- [ ] **Step 3: Commit**

```bash
git add agent/agent_core.py
git commit -m "feat(agent): add AgentForRequest — request-scoped agent with injected LLMPool

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3.7: worker/session.py — Redis 会话管理

**Files:**
- Create: `worker/__init__.py`
- Create: `worker/session.py`

- [ ] **Step 1: 创建 worker/__init__.py**

```python
"""Worker 包 — RabbitMQ 消费者 + 请求级 Agent 工厂."""
```

- [ ] **Step 2: 创建 worker/session.py**

```python
"""Redis 会话管理 — Worker 侧加载/保存."""

from __future__ import annotations

import logging
from typing import Any, Optional

from agent.memory import SessionMemory
from config import config
from infrastructure.embedding import EmbeddingClient

logger = logging.getLogger(__name__)


class SessionManager:
    """Worker 进程内的会话管理器.

    持有进程级共享的 Embedding 和 Milvus 客户端,
    按 session_id 创建/加载 SessionMemory.
    """

    def __init__(self, redis: Any) -> None:
        self._redis = redis
        self._embedding = EmbeddingClient()
        from pymilvus import MilvusClient
        self._milvus = MilvusClient(uri=config.milvus_uri)

    async def load_session(self, session_id: str, user_id: str = "default_user") -> SessionMemory:
        """从 Redis 加载会话 (不存在则创建)."""
        return await SessionMemory.load(
            redis=self._redis,
            session_id=session_id,
            embedding=self._embedding,
            milvus=self._milvus,
        )

    async def save_session(self, memory: SessionMemory) -> None:
        """保存会话到 Redis."""
        await memory.save()

    async def close_session(self, session_id: str) -> None:
        """删除会话所有 Redis Key."""
        await self._redis.delete(
            f"session:{session_id}",
            f"session:{session_id}:messages",
            f"session:{session_id}:state",
        )
        logger.info("会话已关闭: session_id=%s", session_id)
```

- [ ] **Step 3: Commit**

```bash
git add worker/__init__.py worker/session.py
git commit -m "feat(worker): add SessionManager for Redis session load/save in Workers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3.8: worker/agent_factory.py — 请求级 Agent 工厂

**Files:**
- Create: `worker/agent_factory.py`

- [ ] **Step 1: 创建 worker/agent_factory.py**

```python
"""AgentForRequest 工厂 — 每个请求创建一个独立 Agent 实例."""

from __future__ import annotations

import logging
from typing import Any

from agent.agent_core import AgentForRequest
from agent.memory import SessionMemory
from infrastructure.llm_pool import LLMPool
from tools.calculator_tool import CalculatorTool
from tools.rag_tool import RAGTool
from tools.web_search_tool import WebSearchTool

logger = logging.getLogger(__name__)


class AgentFactory:
    """请求级 Agent 工厂.

    持有进程级共享资源 (LLMPool, RAGTool, etc.),
    为每个请求创建独立的 AgentForRequest 实例.
    """

    def __init__(self) -> None:
        self.llm_pool = LLMPool()
        self.rag_tool = RAGTool()
        self.web_search = WebSearchTool()
        self.calculator = CalculatorTool()
        logger.info("AgentFactory 已初始化 (共享 LLMPool + Tools)")

    def create(self, session: SessionMemory) -> AgentForRequest:
        """为给定 session 创建独立的 AgentForRequest."""
        agent = AgentForRequest(
            session=session,
            llm_pool=self.llm_pool,
            rag_tool=self.rag_tool,
            web_search=self.web_search,
            calculator=self.calculator,
        )
        return agent

    async def close(self) -> None:
        """关闭共享资源."""
        await self.llm_pool.close()
        logger.info("AgentFactory 已关闭")
```

- [ ] **Step 2: Commit**

```bash
git add worker/agent_factory.py
git commit -m "feat(worker): add AgentFactory for per-request AgentForRequest creation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3.9: worker/consumer.py — RabbitMQ 消费者主循环

**Files:**
- Create: `worker/consumer.py`

- [ ] **Step 1: 创建 worker/consumer.py**

```python
"""Worker 消费者主循环 — 从 RabbitMQ 消费任务并执行."""

from __future__ import annotations

import json
import logging
import signal
import time
import uuid
from typing import Any, Dict

import aiormq
import redis.asyncio as redis

from config import config
from worker.agent_factory import AgentFactory
from worker.session import SessionManager

logger = logging.getLogger(__name__)

WORKER_ID = f"worker-{uuid.uuid4().hex[:6]}"


class Worker:
    """RabbitMQ 任务消费者.

    负责:
    1. 声明队列 + 绑定
    2. 消费消息 → 加载 Session → 创建 Agent → 执行 → 保存 → 回复
    3. 优雅关闭
    """

    def __init__(self) -> None:
        self._connection: aiormq.Connection | None = None
        self._channel: aiormq.Channel | None = None
        self._redis: redis.Redis | None = None
        self._factory: AgentFactory | None = None
        self._sessions: SessionManager | None = None
        self._running = False

    async def start(self) -> None:
        """启动 Worker."""
        logger.info("Worker %s 启动中...", WORKER_ID)

        self._redis = redis.from_url(config.redis_url, decode_responses=True)
        self._factory = AgentFactory()
        self._sessions = SessionManager(self._redis)

        self._connection = await aiormq.connect(config.rabbitmq_url)
        self._channel = await self._connection.channel()

        # 设置 QoS
        await self._channel.basic_qos(prefetch_count=1)

        # 声明 Exchange
        await self._channel.exchange_declare(
            exchange=config.rabbitmq_exchange,
            exchange_type="topic",
            durable=True,
        )

        # 声明每个队列并绑定 + 启动消费
        for queue_name, params in config.rabbitmq_queues.items():
            await self._channel.queue_declare(
                queue=f"{queue_name}.queue",
                durable=True,
                arguments={
                    "x-max-length": params["max_length"],
                    "x-message-ttl": params["message_ttl"],
                },
            )
            await self._channel.queue_bind(
                queue=f"{queue_name}.queue",
                exchange=config.rabbitmq_exchange,
                routing_key=f"api.{queue_name}",
            )
            await self._channel.basic_consume(
                queue=f"{queue_name}.queue",
                consumer_callback=self._handle_message,
            )
            logger.info("Worker %s 已绑定队列: %s.queue", WORKER_ID, queue_name)

        self._running = True
        logger.info("Worker %s 启动完成, 等待消息...", WORKER_ID)

    async def stop(self) -> None:
        """优雅关闭."""
        logger.info("Worker %s 关闭中...", WORKER_ID)
        self._running = False
        if self._factory:
            await self._factory.close()
        if self._connection:
            await self._connection.close()
        if self._redis:
            await self._redis.aclose()
        logger.info("Worker %s 已关闭", WORKER_ID)

    async def _handle_message(self, message: aiormq.abc.DeliveredMessage) -> None:
        """处理收到的消息."""
        t0 = time.perf_counter()
        try:
            body = json.loads(message.body.decode())
            request_id = body.get("request_id", "unknown")
            session_id = body.get("session_id", "")
            routing_key = body.get("endpoint", "")
            payload = body.get("payload", {})
            reply_to = message.properties.reply_to or body.get("reply_to", "")

            logger.info(
                "[%s] Worker %s 收到: routing=%s session=%s",
                request_id, WORKER_ID, routing_key, session_id,
            )

            # 加载 Session
            session = await self._sessions.load_session(session_id)

            # 创建 Agent
            agent = self._factory.create(session)

            # 执行
            answer = await agent.run_query(payload.get("query", ""))

            latency_ms = int((time.perf_counter() - t0) * 1000)

            response = {
                "request_id": request_id,
                "session_id": session_id,
                "status": "success",
                "data": {"answer": answer},
                "latency_ms": latency_ms,
                "worker_id": WORKER_ID,
            }

            # 保存 Session
            await self._sessions.save_session(session)

            # 回复
            if reply_to:
                await self._channel.basic_publish(
                    body=json.dumps(response, ensure_ascii=False).encode(),
                    exchange="",
                    routing_key=reply_to,
                )

            await self._channel.basic_ack(message.delivery.delivery_tag)
            logger.info(
                "[%s] Worker %s 完成: latency=%dms",
                request_id, WORKER_ID, latency_ms,
            )

        except Exception as exc:
            logger.error("Worker %s 处理失败: %s", WORKER_ID, exc, exc_info=True)
            await self._channel.basic_nack(message.delivery.delivery_tag, requeue=False)


async def main():
    """Worker 入口."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    worker = Worker()

    loop = None
    try:
        await worker.start()
        # 保持运行直到收到停止信号
    except KeyboardInterrupt:
        pass
    finally:
        await worker.stop()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add worker/consumer.py
git commit -m "feat(worker): add RabbitMQ consumer main loop with session load/save

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Phase 4: 业务逻辑

### Task 4.1: engine/rule_engine.py — 车型参数标准化提取

**Files:**
- Create: `engine/__init__.py`
- Create: `engine/rule_engine.py`

- [ ] **Step 1: 创建 engine/__init__.py**

```python
"""Engine 包 — 规则引擎 + 打分 + 对比编排."""
```

- [ ] **Step 2: 创建 engine/rule_engine.py**

```python
"""车型参数规则引擎 — 从非结构化文本中提取标准化参数."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class RuleEngine:
    """基于规则的车型参数提取器.

    从 RAG 检索到的文本中按正则 + 关键字匹配提取标准化参数.
    LLM 不可用时作为降级方案直接返回结构化数据.
    """

    # 参数提取规则: {参数名: [匹配模式列表]}
    PARAM_RULES: Dict[str, List[str]] = {
        "价格": [r"(\d+\.?\d*)\s*万", r"售价[：:]\s*(\d+\.?\d*)", r"指导价[：:]\s*(\d+\.?\d*)"],
        "续航": [r"续航[：:]\s*(\d+)", r"(\d+)\s*公里", r"NEDC[：:]?\s*(\d+)"],
        "功率": [r"(\d+)\s*kW", r"最大功率[：:]\s*(\d+)", r"(\d+)\s*千瓦"],
        "加速": [r"0?[-\s]*100[公km]*[里/小时]*[：:]*\s*(\d+\.?\d*)\s*秒", r"百公里加速[：:]\s*(\d+\.?\d*)"],
        "电池": [r"(\d+\.?\d*)\s*kWh", r"电池容量[：:]\s*(\d+\.?\d*)"],
        "智驾": [r"(L\d+)[级别]*自动驾驶", r"智驾[：:]\s*(.+)", r"智能驾驶[：:]\s*(.+?)[\n，]"],
        "尺寸": [r"(\d{4})\s*[×xX]\s*(\d{4})\s*[×xX]\s*(\d{4})"],
    }

    def extract(self, text: str, aspects: Optional[List[str]] = None) -> Dict[str, Any]:
        """从文本中提取指定维度的参数.

        Args:
            text: 非结构化车型描述文本.
            aspects: 要提取的维度列表. None 表示全部.

        Returns:
            Dict: {维度名: [匹配值列表]}
        """
        target = aspects or list(self.PARAM_RULES.keys())
        result: Dict[str, List[str]] = {}

        for aspect in target:
            patterns = self.PARAM_RULES.get(aspect, [])
            matches = []
            for pattern in patterns:
                found = re.findall(pattern, text, re.IGNORECASE)
                for f in found:
                    if isinstance(f, tuple):
                        matches.append(" × ".join(f))
                    else:
                        matches.append(str(f))
            if matches:
                result[aspect] = matches[:3]  # 最多保留3个匹配

        return result

    def extract_multi(
        self,
        texts: Dict[str, str],
        aspects: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """从多车型文本中批量提取参数.

        Args:
            texts: {车型名: 描述文本}
            aspects: 提取维度.

        Returns:
            Dict: {车型名: {维度: [值]}}
        """
        return {
            vehicle: self.extract(text, aspects)
            for vehicle, text in texts.items()
        }
```

- [ ] **Step 3: Commit**

```bash
git add engine/__init__.py engine/rule_engine.py
git commit -m "feat(engine): add RuleEngine for regex-based vehicle parameter extraction

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4.2: engine/scorer.py — 多维度 LLM 打分

**Files:**
- Create: `engine/scorer.py`

- [ ] **Step 1: 创建 engine/scorer.py**

```python
"""智能推荐打分器 — LLM 多维度评分."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from infrastructure.llm_pool import LLMPool

logger = logging.getLogger(__name__)

# 默认打分维度及权重
DEFAULT_SCORE_DIMENSIONS = {
    "性价比": 0.25,
    "安全性": 0.20,
    "空间舒适": 0.15,
    "智能化": 0.15,
    "品牌售后": 0.10,
    "能耗经济": 0.15,
}


class Scorer:
    """基于 LLM 的多维度车型打分器."""

    def __init__(self, llm_pool: LLMPool) -> None:
        self._llm = llm_pool

    async def score_vehicle(
        self,
        vehicle_name: str,
        vehicle_info: str,
        user_context: Optional[Dict[str, Any]] = None,
        dimensions: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """对单个车型进行多维度打分.

        Args:
            vehicle_name: 车型名称.
            vehicle_info: 车型参数/描述文本.
            user_context: 用户偏好/场景上下文.
            dimensions: 打分维度及权重.

        Returns:
            Dict: {vehicle, total_score, dimensions: {dim: {score, reason}}}
        """
        dims = dimensions or DEFAULT_SCORE_DIMENSIONS
        dim_names = list(dims.keys())

        system_prompt = (
            "你是一个专业的汽车评测评分专家。请对给定车型按以下维度分别打分(0-10分):\n"
            + "\n".join(f"- {d}" for d in dim_names)
            + "\n\n输出 JSON 格式: {\"scores\": [{\"dimension\": \"...\", \"score\": 8.5, \"reason\": \"...\"}]}"
        )

        user_prompt = f"车型: {vehicle_name}\n车型信息:\n{vehicle_info[:2000]}"
        if user_context:
            user_prompt += f"\n\n用户偏好: {user_context}"

        try:
            result = await self._llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=1024,
            )

            scores = result.get("scores", [])
            dim_scores: Dict[str, Dict[str, Any]] = {}
            total = 0.0

            for item in scores:
                dim = item.get("dimension", "")
                score = float(item.get("score", 0))
                reason = item.get("reason", "")
                weight = dims.get(dim, 0.0)
                dim_scores[dim] = {"score": score, "reason": reason, "weight": weight}
                total += score * weight

            return {
                "vehicle": vehicle_name,
                "total_score": round(total, 2),
                "dimensions": dim_scores,
            }
        except Exception as e:
            logger.error("打分失败: vehicle=%s error=%s", vehicle_name, e)
            return {
                "vehicle": vehicle_name,
                "total_score": 0.0,
                "dimensions": {},
                "error": str(e),
            }

    async def score_multi(
        self,
        vehicles: Dict[str, str],
        user_context: Optional[Dict[str, Any]] = None,
        dimensions: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """对多个车型并行打分.

        Args:
            vehicles: {车型名: 描述文本}
            user_context: 用户偏好/场景.
            dimensions: 打分维度.

        Returns:
            List: 按总分降序排列的打分结果.
        """
        import asyncio

        tasks = [
            self.score_vehicle(name, info, user_context, dimensions)
            for name, info in vehicles.items()
        ]
        results = await asyncio.gather(*tasks)
        results.sort(key=lambda r: r["total_score"], reverse=True)
        logger.info("多车型打分完成: vehicles=%d", len(results))
        return results
```

- [ ] **Step 2: Commit**

```bash
git add engine/scorer.py
git commit -m "feat(engine): add LLM-based multi-dimension vehicle scorer

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4.3: engine/comparator.py — 多车型对比编排

**Files:**
- Create: `engine/comparator.py`

- [ ] **Step 1: 创建 engine/comparator.py**

```python
"""多车型对比编排器."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from engine.rule_engine import RuleEngine
from infrastructure.llm_pool import LLMPool

logger = logging.getLogger(__name__)


class Comparator:
    """多车型横向对比 —— 规则提取 + LLM 对比总结."""

    def __init__(self, llm_pool: LLMPool) -> None:
        self._llm = llm_pool
        self._rules = RuleEngine()

    async def compare(
        self,
        vehicle_data: Dict[str, str],
        aspects: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """执行多车型对比.

        Args:
            vehicle_data: {车型名: RAG检索文本}.
            aspects: 对比维度.

        Returns:
            Dict: {comparison_table, llm_summary, structured_params}
        """
        # 1. 规则引擎提取标准化参数
        structured = self._rules.extract_multi(vehicle_data, aspects)

        # 2. 构建对比上下文
        context_parts = []
        for vehicle, text in vehicle_data.items():
            context_parts.append(f"=== {vehicle} ===\n{text[:1500]}")
        context_text = "\n\n".join(context_parts)

        aspect_list = aspects or list(self._rules.PARAM_RULES.keys())

        # 3. LLM 生成对比总结
        try:
            summary = await self._llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个专业的汽车对比评测编辑。请对以下车型进行横向对比分析。\n"
                            f"对比维度: {', '.join(aspect_list)}\n"
                            "输出结构化的 Markdown 对比报告, 包含:\n"
                            "1. 各维度逐一对比表格\n"
                            "2. 综合优劣势分析\n"
                            "3. 不同需求场景的推荐"
                        ),
                    },
                    {"role": "user", "content": f"车型信息:\n{context_text}\n\n请生成对比报告:"},
                ],
                temperature=0.3,
                max_tokens=2048,
            )
        except Exception as e:
            logger.error("LLM 对比生成失败: %s", e)
            summary = "对比生成失败，请参考下方的结构化参数对比。"

        return {
            "structured_params": structured,
            "llm_summary": summary,
            "vehicle_count": len(vehicle_data),
        }
```

- [ ] **Step 3: Commit**

```bash
git add engine/comparator.py
git commit -m "feat(engine): add Comparator for multi-vehicle comparison with rule extraction + LLM

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Phase 5: 部署与验证

### Task 5.1: supervisord.conf — Worker 进程管理

**Files:**
- Create: `supervisord.conf`

- [ ] **Step 1: 创建 supervisord.conf**

```ini
[supervisord]
logfile=/tmp/supervisord.log
pidfile=/tmp/supervisord.pid
nodaemon=true

[program:worker]
command=python -m worker.consumer
directory=/app
numprocs=4
process_name=worker-%(process_num)s
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=30
redirect_stderr=true
stdout_logfile=/tmp/worker-%(process_num)s.log

[program:gateway]
command=uvicorn gateway.app:app --host 0.0.0.0 --port 8000
directory=/app
numprocs=2
process_name=gateway-%(process_num)s
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/tmp/gateway-%(process_num)s.log
```

- [ ] **Step 2: Commit**

```bash
git add supervisord.conf
git commit -m "feat(deploy): add supervisord config for Worker + Gateway process management

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5.2: Dockerfile — 容器化

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: 创建 Dockerfile**

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 暴露 Gateway 端口
EXPOSE 8000

# 默认启动 Gateway (生产由 supervisord 管理)
CMD ["uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Commit**

```bash
git add Dockerfile
git commit -m "feat(deploy): add Dockerfile for containerized deployment

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5.3: 端到端集成测试

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: 创建 tests 目录和集成测试**

```bash
mkdir -p c:/Users/18049/Desktop/agent_car/tests
```

```python
"""端到端集成测试 — 验证 Gateway → RabbitMQ → Worker 完整链路."""

import asyncio
import json
import pytest
import uuid


@pytest.mark.asyncio
async def test_session_isolation():
    """验证两个独立 session 的记忆不串扰."""
    # 此测试需要 Redis + RabbitMQ + Worker 运行中
    # 可通过 docker-compose up 启动基础设施
    ...


@pytest.mark.asyncio
async def test_vehicle_query_end_to_end():
    """验证车型查询端到端."""
    ...


@pytest.mark.asyncio
async def test_rate_limit_blocks_excess():
    """验证限流正确拦截超量请求."""
    ...
```

- [ ] **Step 2: Commit**

```bash
git add tests/
git commit -m "test: add integration test stubs for e2e concurrency validation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5.4: 清理旧代码 — 移除 frontend/backend/server.py 中的全局单例

**Files:**
- Modify: `frontend/backend/server.py:176-193`

- [ ] **Step 1: 标记 get_agent() 为废弃**

在 `get_agent` 函数上方添加废弃警告：

```python
import warnings

def get_agent() -> AutoSalesAgent:
    """[DEPRECATED] 获取 AutoSalesAgent 单例.

    警告: 此函数在高并发改造后不再适用。
    请使用 worker/agent_factory.py 中的 AgentFactory 创建请求级 Agent。
    """
    warnings.warn(
        "get_agent() is deprecated. Use AgentFactory for request-scoped agents.",
        DeprecationWarning,
        stacklevel=2,
    )
    global _agent
    if _agent is None:
        _agent = AutoSalesAgent()
    return _agent
```

- [ ] **Step 2: Commit**

```bash
git add frontend/backend/server.py
git commit -m "refactor(server): deprecate get_agent() singleton, point to AgentFactory

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5.X: 可观测性 — Prometheus Metrics + JSON 日志

**Files:**
- Create: `infrastructure/metrics.py`
- Modify: `gateway/app.py`
- Modify: `worker/consumer.py`

- [ ] **Step 1: 创建 infrastructure/metrics.py**

```python
"""Prometheus 指标收集."""

from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Gateway 指标
gateway_requests = Counter(
    "gateway_requests_total", "Total Gateway requests",
    ["endpoint", "status"],
)
gateway_latency = Histogram(
    "gateway_request_latency_seconds", "Gateway request latency",
    ["endpoint"], buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

# Worker 指标
worker_messages = Counter(
    "worker_messages_total", "Total Worker messages processed",
    ["queue", "status"],
)
worker_latency = Histogram(
    "worker_message_latency_seconds", "Worker message latency",
    ["queue"], buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)
llm_call_latency = Histogram(
    "llm_call_latency_seconds", "LLM API call latency",
    ["model"], buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)
rabbitmq_queue_depth = Gauge(
    "rabbitmq_queue_depth", "RabbitMQ queue message count",
    ["queue"],
)
```

- [ ] **Step 2: 在 gateway/app.py 中添加 /metrics 端点**

```python
from infrastructure.metrics import gateway_requests, gateway_latency, generate_latest

@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")
```

并在 `_handle_request` 中记录指标：

```python
gateway_requests.labels(endpoint=endpoint, status=result.get("status", "error")).inc()
gateway_latency.labels(endpoint=endpoint).observe(latency_ms / 1000.0)
```

- [ ] **Step 3: 在 worker/consumer.py 中记录 Worker 指标**

在 `_handle_message` 的 response 构建前添加：

```python
from infrastructure.metrics import worker_messages, worker_latency
worker_messages.labels(queue=routing_key, status="success").inc()
worker_latency.labels(queue=routing_key).observe(latency_ms / 1000.0)
```

- [ ] **Step 4: Commit**

```bash
git add infrastructure/metrics.py gateway/app.py worker/consumer.py
git commit -m "feat(observability): add Prometheus metrics for Gateway, Worker, LLM latency

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Known Issues & Future Work

1. **PlanningModule/ReflectionModule 同步调用兼容性**: Task 3.3/3.4 中 PlanningModule 和 ReflectionModule 的内部逻辑仍使用同步 OpenAI 客户端调用 (`self.llm_client.chat.completions.create()`)。当 AgentForRequest 传入 LLMPool (异步) 时会产生类型不匹配。建议在 LLMPool 中新增同步包装方法 `chat_sync()`，内部使用 `threading.Event` 或保持共享的同步 `openai.OpenAI` 客户端在 AgentFactory 层面分别管理同步/异步两个客户端。

2. **容错降级完整实现**: Spec Section 8 定义的 LLM/Milvus/Redis 降级逻辑在当前计划中以 Worker 异常捕获为基础，具体降级路径 (如 LLM 超时返回 RAG 原始结果) 需在 Phase 4 业务逻辑实现时逐条落地。

3. **集成测试**: Task 5.3 的集成测试需要 Redis + RabbitMQ + Worker 全部运行，仅提供骨架。完整的 E2E 测试应在基础设施就绪后填充实际断言。

---

## Completion Checklist

- [ ] Phase 1: config + deps + docker-compose 就绪
- [ ] Phase 2: Gateway 可启动, 4 个端点 + 鉴权 + 限流
- [ ] Phase 3: Worker 可消费, AgentForRequest 端到端运行
- [ ] Phase 4: RuleEngine + Scorer + Comparator 通过单元测试
- [ ] Phase 5: Docker 部署, 压测验证 2000 QPS
- [ ] `git log --oneline` 显示清晰的功能提交历史
- [ ] 旧 `main.py` CLI 模式仍可运行 (向后兼容)
- [ ] 旧 `frontend/backend/server.py` WebSocket 模式仍可运行 (带 deprecated 警告)
