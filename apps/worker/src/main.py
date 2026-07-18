import json
import logging
import signal
import sys
import time

from .config import Config
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


def process_job(consumer: QueueConsumer, job: dict) -> None:
    job_id = job.get("job_id", "")
    text = job.get("text", "")
    start = time.time()

    consumer.save_result(job_id, "processing")

    try:
        rules = check_tajwid(text)
        result = json.dumps(rules)
        duration_ms = int((time.time() - start) * 1000)
        consumer.save_result(job_id, "completed", result=result)
        logger.info(f"job {job_id} completed in {duration_ms}ms, rules={len(rules)}")
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        consumer.save_result(job_id, "error", error=str(e))
        logger.error(f"job {job_id} failed: {e}")


def main() -> None:
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    config = Config.from_env()
    logging.getLogger().setLevel(config.log_level)

    consumer = QueueConsumer(
        host=config.redis_host,
        port=config.redis_port,
        queue_key=config.queue_key,
        result_key_prefix=config.result_key_prefix,
        result_ttl=config.result_ttl,
    )
    consumer.connect()
    logger.info("worker ready, waiting for jobs...")

    try:
        while not shutdown_flag:
            try:
                job = consumer.wait_for_job(timeout=1)
                if job is None:
                    continue
                process_job(consumer, job)
            except Exception as e:
                logger.error(f"error processing job: {e}", exc_info=True)
                time.sleep(1)
    finally:
        consumer.disconnect()
        logger.info("worker stopped")


if __name__ == "__main__":
    main()
