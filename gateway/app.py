"""FastAPI Gateway 应用 — 路由 + 生命周期 + 用户认证."""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import config
from gateway.auth import (
    UserStore, UserRegister, UserLogin,
    get_current_user,
)
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
_user_store: UserStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭钩子."""
    global _publisher, _rate_limiter, _redis, _user_store

    logger.info("Gateway 启动中...")
    _redis = redis.from_url(config.redis_url, decode_responses=True)
    _rate_limiter = RateLimiter(_redis)
    _user_store = UserStore(_redis)
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


# =========================================================================
# 认证端点
# =========================================================================

@app.post("/api/auth/register")
async def auth_register(req: UserRegister):
    """用户注册."""
    ok = await _user_store.register(req.username, req.password)
    if not ok:
        raise HTTPException(status_code=409, detail="用户名已存在")
    token = create_jwt_from_module(req.username)
    return {"status": "ok", "token": token, "username": req.username}


@app.post("/api/auth/login")
async def auth_login(req: UserLogin):
    """用户登录."""
    valid = await _user_store.verify_password(req.username, req.password)
    if not valid:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_jwt_from_module(req.username)
    return {"status": "ok", "token": token, "username": req.username}


# =========================================================================
# v1 API — 通用请求处理
# =========================================================================

async def _handle_request(
    routing_key: str,
    payload: dict,
    session_id: str,
    user: dict,
    endpoint: str,
) -> ApiResponse:
    """通用请求处理: 限流 → 注入用户 API keys → 发布 → 等待回复."""
    username = user.get("username", "unknown")

    # 限流
    allowed = await _rate_limiter.check_and_increment(
        api_key=username,
        endpoint=endpoint,
        max_rps=user.get("rate_limit_rps", config.rate_limit_default_rps),
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


# =========================================================================
# 健康检查
# =========================================================================

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


# =========================================================================
# v1 业务路由 (需 JWT 认证)
# =========================================================================

@app.post("/api/v1/vehicle/query", response_model=ApiResponse)
async def vehicle_query(
    req: VehicleQueryRequest,
    user: dict = Depends(get_current_user),
) -> ApiResponse:
    return await _handle_request(
        routing_key="vehicle.query",
        payload={"query": req.query},
        session_id=req.session_id,
        user=user,
        endpoint="vehicle.query",
    )


@app.post("/api/v1/vehicle/compare", response_model=ApiResponse)
async def vehicle_compare(
    req: VehicleCompareRequest,
    user: dict = Depends(get_current_user),
) -> ApiResponse:
    return await _handle_request(
        routing_key="vehicle.compare",
        payload={"vehicles": req.vehicles, "aspects": req.aspects},
        session_id=req.session_id,
        user=user,
        endpoint="vehicle.compare",
    )


@app.post("/api/v1/recommend", response_model=ApiResponse)
async def recommend(
    req: RecommendRequest,
    user: dict = Depends(get_current_user),
) -> ApiResponse:
    return await _handle_request(
        routing_key="recommend",
        payload={
            "scenario": req.scenario,
            "budget": req.budget,
            "preferences": req.preferences,
        },
        session_id=req.session_id,
        user=user,
        endpoint="recommend",
    )


# =========================================================================
# 会话管理 (需 JWT 认证)
# =========================================================================

@app.post("/api/v1/session/create", response_model=ApiResponse)
async def session_create(
    user: dict = Depends(get_current_user),
) -> ApiResponse:
    """创建新会话."""
    import uuid as _uuid
    username = user.get("username", "default_user")
    session_id = f"sess_{_uuid.uuid4().hex[:16]}"

    await _redis.hset(f"session:{session_id}", mapping={
        "user_id": username,
        "created_at": str(time.time()),
        "message_count": "0",
    })
    await _redis.expire(f"session:{session_id}", config.redis_session_ttl)
    await _redis.sadd(f"user:{username}:sessions", session_id)

    logger.info("会话已创建: session=%s user=%s", session_id, username)
    return ApiResponse(
        request_id="",
        session_id=session_id,
        status="success",
        data={"session_id": session_id, "user_id": username},
    )


@app.get("/api/v1/sessions")
async def list_sessions(
    user: dict = Depends(get_current_user),
):
    """列出当前用户的所有活跃会话."""
    username = user.get("username", "default_user")
    session_ids = await _redis.smembers(f"user:{username}:sessions")
    sessions = []
    for sid in session_ids:
        meta = await _redis.hgetall(f"session:{sid}")
        if meta:
            sessions.append({
                "session_id": sid,
                "user_id": meta.get("user_id", ""),
                "message_count": int(meta.get("message_count", 0)),
                "created_at": meta.get("created_at", ""),
            })
    sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return {"sessions": sessions, "user_id": username}


@app.post("/api/v1/session/close", response_model=ApiResponse)
async def session_close(
    req: SessionCloseRequest,
    user: dict = Depends(get_current_user),
) -> ApiResponse:
    await _redis.delete(
        f"session:{req.session_id}",
        f"session:{req.session_id}:messages",
        f"session:{req.session_id}:state",
    )
    await _redis.srem(f"user:{req.user_id}:sessions", req.session_id)
    logger.info("会话已关闭: session_id=%s", req.session_id)
    return ApiResponse(
        request_id="",
        session_id=req.session_id,
        status="success",
    )


# =========================================================================
# 管理接口 — 用户配置 (需 JWT 认证)
# =========================================================================

# --- Schemas ---

class ConfigSettings(BaseModel):
    llm_api_key: str = ""
    serpapi_key: str = ""
    llamaparse_api_key: str = ""
    embedding_model: str = ""
    llm_model: str = ""
    llm_api_url: str = ""
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048


class PdfUploadResponse(BaseModel):
    status: str
    filename: str = ""
    chunks: int = 0
    message: str = ""


class EvalRunRequest(BaseModel):
    dataset_name: str = Field(..., min_length=1)
    retrieval_mode: str = Field("hybrid", pattern="^(dense|sparse|hybrid)$")
    top_k: int = Field(5, ge=1, le=50)
    generate_answers: bool = Field(True)


class DatasetItem(BaseModel):
    name: str
    total_samples: int
    by_type: dict
    by_difficulty: dict


# --- Agent 单例 (管理接口用) ---

_agent: Any = None


def _get_agent() -> Any:
    global _agent
    if _agent is None:
        from agent.agent_core import AutoSalesAgent
        logger.info("AutoSalesAgent 管理单例初始化中 ...")
        _agent = AutoSalesAgent()
        logger.info("管理单例就绪: %s", _agent.executor.get_tool_names())
    return _agent


def _mask_api_key(key: str) -> str:
    if not key or "your-" in key:
        return ""
    if len(key) <= 8:
        return "***"
    return key[:3] + "***" + key[-4:]


# --- 全局配置 (只读, 所有用户共享 .env) ---

@app.get("/api/config")
async def get_config(user: dict = Depends(get_current_user)):
    """获取全局配置 (脱敏). 所有用户共享 .env 中的 API Key."""
    return ConfigSettings(
        llm_api_key=_mask_api_key(config.llm_api_key),
        serpapi_key=_mask_api_key(config.serpapi_key),
        llamaparse_api_key=_mask_api_key(config.llamaparse_api_key),
        embedding_model=config.local_embedding_model,
        llm_model=config.llm_model,
        llm_api_url=config.llm_api_url,
        llm_temperature=config.llm_temperature,
        llm_max_tokens=config.llm_max_tokens,
    )


# --- PDF 上传 ---

@app.post("/api/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return PdfUploadResponse(status="error", filename=file.filename or "", message="仅支持 PDF 文件")
    agent = _get_agent()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        chunk_count = agent.index_knowledge_base(tmp_path)
        logger.info("PDF 上传索引: %s -> %d 块 (user=%s)", file.filename, chunk_count, user.get("username"))
        return PdfUploadResponse(status="success", filename=file.filename, chunks=chunk_count, message=f"已切分为 {chunk_count} 块")
    except Exception as exc:
        logger.error("PDF 上传失败: %s", exc)
        return PdfUploadResponse(status="error", filename=file.filename, message=str(exc))
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass


# --- Agent 状态 ---

@app.get("/api/state")
async def get_state(user: dict = Depends(get_current_user)):
    agent = _get_agent()
    raw = agent.get_state()
    return {
        "memory": raw.get("memory", []),
        "tools": raw.get("tools", []),
        "rag_indexed": bool(raw.get("rag_indexed", False)),
        "iteration_count": int(raw.get("iteration_count", 0)),
    }


# --- RAG 评测 ---

@app.get("/api/eval/datasets")
async def get_eval_datasets(user: dict = Depends(get_current_user)):
    from eval.dataset import GoldenDataset
    datasets_dir = Path(__file__).resolve().parent.parent / "eval" / "datasets"
    items: List[DatasetItem] = []
    if not datasets_dir.exists():
        return items
    for f in sorted(datasets_dir.glob("*.json")):
        try:
            ds = GoldenDataset.load(f)
            summary = ds.summary()
            items.append(DatasetItem(
                name=f.name,
                total_samples=summary["total_samples"],
                by_type=summary.get("by_type", {}),
                by_difficulty=summary.get("by_difficulty", {}),
            ))
        except Exception as exc:
            logger.warning("加载数据集失败: %s - %s", f.name, exc)
    return items


@app.post("/api/eval/run")
async def run_eval(request: EvalRunRequest, user: dict = Depends(get_current_user)):
    from eval.dataset import GoldenDataset
    from eval.runner import EvalRunner
    agent = _get_agent()
    state = agent.get_state()
    if not state.get("rag_indexed", False):
        raise HTTPException(status_code=400, detail="请先索引知识库")
    datasets_dir = Path(__file__).resolve().parent.parent / "eval" / "datasets"
    dataset_path = datasets_dir / request.dataset_name
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"数据集不存在: {request.dataset_name}")
    try:
        dataset = GoldenDataset.load(dataset_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"数据集加载失败: {exc}")
    try:
        runner = EvalRunner(rag_tool=agent.rag_tool, top_k=request.top_k)
        report = runner.run(dataset, retrieval_mode=request.retrieval_mode, generate_answers=request.generate_answers)
        return report.to_dict()
    except Exception as exc:
        logger.error("评测失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"评测运行失败: {exc}")


@app.post("/api/eval/sweep")
async def run_eval_sweep(request: EvalRunRequest, user: dict = Depends(get_current_user)):
    from eval.dataset import GoldenDataset
    from eval.runner import EvalRunner
    agent = _get_agent()
    state = agent.get_state()
    if not state.get("rag_indexed", False):
        raise HTTPException(status_code=400, detail="请先索引知识库")
    datasets_dir = Path(__file__).resolve().parent.parent / "eval" / "datasets"
    dataset_path = datasets_dir / request.dataset_name
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"数据集不存在: {request.dataset_name}")
    try:
        dataset = GoldenDataset.load(dataset_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"数据集加载失败: {exc}")
    try:
        runner = EvalRunner(rag_tool=agent.rag_tool, top_k=request.top_k)
        reports = runner.sweep_weights(dataset, generate_answers=request.generate_answers)
        return [r.to_dict() for r in reports]
    except Exception as exc:
        logger.error("权重扫描失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"权重扫描失败: {exc}")


# --- 兼容旧版 ---

@app.get("/api/health")
async def health_legacy():
    return {"status": "ok"}


# =========================================================================
# 模块内 JWT 创建 (避免循环导入)
# =========================================================================

def create_jwt_from_module(username: str) -> str:
    from gateway.auth import create_jwt
    return create_jwt(username)
