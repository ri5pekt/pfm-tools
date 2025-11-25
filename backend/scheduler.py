import os
import logging
from app.jobs.queues import get_redis_connection
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.jobs.models import ScheduledExport
from app.features.inventory_data.scheduler_service import schedule_rq_job as schedule_inventory_export
from app.features.ulta_marketplace.scheduler_service import schedule_rq_job as schedule_ulta_export

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)
settings = get_settings()


def main():
    """
    Load all enabled scheduled exports from the database and register them with RQ Scheduler.
    This replaces the old hardcoded scheduler.
    """
    db = SessionLocal()
    try:
        # Clear old hardcoded scheduler job if it exists
        from rq_scheduler import Scheduler
        conn = get_redis_connection()
        scheduler = Scheduler(connection=conn)
        
        try:
            old_job = scheduler.get_job("ulta_daily_export")
            if old_job:
                scheduler.cancel("ulta_daily_export")
                logger.info("Cleared old hardcoded scheduled job 'ulta_daily_export'")
        except Exception as e:
            logger.debug(f"Could not clear old job (may not exist): {e}")

        # Load all enabled scheduled exports
        scheduled_exports = db.query(ScheduledExport).filter(
            ScheduledExport.enabled == True
        ).all()

        logger.info(f"Found {len(scheduled_exports)} enabled scheduled export(s)")

        scheduled_count = 0
        for scheduled_export in scheduled_exports:
            try:
                # Use the appropriate scheduler service based on feature
                if scheduled_export.feature == "inventory_data":
                    rq_job_id = schedule_inventory_export(db, scheduled_export)
                elif scheduled_export.feature == "ulta_marketplace":
                    rq_job_id = schedule_ulta_export(db, scheduled_export)
                else:
                    logger.warning(f"Unknown feature '{scheduled_export.feature}' for scheduled export {scheduled_export.id}, skipping")
                    continue

                if rq_job_id:
                    scheduled_count += 1
                    logger.info(f"Successfully registered scheduled export {scheduled_export.id} ({scheduled_export.name})")
                else:
                    logger.error(f"Failed to register scheduled export {scheduled_export.id} ({scheduled_export.name})")
            except Exception as e:
                logger.error(f"Error registering scheduled export {scheduled_export.id}: {str(e)}", exc_info=True)

        logger.info(f"Successfully registered {scheduled_count} of {len(scheduled_exports)} scheduled exports")
        logger.info("RQ Scheduler initialization complete. The rqscheduler process will handle execution.")

    except Exception as e:
        logger.error(f"Error initializing scheduler: {str(e)}", exc_info=True)
    finally:
        db.close()

    # Exit after scheduling - the rqscheduler command (run separately) will process jobs
    # This script just schedules the jobs, rqscheduler handles execution
    import sys
    sys.exit(0)


if __name__ == "__main__":
    main()

