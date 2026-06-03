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
