import logging

from rq import Worker
from app.jobs.queues import get_redis_connection
from app.core.config import get_settings

# Import job functions so RQ can find them
from app.features.sales_tax_processor.worker import run_sales_tax_job  # noqa

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Temporarily set to DEBUG to see full request details
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

settings = get_settings()


def main():
    conn = get_redis_connection()
    worker = Worker([settings.rq_default_queue], connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
