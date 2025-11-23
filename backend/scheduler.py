import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from rq_scheduler import Scheduler
from app.jobs.queues import get_redis_connection
from app.core.config import get_settings
from app.features.ulta_marketplace.scheduler import create_daily_export_job

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
    Start the RQ Scheduler to schedule daily Ulta exports.
    """
    conn = get_redis_connection()
    scheduler = Scheduler(connection=conn)

    # Get schedule time from environment or use default (6:00 AM Chicago time)
    # For testing, use 1 minute interval
    test_mode = os.getenv("ULTA_SCHEDULER_TEST_MODE", "false").lower() == "true"

    # Clear any existing scheduled job with the same ID
    try:
        existing_job = scheduler.get_job("ulta_daily_export")
        if existing_job:
            scheduler.cancel("ulta_daily_export")
            logger.info("Cleared existing scheduled job")
    except Exception:
        pass

    if test_mode:
        logger.info("TEST MODE: Scheduling exports every 1 minute")
        # Schedule to run every minute for testing
        # Calculate next run time (1 minute from now)
        next_run = datetime.now() + timedelta(minutes=1)
        scheduler.schedule(
            scheduled_time=next_run,
            func=create_daily_export_job,
            interval=60,  # 60 seconds = 1 minute
            repeat=None,  # Repeat indefinitely
            id="ulta_daily_export",
            queue_name=settings.rq_default_queue  # Use the correct queue name
        )
        logger.info(f"First test run scheduled for: {next_run}")
    else:
        # Production: Schedule for daily at specified time in specified timezone
        schedule_hour = int(os.getenv("ULTA_SCHEDULED_EXPORT_HOUR", "9"))
        schedule_minute = int(os.getenv("ULTA_SCHEDULED_EXPORT_MINUTE", "0"))
        schedule_timezone = os.getenv("ULTA_SCHEDULED_EXPORT_TIMEZONE", "Asia/Jerusalem")

        # Calculate next run time in the specified timezone
        target_tz = ZoneInfo(schedule_timezone)
        now_target = datetime.now(target_tz)
        next_run_target = now_target.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)

        # If the time has already passed today, schedule for tomorrow
        if next_run_target <= now_target:
            next_run_target += timedelta(days=1)

        # Convert to UTC for scheduler (RQ scheduler expects naive datetime in UTC)
        next_run_utc = next_run_target.astimezone(ZoneInfo("UTC"))
        next_run_utc_naive = next_run_utc.replace(tzinfo=None)

        logger.info(f"Production mode: Scheduling daily exports at {schedule_hour:02d}:{schedule_minute:02d} {schedule_timezone} time")
        logger.info(f"Next run scheduled for: {next_run_target} ({schedule_timezone}) = {next_run_utc_naive} (UTC)")

        scheduler.schedule(
            scheduled_time=next_run_utc_naive,
            func=create_daily_export_job,
            interval=86400,  # 24 hours in seconds
            repeat=None,  # Repeat indefinitely
            id="ulta_daily_export",
            queue_name=settings.rq_default_queue  # Use the correct queue name
        )

    logger.info("RQ Scheduler started successfully")
    logger.info("Job scheduled. The rqscheduler process will handle execution.")

    # Exit after scheduling - the rqscheduler command (run separately) will process jobs
    # This script just schedules the job, rqscheduler handles execution
    import sys
    sys.exit(0)


if __name__ == "__main__":
    main()

