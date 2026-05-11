import logging
from datetime import datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from rq_scheduler import Scheduler
from ...core.config import get_settings
from ...jobs.models import ScheduledExport
from ...jobs.queues import get_redis_connection
from .worker import run_one_time_vs_subscription_export_job

logger = logging.getLogger(__name__)
settings = get_settings()


def create_scheduled_export_job(scheduled_export_id: int):
    """
    Called by RQ scheduler when the scheduled time arrives.
    Creates a job for the previous calendar day in America/New_York timezone.
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

        woo_base_url = settings.woo_base_url
        woo_consumer_key = settings.woo_consumer_key
        woo_consumer_secret = settings.woo_consumer_secret

        if not woo_base_url or not woo_consumer_key or not woo_consumer_secret:
            logger.error("WooCommerce credentials not configured, skipping scheduled export")
            return

        ny_tz = ZoneInfo("America/New_York")
        now_ny = datetime.now(ny_tz)
        yesterday_date = (now_ny - timedelta(days=1)).date()

        yesterday_start = datetime.combine(yesterday_date, dt_time(0, 0, 0)).replace(tzinfo=ny_tz)
        yesterday_end = datetime.combine(yesterday_date, dt_time(23, 59, 59, 999999)).replace(tzinfo=ny_tz)

        yesterday_start_utc = yesterday_start.astimezone(ZoneInfo("UTC"))
        yesterday_end_utc = yesterday_end.astimezone(ZoneInfo("UTC"))

        date_from_str = yesterday_start_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        date_to_str = yesterday_end_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        date_display = yesterday_start.strftime('%Y-%m-%d')

        logger.info(f"Scheduled export {scheduled_export_id}: Creating job for {date_display} (previous day)")

        export_options = scheduled_export.options or {}
        export_to_file = export_options.get("export_to_file", True)
        export_to_google_sheets = export_options.get("export_to_google_sheets", True)

        from ...jobs.models import Job
        job = Job(
            feature="one_time_vs_subscription",
            status="pending",
            input_filename="",
            options={
                "date_from": date_from_str,
                "date_to": date_to_str,
                "is_manual": False,
                "export_to_file": export_to_file,
                "export_to_google_sheets": export_to_google_sheets,
                "progress": 0,
                "status_message": "Queued for processing (scheduled)",
                "date_from_display": date_display,
                "date_to_display": date_display,
                "scheduled_export_id": scheduled_export_id,
            }
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        from ...jobs.queues import get_default_queue
        queue = get_default_queue()
        rq_job = queue.enqueue(run_one_time_vs_subscription_export_job, job.id, job_timeout=7200)
        logger.info(f"Scheduled export {scheduled_export_id}: Created job {job.id}, RQ job ID: {rq_job.id if rq_job else 'N/A'}")

        try:
            schedule_rq_job(db, scheduled_export)
            logger.info(f"Rescheduled next occurrence for scheduled export {scheduled_export_id}")
        except Exception as resched_exc:
            logger.warning(f"Could not reschedule next occurrence for {scheduled_export_id}: {resched_exc}")

    except Exception as e:
        logger.error(f"Error creating scheduled export job for {scheduled_export_id}: {e}", exc_info=True)
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

        if scheduled_export.rq_job_id:
            try:
                existing_job = scheduler.get_job(scheduled_export.rq_job_id)
                if existing_job:
                    scheduler.cancel(scheduled_export.rq_job_id)
                    logger.info(f"Cancelled existing RQ job {scheduled_export.rq_job_id}")
            except Exception as e:
                logger.debug(f"Could not cancel existing job (may not exist): {e}")

        frequency = scheduled_export.frequency if scheduled_export.frequency else 1
        if frequency < 1:
            frequency = 1

        target_tz = ZoneInfo(scheduled_export.timezone)
        now_target = datetime.now(target_tz)

        next_run_target = None
        interval_seconds = None

        if scheduled_export.period == "minute":
            next_run_target = now_target + timedelta(minutes=1)
            interval_seconds = frequency * 60

        elif scheduled_export.period == "daily":
            if not scheduled_export.time:
                raise ValueError("time is required for daily period")
            time_parts = str(scheduled_export.time).split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            next_run_target = now_target.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run_target <= now_target:
                next_run_target += timedelta(days=1)
            interval_seconds = frequency * 86400

        elif scheduled_export.period == "weekly":
            if scheduled_export.day_of_week is None:
                raise ValueError("day_of_week is required for weekly period")
            if not scheduled_export.time:
                raise ValueError("time is required for weekly period")
            time_parts = str(scheduled_export.time).split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            days_ahead = scheduled_export.day_of_week - now_target.weekday()
            if days_ahead <= 0:
                days_ahead += 7 * frequency
            elif days_ahead == 0 and now_target.hour >= hour and (now_target.hour > hour or now_target.minute >= minute):
                days_ahead = 7 * frequency
            next_run_target = now_target.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
            interval_seconds = frequency * 604800

        elif scheduled_export.period == "monthly":
            if scheduled_export.day_of_month is None:
                raise ValueError("day_of_month is required for monthly period")
            if not scheduled_export.time:
                raise ValueError("time is required for monthly period")
            time_parts = str(scheduled_export.time).split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            day = scheduled_export.day_of_month
            next_run_target = now_target.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
            if next_run_target <= now_target:
                months_to_add = frequency
                if next_run_target.month + months_to_add > 12:
                    next_run_target = next_run_target.replace(
                        year=next_run_target.year + 1,
                        month=(next_run_target.month + months_to_add - 12)
                    )
                else:
                    next_run_target = next_run_target.replace(month=next_run_target.month + months_to_add)
            while True:
                try:
                    next_run_target = next_run_target.replace(day=day)
                    break
                except ValueError:
                    if next_run_target.month == 12:
                        next_run_target = next_run_target.replace(year=next_run_target.year + 1, month=1, day=1)
                    else:
                        next_run_target = next_run_target.replace(month=next_run_target.month + 1, day=1)
                    next_month = next_run_target.replace(day=28) + timedelta(days=4)
                    last_day = (next_month - timedelta(days=next_month.day)).day
                    next_run_target = next_run_target.replace(day=min(day, last_day))
                    break
            interval_seconds = frequency * 2592000

        else:
            raise ValueError(f"Unknown period: {scheduled_export.period}")

        next_run_utc = next_run_target.astimezone(ZoneInfo("UTC"))
        next_run_utc_naive = next_run_utc.replace(tzinfo=None)

        rq_job_id = f"one_time_vs_subscription_scheduled_export_{scheduled_export.id}"

        if scheduled_export.period == "minute":
            logger.info(f"Scheduling export {scheduled_export.id} ({scheduled_export.name}): every {frequency} minute(s)")
        else:
            time_parts = str(scheduled_export.time).split(':') if scheduled_export.time else ['0', '0']
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            logger.info(f"Scheduling export {scheduled_export.id} ({scheduled_export.name}): every {frequency} {scheduled_export.period}(s) at {hour:02d}:{minute:02d} {scheduled_export.timezone}")
        logger.info(f"  Next run: {next_run_target} ({scheduled_export.timezone}) = {next_run_utc_naive} (UTC)")

        scheduler.schedule(
            scheduled_time=next_run_utc_naive,
            func=create_scheduled_export_job,
            args=(scheduled_export.id,),
            interval=interval_seconds,
            repeat=1,
            id=rq_job_id,
            queue_name=settings.rq_default_queue
        )

        scheduled_export.rq_job_id = rq_job_id
        db.commit()

        logger.info(f"Successfully scheduled RQ job {rq_job_id} for scheduled export {scheduled_export.id}")
        return rq_job_id

    except Exception as e:
        logger.error(f"Error scheduling RQ job for scheduled export {scheduled_export.id}: {e}", exc_info=True)
        return None


def unschedule_rq_job(db: Session, scheduled_export: ScheduledExport):
    """Cancel an RQ job for a ScheduledExport configuration."""
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
        logger.error(f"Error cancelling RQ job {scheduled_export.rq_job_id}: {e}", exc_info=True)
        return False
