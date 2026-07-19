import os
from dataclasses import dataclass


@dataclass
class Config:
    redis_host: str
    redis_port: int
    queue_key: str
    result_key_prefix: str
    result_ttl: int
    log_level: str
    otel_endpoint: str
    fault_mode: bool

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            queue_key="tahseen:queue",
            result_key_prefix="tahseen:result:",
            result_ttl=3600,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            otel_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"),
            fault_mode=os.getenv("FAULT_MODE", "").lower() in ("1", "true", "yes"),
        )
