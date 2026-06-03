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
