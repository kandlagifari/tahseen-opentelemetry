import json
import logging
import signal
import sys
import time

from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode

from .config import Config
from .instrumentation import init_otel
from .queue import QueueConsumer
from .tajwid import check_tajwid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

shutdown_flag = False


def handle_shutdown(signum, frame):
    global shutdown_flag
    logger.info(f"received signal {signum}, shutting down")
    shutdown_flag = True


def process_job(consumer: QueueConsumer, job: dict, tracer, checks_counter, duration_hist, fault_mode: bool) -> None:
    job_id = job.get("job_id", "")
    text = job.get("text", "")
    parent_ctx = job.get("_otel_ctx")

    with tracer.start_as_current_span("worker.process_job", context=parent_ctx) as span:
        span.set_attribute("job.id", job_id)
        span.set_attribute("job.text_length", len(text))
        start = time.time()

        consumer.save_result(job_id, "processing")

        try:
            if fault_mode:
                time.sleep(2.0)
                raise RuntimeError("fault mode enabled")

            rules = check_tajwid(text)
            result = json.dumps(rules)
            duration = time.time() - start

            span.set_attribute("job.rule_count", len(rules))
            checks_counter.add(1, {"status": "completed"})
            duration_hist.record(duration, {"status": "completed"})

            consumer.save_result(job_id, "completed", result=result)
            logger.info("job completed", extra={"job_id": job_id, "duration_ms": int(duration * 1000), "rule_count": len(rules)})
        except Exception as e:
            duration = time.time() - start
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            checks_counter.add(1, {"status": "error"})
            duration_hist.record(duration, {"status": "error"})
            consumer.save_result(job_id, "error", error=str(e))
            logger.error("job failed", extra={"job_id": job_id, "error": str(e)})


def main() -> None:
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    config = Config.from_env()
    logging.getLogger().setLevel(config.log_level)

    init_otel("tahseen-worker", config.otel_endpoint)

    tracer = trace.get_tracer("tahseen-worker")
    meter = metrics.get_meter("tahseen-worker")
    checks_counter = meter.create_counter(
        "tahseen_checks_processed_total",
        description="Total number of tajwid checks processed",
    )
    duration_hist = meter.create_histogram(
        "tahseen_check_duration_seconds",
        description="Duration of tajwid check processing",
        unit="s",
    )

    consumer = QueueConsumer(
        host=config.redis_host,
        port=config.redis_port,
        queue_key=config.queue_key,
        result_key_prefix=config.result_key_prefix,
        result_ttl=config.result_ttl,
    )
    consumer.connect()
    logger.info("worker ready, waiting for jobs...", extra={"fault_mode": config.fault_mode})

    try:
        while not shutdown_flag:
            try:
                job = consumer.wait_for_job(timeout=1)
                if job is None:
                    continue
                process_job(consumer, job, tracer, checks_counter, duration_hist, config.fault_mode)
            except Exception as e:
                logger.error(f"error processing job: {e}", exc_info=True)
                time.sleep(1)
    finally:
        consumer.disconnect()
        logger.info("worker stopped")


if __name__ == "__main__":
    main()
