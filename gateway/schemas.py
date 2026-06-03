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
