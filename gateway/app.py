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
