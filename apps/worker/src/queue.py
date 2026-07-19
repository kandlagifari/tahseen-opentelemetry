import json
import logging
from typing import Any, Dict, Optional

import redis
from opentelemetry import trace
from opentelemetry.propagators.textmap import DefaultGetter
from opentelemetry.propagate import extract

logger = logging.getLogger(__name__)


class _DictGetter(DefaultGetter):
    def get(self, carrier: dict, key: str):
        val = carrier.get(key)
        return [val] if val is not None else []

    def keys(self, carrier: dict):
        return list(carrier.keys())


_getter = _DictGetter()


class QueueConsumer:
    def __init__(self, host: str, port: int, queue_key: str, result_key_prefix: str, result_ttl: int):
        self.host = host
        self.port = port
        self.queue_key = queue_key
        self.result_key_prefix = result_key_prefix
        self.result_ttl = result_ttl
        self.client: Optional[redis.Redis] = None

    def connect(self) -> None:
        self.client = redis.Redis(
            host=self.host,
            port=self.port,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )
        self.client.ping()
        logger.info("connected to redis", extra={"host": self.host, "port": self.port})

    def wait_for_job(self, timeout: int = 1) -> Optional[Dict[str, Any]]:
        if not self.client:
            raise RuntimeError("not connected")
        result = self.client.brpop([self.queue_key], timeout=timeout)
        if result is None:
            return None
        _, job_json = result
        job = json.loads(job_json)
        # extract W3C trace context injected by the API so the worker span
        # becomes a child of the originating request span
        ctx = extract(job, getter=_getter)
        job["_otel_ctx"] = ctx
        logger.info("received job", extra={"job_id": job.get("job_id")})
        return job

    def save_result(self, job_id: str, status: str, result: str = "", error: str = "") -> None:
        if not self.client:
            raise RuntimeError("not connected")
        self.client.hset(self.result_key_prefix + job_id, mapping={
            "status": status,
            "result": result,
            "error": error,
        })
        self.client.expire(self.result_key_prefix + job_id, self.result_ttl)

    def disconnect(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
        logger.info("disconnected from redis")
