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
