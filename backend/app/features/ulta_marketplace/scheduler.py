import os
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from rq_scheduler import Scheduler
from rq import Queue

from ...core.config import get_settings
from ...core.db import SessionLocal
from ...jobs.models import Job
from ...jobs.queues import get_redis_connection, get_default_queue
from .worker import run_ulta_export_job

logger = logging.getLogger(__name__)
settings = get_settings()


def create_daily_export_job():
    """
    Create a scheduled export job for the previous day.
    This function is called by the scheduler every morning.
    """
    db = SessionLocal()
    try:
        # Calculate yesterday's date range in Chicago timezone
        chicago_tz = ZoneInfo("America/Chicago")
        now_chicago = datetime.now(chicago_tz)

        # Yesterday at 6:00 AM Chicago time
        yesterday_start = (now_chicago - timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
        # Today at 5:59:59 AM Chicago time (end of yesterday)
        yesterday_end = now_chicago.replace(hour=5, minute=59, second=59, microsecond=999999)

        # Convert to UTC for API
        start_date_utc = yesterday_start.astimezone(ZoneInfo("UTC"))
        end_date_utc = yesterday_end.astimezone(ZoneInfo("UTC"))

        # Format as ISO strings
        start_date_str = start_date_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        end_date_str = end_date_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

        # Format for display
        start_date_display = yesterday_start.strftime('%Y-%m-%d')
        end_date_display = yesterday_start.strftime('%Y-%m-%d')

        logger.info(f"Scheduled export: Creating job for {start_date_display}")
        logger.info(f"  Date range: {start_date_str} to {end_date_str}")

        # Get API key
        ulta_api_key = os.getenv("ULTA_API_KEY") or settings.ulta_api_key
        if not ulta_api_key:
            logger.error("Ulta API key not configured, skipping scheduled export")
            return

        # Create job record
        job = Job(
            feature="ulta_marketplace",
            status="pending",
            input_filename="",
            options={
                "start_date": start_date_str,
                "end_date": end_date_str,
                "is_manual": False,  # Mark as scheduled, not manual
                "ulta_api_key": ulta_api_key,
                "progress": 0,
                "status_message": "Queued for processing (scheduled)",
                "start_date_display": start_date_display,
                "end_date_display": end_date_display
            }
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # Enqueue the job directly (not through scheduler, since we're already in a scheduled context)
        # Use the same queue that workers are listening to
        queue = get_default_queue()
        rq_job = queue.enqueue(run_ulta_export_job, job.id, job_timeout=3600)
        logger.info(f"Enqueued export job {job.id} to queue '{queue.name}', RQ job ID: {rq_job.id if rq_job else 'N/A'}")

        logger.info(f"Scheduled export job {job.id} created successfully for {start_date_display}")

    except Exception as e:
        logger.error(f"Error creating scheduled export job: {str(e)}", exc_info=True)
    finally:
        db.close()


def get_scheduler_status():
    """
    Get the status of the scheduler including next run time and last run time.
    Returns a dict with scheduler information.
    """
    try:
        conn = get_redis_connection()
        scheduler = Scheduler(connection=conn)

        # Check if scheduler is connected
        try:
            conn.ping()
            scheduler_connected = True
        except:
            scheduler_connected = False

        # Find the scheduled job by ID
        ulta_job = None
        try:
            # RQ Scheduler stores jobs in Redis, try to get by ID
            scheduled_jobs = scheduler.get_jobs()
            for job in scheduled_jobs:
                if job.id == "ulta_daily_export":
                    ulta_job = job
                    break
        except Exception as e:
            logger.debug(f"Could not get scheduled jobs: {e}")

        if not ulta_job:
            # Get last run time from database even if scheduler is not running
            db = SessionLocal()
            try:
                last_job = db.query(Job).filter(
                    Job.feature == "ulta_marketplace",
                    Job.options['is_manual'].astext == 'false'
                ).order_by(Job.created_at.desc()).first()

                last_run = None
                if last_job and last_job.created_at:
                    # Ensure timezone-aware datetime
                    last_run = last_job.created_at
                    if last_run.tzinfo is None:
                        # Assume UTC if timezone-naive
                        last_run = last_run.replace(tzinfo=timezone.utc)
            finally:
                db.close()

            return {
                "scheduler_running": scheduler_connected,
                "job_scheduled": False,
                "next_run": None,
                "last_run": last_run.isoformat() if last_run else None
            }

        # Get next run time from the scheduled job
        # Try to get the actual scheduled time from Redis first (most accurate)
        next_run = None
        try:
            # Get the scheduled time directly from Redis sorted set
            redis_conn = get_redis_connection()
            scheduled_score = redis_conn.zscore('rq:scheduler:scheduled_jobs', 'ulta_daily_export')
            if scheduled_score:
                # Convert Unix timestamp to datetime
                next_run = datetime.fromtimestamp(scheduled_score, tz=timezone.utc)
                logger.debug(f"Got scheduled time from Redis: {next_run}")
        except Exception as e:
            logger.debug(f"Could not get scheduled time from Redis: {e}")

        # Fallback: Try to get from job object
        if not next_run:
            if hasattr(ulta_job, 'scheduled_time') and ulta_job.scheduled_time:
                next_run = ulta_job.scheduled_time
                if next_run.tzinfo is None:
                    next_run = next_run.replace(tzinfo=timezone.utc)
            elif hasattr(ulta_job, 'meta') and ulta_job.meta:
                # Check if it's a recurring job with interval
                if 'interval' in ulta_job.meta:
                    interval_seconds = ulta_job.meta['interval']
                    # For recurring jobs, calculate next run based on when job was created and interval
                    now = datetime.now(timezone.utc)

                    # Get when the job was first scheduled (created_at)
                    if hasattr(ulta_job, 'created_at') and ulta_job.created_at:
                        # Ensure created_at is timezone-aware
                        created_at = ulta_job.created_at
                        if created_at.tzinfo is None:
                            created_at = created_at.replace(tzinfo=timezone.utc)

                        # Calculate how many intervals have passed
                        time_since_creation = (now - created_at).total_seconds()
                        intervals_passed = int(time_since_creation / interval_seconds)
                        next_interval = intervals_passed + 1
                        next_run = created_at + timedelta(seconds=next_interval * interval_seconds)
                    else:
                        # Fallback: next run is current time + interval
                        next_run = now + timedelta(seconds=interval_seconds)
                elif 'scheduled_time' in ulta_job.meta:
                    next_run = datetime.fromisoformat(ulta_job.meta['scheduled_time'])
                    if next_run.tzinfo is None:
                        next_run = next_run.replace(tzinfo=timezone.utc)

        # Get last run time from database (last scheduled job)
        db = SessionLocal()
        try:
            last_job = db.query(Job).filter(
                Job.feature == "ulta_marketplace",
                Job.options['is_manual'].astext == 'false'
            ).order_by(Job.created_at.desc()).first()

            last_run = None
            if last_job and last_job.created_at:
                # Ensure timezone-aware datetime
                last_run = last_job.created_at
                if last_run.tzinfo is None:
                    # Assume UTC if timezone-naive
                    last_run = last_run.replace(tzinfo=timezone.utc)
        finally:
            db.close()

        return {
            "scheduler_running": scheduler_connected,
            "job_scheduled": True,
            "next_run": next_run.isoformat() if next_run else None,
            "last_run": last_run.isoformat() if last_run else None
        }
    except Exception as e:
        logger.error(f"Error getting scheduler status: {str(e)}", exc_info=True)
        return {
            "scheduler_running": False,
            "job_scheduled": False,
            "next_run": None,
            "last_run": None,
            "error": str(e)
        }

