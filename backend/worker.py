import logging

from rq import Worker
from app.jobs.queues import get_redis_connection
from app.core.config import get_settings

# Import job functions so RQ can find them
from app.features.sales_tax_processor.worker import run_sales_tax_job  # noqa
from app.features.order_comparison.worker import run_comparison_job  # noqa
from app.features.ulta_marketplace.worker import run_ulta_export_job  # noqa
from app.features.inventory_data.worker import run_inventory_data_export_job  # noqa
from app.features.tiktok_marketplace.worker import run_tiktok_export_job  # noqa
from app.features.daily_product_sales.worker import run_daily_product_sales_export_job  # noqa

# Configure logging
logging.basicConfig(
    level=logging.INFO,
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
