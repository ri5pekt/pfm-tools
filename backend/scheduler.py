import os
import logging
from app.jobs.queues import get_redis_connection
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.jobs.models import ScheduledExport
from app.features.inventory_data.scheduler_service import schedule_rq_job as schedule_inventory_export
from app.features.ulta_marketplace.scheduler_service import schedule_rq_job as schedule_ulta_export
from app.features.daily_orders_data.scheduler_service import schedule_rq_job as schedule_daily_orders_export

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

        # Cancel ALL old hardcoded jobs - be thorough to prevent duplicates
        old_job_ids = ["ulta_daily_export", "ulta_marketplace_scheduled_export_1", "ulta_marketplace_scheduled_export_2"]

        # First, get all scheduled jobs and cancel any that match old patterns
        try:
            all_jobs = scheduler.get_jobs()
            for job in all_jobs:
                if job.id in old_job_ids or job.id.startswith("ulta_daily_export"):
                    try:
                        scheduler.cancel(job.id)
                        logger.info(f"Cleared old scheduled job '{job.id}'")
                    except Exception as e:
                        logger.debug(f"Could not cancel job '{job.id}': {e}")
        except Exception as e:
            logger.debug(f"Could not get all jobs: {e}")

        # Also cancel by ID directly (in case get_jobs() missed them)
        for old_job_id in old_job_ids:
            try:
                existing_job = scheduler.get_job(old_job_id)
                if existing_job:
                    scheduler.cancel(old_job_id)
                    logger.info(f"Cleared old scheduled job '{old_job_id}'")
            except Exception as e:
                # Job may not exist, which is fine
                logger.debug(f"Could not clear old job '{old_job_id}' (may not exist): {e}")

        # Also delete from Redis directly to ensure complete cleanup
        # This handles orphaned jobs that might not be in the scheduler
        for old_job_id in old_job_ids:
            try:
                # Delete job data
                conn.delete(f"rq:job:{old_job_id}")
                conn.delete(f"rq:results:{old_job_id}")
                # Remove from scheduled jobs sorted set (this is critical - it's where RQ Scheduler looks)
                removed = conn.zrem('rq:scheduler:scheduled_jobs', old_job_id)
                if removed:
                    logger.info(f"Removed '{old_job_id}' from scheduled_jobs sorted set")
                logger.debug(f"Cleaned up Redis keys for '{old_job_id}'")
            except Exception as e:
                logger.debug(f"Could not clean Redis keys for '{old_job_id}': {e}")

        # Final check: Get all scheduled jobs and verify no old jobs remain
        try:
            final_check = scheduler.get_jobs()
            remaining_old_jobs = [job.id for job in final_check if job.id in old_job_ids]
            if remaining_old_jobs:
                logger.warning(f"WARNING: Old jobs still exist after cleanup: {remaining_old_jobs}")
                # Try one more time to remove them from Redis sorted set
                for old_job_id in remaining_old_jobs:
                    conn.zrem('rq:scheduler:scheduled_jobs', old_job_id)
                    logger.info(f"Force-removed '{old_job_id}' from scheduled_jobs sorted set")
            else:
                logger.info("✓ All old scheduled jobs successfully cleaned up")
        except Exception as e:
            logger.debug(f"Could not perform final check: {e}")

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
                elif scheduled_export.feature == "daily_orders_data":
                    rq_job_id = schedule_daily_orders_export(db, scheduled_export)
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

