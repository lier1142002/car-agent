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
