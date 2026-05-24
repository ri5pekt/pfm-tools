import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from rq_scheduler import Scheduler

from ...core.config import get_settings
from ...jobs.models import LowStockAlert
from ...jobs.queues import get_redis_connection
from .low_stock_alert_worker import run_low_stock_alert_job
from .schedule_utils import get_alert_daily_times, get_alert_rq_job_ids, get_alert_thresholds, normalize_time_format

logger = logging.getLogger(__name__)
settings = get_settings()


def _time_slot_key(time_str: str) -> str:
    return normalize_time_format(time_str).replace(":", "")


def _rq_job_id_for_alert(alert_id: int, time_slot: str = None) -> str:
    if time_slot:
        return f"inventory_data_low_stock_alert_{alert_id}_{time_slot}"
    return f"inventory_data_low_stock_alert_{alert_id}"


def create_scheduled_alert_job(low_stock_alert_id: int, time_slot: str = None):
    """
    Create a low stock alert check job when the scheduled time arrives.
    """
    from ...core.db import SessionLocal

    db = SessionLocal()
    try:
        alert = db.query(LowStockAlert).filter(
            LowStockAlert.id == low_stock_alert_id,
            LowStockAlert.enabled == True,
        ).first()

        if not alert:
            logger.warning(f"Low stock alert {low_stock_alert_id} not found or disabled, skipping")
            return

        zenventory_username = settings.zenventory_klb_username
        zenventory_password = settings.zenventory_klb_password
        zenventory_base_url = settings.zenventory_klb_base_url
        shipbob_api_key = settings.shipbob_api_key
        shipbob_base_url = settings.shipbob_base_url

        if not zenventory_username or not zenventory_password:
            logger.error("Zenventory KLB credentials not configured, skipping low stock alert")
            return

        if not shipbob_api_key:
            logger.error("Shipbob API key not configured, skipping low stock alert")
            return

        from ...jobs.models import Job

        klb_threshold, shipbob_threshold = get_alert_thresholds(alert)

        job = Job(
            feature="inventory_data_low_stock_alert",
            status="pending",
            input_filename="",
            options={
                "is_manual": False,
                "low_stock_alert_id": low_stock_alert_id,
                "alert_name": alert.name,
                "threshold": alert.threshold,
                "klb_threshold": klb_threshold,
                "shipbob_threshold": shipbob_threshold,
                "slack_webhook_url": alert.slack_webhook_url,
                "excluded_skus": alert.excluded_skus or [],
                "zenventory_username": zenventory_username,
                "zenventory_password": zenventory_password,
                "zenventory_base_url": zenventory_base_url,
                "shipbob_api_key": shipbob_api_key,
                "shipbob_base_url": shipbob_base_url,
                "progress": 0,
                "status_message": "Queued for processing (scheduled)",
            },
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        from ...jobs.queues import get_default_queue

        queue = get_default_queue()
        rq_job = queue.enqueue(run_low_stock_alert_job, job.id, job_timeout=1800)
        logger.info(
            f"Low stock alert {low_stock_alert_id}: Created job {job.id}, "
            f"RQ job ID: {rq_job.id if rq_job else 'N/A'}"
        )

        try:
            schedule_rq_job(db, alert, time_slot=time_slot)
            logger.info(f"Rescheduled next occurrence for low stock alert {low_stock_alert_id}")
        except Exception as resched_exc:
            logger.warning(
                f"Could not reschedule next occurrence for alert {low_stock_alert_id}: {resched_exc}"
            )

    except Exception as e:
        logger.error(
            f"Error creating low stock alert job for alert_id {low_stock_alert_id}: {str(e)}",
            exc_info=True,
        )
    finally:
        db.close()


def _cancel_rq_jobs(scheduler: Scheduler, job_ids: list):
    for job_id in job_ids:
        try:
            existing_job = scheduler.get_job(job_id)
            if existing_job:
                scheduler.cancel(job_id)
                logger.info(f"Cancelled existing RQ job {job_id}")
        except Exception as e:
            logger.debug(f"Could not cancel job {job_id} (may not exist): {e}")


def _compute_daily_next_run(now_target: datetime, hour: int, minute: int, frequency: int) -> datetime:
    next_run_target = now_target.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run_target <= now_target:
        next_run_target += timedelta(days=frequency if frequency > 1 else 1)
    return next_run_target


def _schedule_daily_time_slot(
    scheduler: Scheduler,
    alert: LowStockAlert,
    time_str: str,
    frequency: int,
    target_tz: ZoneInfo,
    now_target: datetime,
) -> str:
    time_slot = _time_slot_key(time_str)
    rq_job_id = _rq_job_id_for_alert(alert.id, time_slot)

    time_parts = time_str.split(":")
    hour = int(time_parts[0])
    minute = int(time_parts[1])

    next_run_target = _compute_daily_next_run(now_target, hour, minute, frequency)
    next_run_utc_naive = next_run_target.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    interval_seconds = frequency * 86400

    logger.info(
        f"Scheduling alert {alert.id} ({alert.name}) daily at {time_str} {alert.timezone} "
        f"(next: {next_run_target})"
    )

    scheduler.schedule(
        scheduled_time=next_run_utc_naive,
        func=create_scheduled_alert_job,
        args=(alert.id, time_slot),
        interval=interval_seconds,
        repeat=1,
        id=rq_job_id,
        queue_name=settings.rq_default_queue,
    )

    return rq_job_id


def schedule_rq_job(db: Session, alert: LowStockAlert, time_slot: str = None):
    """
    Schedule RQ job(s) for a LowStockAlert configuration.
    For daily period with multiple times, schedules one job per time slot.
    If time_slot is provided, only reschedule that specific daily slot.
    """
    try:
        conn = get_redis_connection()
        scheduler = Scheduler(connection=conn)

        frequency = alert.frequency if alert.frequency else 1
        if frequency < 1:
            frequency = 1

        target_tz = ZoneInfo(alert.timezone)
        now_target = datetime.now(target_tz)

        if alert.period == "daily":
            daily_times = get_alert_daily_times(alert)
            if not daily_times:
                raise ValueError("At least one daily time is required")

            if time_slot:
                matching_time = None
                for time_str in daily_times:
                    if _time_slot_key(time_str) == time_slot:
                        matching_time = time_str
                        break
                if not matching_time:
                    raise ValueError(f"Unknown time slot {time_slot} for alert {alert.id}")

                _cancel_rq_jobs(scheduler, [_rq_job_id_for_alert(alert.id, time_slot)])
                new_job_id = _schedule_daily_time_slot(
                    scheduler, alert, matching_time, frequency, target_tz, now_target
                )

                job_ids = list(alert.rq_job_ids or [])
                if alert.rq_job_id and alert.rq_job_id not in job_ids:
                    job_ids.append(alert.rq_job_id)
                job_ids = [jid for jid in job_ids if jid != _rq_job_id_for_alert(alert.id, time_slot)]
                job_ids.append(new_job_id)

                alert.rq_job_ids = job_ids
                alert.rq_job_id = job_ids[0] if job_ids else None
                db.commit()
                return new_job_id

            unschedule_rq_job(db, alert, commit=False)

            scheduled_job_ids = []
            for time_str in daily_times:
                job_id = _schedule_daily_time_slot(
                    scheduler, alert, time_str, frequency, target_tz, now_target
                )
                scheduled_job_ids.append(job_id)

            alert.rq_job_ids = scheduled_job_ids
            alert.rq_job_id = scheduled_job_ids[0] if scheduled_job_ids else None
            db.commit()
            logger.info(
                f"Successfully scheduled {len(scheduled_job_ids)} daily job(s) for alert {alert.id}"
            )
            return scheduled_job_ids[0] if scheduled_job_ids else None

        if time_slot:
            raise ValueError("time_slot rescheduling is only supported for daily period")

        unschedule_rq_job(db, alert, commit=False)

        next_run_target = None
        interval_seconds = None

        if alert.period == "minute":
            next_run_target = now_target + timedelta(minutes=1)
            interval_seconds = frequency * 60

        elif alert.period == "weekly":
            if alert.day_of_week is None:
                raise ValueError("day_of_week is required for weekly period")
            if not alert.time:
                raise ValueError("time is required for weekly period")

            time_parts = str(alert.time).split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0

            days_ahead = alert.day_of_week - now_target.weekday()
            if days_ahead <= 0:
                days_ahead += 7 * frequency
            elif days_ahead == 0 and now_target.hour >= hour and (
                now_target.hour > hour or now_target.minute >= minute
            ):
                days_ahead = 7 * frequency

            next_run_target = now_target.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            ) + timedelta(days=days_ahead)
            interval_seconds = frequency * 604800

        elif alert.period == "monthly":
            if alert.day_of_month is None:
                raise ValueError("day_of_month is required for monthly period")
            if not alert.time:
                raise ValueError("time is required for monthly period")

            time_parts = str(alert.time).split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0

            day = alert.day_of_month
            next_run_target = now_target.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)

            if next_run_target <= now_target:
                months_to_add = frequency
                if next_run_target.month + months_to_add > 12:
                    next_run_target = next_run_target.replace(
                        year=next_run_target.year + 1,
                        month=(next_run_target.month + months_to_add - 12),
                    )
                else:
                    next_run_target = next_run_target.replace(
                        month=next_run_target.month + months_to_add
                    )

            while True:
                try:
                    test_date = next_run_target.replace(day=day)
                    next_run_target = test_date
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
            raise ValueError(f"Unknown period: {alert.period}")

        next_run_utc_naive = next_run_target.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        rq_job_id = _rq_job_id_for_alert(alert.id)

        if alert.period == "minute":
            logger.info(f"Scheduling alert {alert.id} ({alert.name}): every {frequency} minute(s)")
        else:
            time_parts = str(alert.time).split(":") if alert.time else ["0", "0"]
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            logger.info(
                f"Scheduling alert {alert.id} ({alert.name}): every {frequency} {alert.period}(s) "
                f"at {hour:02d}:{minute:02d} {alert.timezone}"
            )
        logger.info(f"  Next run: {next_run_target} ({alert.timezone}) = {next_run_utc_naive} (UTC)")

        scheduler.schedule(
            scheduled_time=next_run_utc_naive,
            func=create_scheduled_alert_job,
            args=(alert.id,),
            interval=interval_seconds,
            repeat=1,
            id=rq_job_id,
            queue_name=settings.rq_default_queue,
        )

        alert.rq_job_id = rq_job_id
        alert.rq_job_ids = [rq_job_id]
        db.commit()

        logger.info(f"Successfully scheduled RQ job {rq_job_id} for low stock alert {alert.id}")
        return rq_job_id

    except Exception as e:
        logger.error(f"Error scheduling RQ job for low stock alert {alert.id}: {str(e)}", exc_info=True)
        return None


def unschedule_rq_job(db: Session, alert: LowStockAlert, commit: bool = True):
    """Cancel all RQ jobs for a LowStockAlert configuration."""
    job_ids = get_alert_rq_job_ids(alert)
    if not job_ids:
        return True

    try:
        conn = get_redis_connection()
        scheduler = Scheduler(connection=conn)

        _cancel_rq_jobs(scheduler, job_ids)

        alert.rq_job_id = None
        alert.rq_job_ids = []
        if commit:
            db.commit()
        return True
    except Exception as e:
        logger.error(f"Error cancelling RQ jobs for low stock alert {alert.id}: {str(e)}", exc_info=True)
        return False
