import os
import logging
from datetime import datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from rq_scheduler import Scheduler
from ...core.config import get_settings
from ...jobs.models import ScheduledExport
from ...jobs.queues import get_redis_connection
from .worker import run_inventory_data_export_job

logger = logging.getLogger(__name__)
settings = get_settings()


def create_scheduled_export_job(scheduled_export_id: int):
    """
    Create an actual export job from a scheduled export configuration.
    This function is called by the RQ scheduler when the scheduled time arrives.
    """
    from ...core.db import SessionLocal

    db = SessionLocal()
    try:
        scheduled_export = db.query(ScheduledExport).filter(
            ScheduledExport.id == scheduled_export_id,
            ScheduledExport.enabled == True
        ).first()

        if not scheduled_export:
            logger.warning(f"Scheduled export {scheduled_export_id} not found or disabled, skipping")
            return

        # Get API credentials from settings
        zenventory_username = settings.zenventory_klb_username
        zenventory_password = settings.zenventory_klb_password
        zenventory_base_url = settings.zenventory_klb_base_url
        shipbob_api_key = settings.shipbob_api_key
        shipbob_base_url = settings.shipbob_base_url

        if not zenventory_username or not zenventory_password:
            logger.error("Zenventory KLB credentials not configured, skipping scheduled export")
            return

        if not shipbob_api_key:
            logger.error("Shipbob API key not configured, skipping scheduled export")
            return

        # Get export date (today)
        export_date = datetime.now().strftime("%Y-%m-%d")
        export_date_display = export_date

        # Create job record
        from ...jobs.models import Job
        job = Job(
            feature="inventory_data",
            status="pending",
            input_filename="",
            options={
                "is_manual": False,
                "export_date": export_date,
                "export_date_display": export_date_display,
                "zenventory_username": zenventory_username,
                "zenventory_password": zenventory_password,
                "zenventory_base_url": zenventory_base_url,
                "shipbob_api_key": shipbob_api_key,
                "shipbob_base_url": shipbob_base_url,
                "progress": 0,
                "status_message": "Queued for processing (scheduled)",
                "scheduled_export_id": scheduled_export_id,
            }
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # Enqueue the job
        from ...jobs.queues import get_default_queue
        queue = get_default_queue()
        rq_job = queue.enqueue(run_inventory_data_export_job, job.id, job_timeout=3600)
        logger.info(f"Scheduled export {scheduled_export_id}: Created job {job.id}, RQ job ID: {rq_job.id if rq_job else 'N/A'}")

    except Exception as e:
        logger.error(f"Error creating scheduled export job for scheduled_export_id {scheduled_export_id}: {str(e)}", exc_info=True)
    finally:
        db.close()


def schedule_rq_job(db: Session, scheduled_export: ScheduledExport):
    """
    Schedule an RQ job for a ScheduledExport configuration.
    Returns the RQ job ID if successful, None otherwise.
    """
    try:
        conn = get_redis_connection()
        scheduler = Scheduler(connection=conn)

        # Cancel existing job if it exists
        if scheduled_export.rq_job_id:
            try:
                existing_job = scheduler.get_job(scheduled_export.rq_job_id)
                if existing_job:
                    scheduler.cancel(scheduled_export.rq_job_id)
                    logger.info(f"Cancelled existing RQ job {scheduled_export.rq_job_id}")
            except Exception as e:
                logger.debug(f"Could not cancel existing job (may not exist): {e}")

        # Get frequency (default to 1 if not set)
        frequency = scheduled_export.frequency if scheduled_export.frequency else 1
        if frequency < 1:
            frequency = 1

        # Calculate next run time based on period
        target_tz = ZoneInfo(scheduled_export.timezone)
        now_target = datetime.now(target_tz)

        next_run_target = None
        interval_seconds = None

        if scheduled_export.period == "minute":
            # Minute: run every X minutes (for testing)
            # Schedule to run immediately (or very soon), then repeat every frequency minutes
            next_run_target = now_target + timedelta(minutes=1)  # Start in 1 minute
            interval_seconds = frequency * 60  # Convert minutes to seconds

        elif scheduled_export.period == "daily":
            # Daily: run at specified time every X days
            if not scheduled_export.time:
                raise ValueError("time is required for daily period")

            # Parse time string (HH:MM format)
            time_parts = str(scheduled_export.time).split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0

            # Calculate next occurrence
            next_run_target = now_target.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # If time has passed today, start from tomorrow
            if next_run_target <= now_target:
                next_run_target += timedelta(days=1)

            # If frequency > 1, we need to find the next occurrence that matches the frequency
            # For example, if frequency is 3, we want every 3 days
            # We'll calculate the first occurrence, then the interval handles the rest
            interval_seconds = frequency * 86400  # frequency * 24 hours

        elif scheduled_export.period == "weekly":
            # Weekly: run on specified day of week at specified time every X weeks
            if scheduled_export.day_of_week is None:
                raise ValueError("day_of_week is required for weekly period")
            if not scheduled_export.time:
                raise ValueError("time is required for weekly period")

            # Parse time string (HH:MM format)
            time_parts = str(scheduled_export.time).split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0

            # Calculate days until next occurrence
            days_ahead = scheduled_export.day_of_week - now_target.weekday()
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7 * frequency  # Skip to next occurrence based on frequency
            elif days_ahead == 0 and now_target.hour >= hour and (now_target.hour > hour or now_target.minute >= minute):
                # If it's the target day but time has passed, schedule for next occurrence
                days_ahead = 7 * frequency
            else:
                # Find the next occurrence that matches the frequency
                # For frequency > 1, we need to find which "week cycle" we're in
                # This is simplified - we'll schedule the next matching day, then interval handles frequency
                pass

            next_run_target = now_target.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
            interval_seconds = frequency * 604800  # frequency * 7 days

        elif scheduled_export.period == "monthly":
            # Monthly: run on specified day of month at specified time every X months
            if scheduled_export.day_of_month is None:
                raise ValueError("day_of_month is required for monthly period")
            if not scheduled_export.time:
                raise ValueError("time is required for monthly period")

            # Parse time string (HH:MM format)
            time_parts = str(scheduled_export.time).split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0

            # Calculate next occurrence
            day = scheduled_export.day_of_month
            next_run_target = now_target.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)

            # If the day has passed this month, or if it's today but time has passed, schedule for next month
            if next_run_target <= now_target:
                # Move to next month (considering frequency)
                months_to_add = frequency
                if next_run_target.month + months_to_add > 12:
                    next_run_target = next_run_target.replace(year=next_run_target.year + 1, month=(next_run_target.month + months_to_add - 12))
                else:
                    next_run_target = next_run_target.replace(month=next_run_target.month + months_to_add)

            # Handle edge case: if day doesn't exist in target month (e.g., Feb 31), use last day of month
            while True:
                try:
                    # Try to create the date
                    test_date = next_run_target.replace(day=day)
                    next_run_target = test_date
                    break
                except ValueError:
                    # Day doesn't exist, use last day of month
                    if next_run_target.month == 12:
                        next_run_target = next_run_target.replace(year=next_run_target.year + 1, month=1, day=1)
                    else:
                        next_run_target = next_run_target.replace(month=next_run_target.month + 1, day=1)
                    # Get last day of month
                    next_month = next_run_target.replace(day=28) + timedelta(days=4)
                    last_day = (next_month - timedelta(days=next_month.day)).day
                    next_run_target = next_run_target.replace(day=min(day, last_day))
                    break

            # Calculate interval (approximate, as months vary in length)
            # For frequency > 1, we approximate: frequency * 30 days
            interval_seconds = frequency * 2592000  # frequency * ~30 days

        else:
            raise ValueError(f"Unknown period: {scheduled_export.period}")

        # Convert to UTC for scheduler
        next_run_utc = next_run_target.astimezone(ZoneInfo("UTC"))
        next_run_utc_naive = next_run_utc.replace(tzinfo=None)

        # Create unique RQ job ID
        rq_job_id = f"inventory_data_scheduled_export_{scheduled_export.id}"

        # Log scheduling info
        if scheduled_export.period == "minute":
            logger.info(f"Scheduling export {scheduled_export.id} ({scheduled_export.name}): every {frequency} minute(s)")
        else:
            time_parts = str(scheduled_export.time).split(':') if scheduled_export.time else ['0', '0']
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            logger.info(f"Scheduling export {scheduled_export.id} ({scheduled_export.name}): every {frequency} {scheduled_export.period}(s) at {hour:02d}:{minute:02d} {scheduled_export.timezone}")
        logger.info(f"  Next run: {next_run_target} ({scheduled_export.timezone}) = {next_run_utc_naive} (UTC)")

        # Schedule the job
        scheduler.schedule(
            scheduled_time=next_run_utc_naive,
            func=create_scheduled_export_job,
            args=(scheduled_export.id,),
            interval=interval_seconds,
            repeat=None,  # Repeat indefinitely
            id=rq_job_id,
            queue_name=settings.rq_default_queue
        )

        # Update scheduled_export with RQ job ID
        scheduled_export.rq_job_id = rq_job_id
        db.commit()

        logger.info(f"Successfully scheduled RQ job {rq_job_id} for scheduled export {scheduled_export.id}")
        return rq_job_id

    except Exception as e:
        logger.error(f"Error scheduling RQ job for scheduled export {scheduled_export.id}: {str(e)}", exc_info=True)
        return None


def unschedule_rq_job(db: Session, scheduled_export: ScheduledExport):
    """
    Cancel an RQ job for a ScheduledExport configuration.
    """
    if not scheduled_export.rq_job_id:
        return True

    try:
        conn = get_redis_connection()
        scheduler = Scheduler(connection=conn)

        scheduler.cancel(scheduled_export.rq_job_id)
        logger.info(f"Cancelled RQ job {scheduled_export.rq_job_id} for scheduled export {scheduled_export.id}")

        scheduled_export.rq_job_id = None
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Error cancelling RQ job {scheduled_export.rq_job_id}: {str(e)}", exc_info=True)
        return False

