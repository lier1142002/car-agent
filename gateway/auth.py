"""JWT 认证 + 用户管理模块.

用户注册/登录 → JWT Token → Redis 持久化用户数据
每个用户可有自己的 API Key 配置，存储在 Redis 中.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# JWT 密钥 (生产环境应从环境变量或密钥管理服务获取)
_JWT_SECRET = os.getenv("JWT_SECRET", "agent_car_dev_secret_change_in_production")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_HOURS = 24


# =========================================================================
# Pydantic Schemas
# =========================================================================

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)


# =========================================================================
# JWT 工具
# =========================================================================

def create_jwt(username: str) -> str:
    """生成 JWT token."""
    payload = {
        "sub": username,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=_JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    """解析 JWT token, 返回 payload. 无效/过期时抛 HTTPException."""
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# =========================================================================
# 用户存储 (Redis)
# =========================================================================

class UserStore:
    """Redis 用户存储.

    Key 设计:
      user:{username}:info  — Hash: password_hash, created_at
    """

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def register(self, username: str, password: str) -> bool:
        """注册用户. 返回 True=成功, False=用户已存在."""
        key = f"user:{username}:info"
        exists = await self._redis.exists(key)
        if exists:
            return False
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        await self._redis.hset(key, mapping={
            "password_hash": hashed,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("用户注册: %s", username)
        return True

    async def verify_password(self, username: str, password: str) -> bool:
        """验证密码."""
        key = f"user:{username}:info"
        data = await self._redis.hgetall(key)
        if not data:
            return False
        stored = data.get("password_hash", "")
        return bcrypt.checkpw(password.encode(), stored.encode())


# =========================================================================
# FastAPI 鉴权依赖
# =========================================================================

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """从 Authorization Bearer header 解析 JWT, 返回用户上下文."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization format")
    token = authorization[7:]
    payload = decode_jwt(token)
    return {
        "username": payload["sub"],
        "rate_limit_rps": 100,
        "enabled": True,
    }
