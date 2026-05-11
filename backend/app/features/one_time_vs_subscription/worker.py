import os
import logging
from datetime import datetime, timedelta

from ...core.config import get_settings
from ...core.db import SessionLocal
from ...jobs.models import Job
from .service import (
    fetch_single_day_data,
    save_to_csv,
    export_single_day_to_google_sheets,
)

settings = get_settings()
logger = logging.getLogger(__name__)


def ensure_dirs():
    os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(settings.processed_dir, exist_ok=True)


def run_one_time_vs_subscription_export_job(job_id: int):
    """
    Worker function to process One-Time vs Subscription export job.
    """
    ensure_dirs()
    db = SessionLocal()
    try:
        job: Job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.warning(f"Job {job_id} not found, skipping")
            return

        job.status = "running"
        db.commit()
        db.refresh(job)

        if not db.query(Job).filter(Job.id == job_id).first():
            logger.warning(f"Job {job_id} was deleted, stopping")
            return

        options = job.options or {}
        date_from = options.get("date_from")
        date_to = options.get("date_to")
        is_manual = options.get("is_manual", True)

        woo_base_url = settings.woo_base_url
        woo_consumer_key = settings.woo_consumer_key
        woo_consumer_secret = settings.woo_consumer_secret

        if not woo_base_url or not woo_consumer_key or not woo_consumer_secret:
            job.status = "error"
            job.error_message = "WooCommerce credentials not configured"
            db.commit()
            return

        if not date_from or not date_to:
            job.status = "error"
            job.error_message = "Date range is required (date_from and date_to)"
            db.commit()
            return

        logger.info(f"Starting One-Time vs Subscription export job {job_id}")
        logger.info(f"Date range: {date_from} to {date_to}, manual: {is_manual}")

        def update_progress(progress, message):
            try:
                job_check = db.query(Job).filter(Job.id == job_id).first()
                if not job_check:
                    raise ValueError("Job was deleted")
                try:
                    db.refresh(job)
                except Exception:
                    job_check = db.query(Job).filter(Job.id == job_id).first()
                    if not job_check:
                        raise ValueError("Job was deleted")

                if job.status != "running":
                    raise ValueError(f"Job status is {job.status}")

                new_options = dict(job.options or {})
                new_options['progress'] = progress
                new_options['status_message'] = message
                job.options = new_options
                db.commit()
                db.refresh(job)
            except ValueError:
                raise
            except Exception as e:
                logger.warning(f"Could not update progress: {e}")
                if "0 were matched" in str(e) or "does not exist" in str(e).lower():
                    raise ValueError("Job was deleted")

        export_to_file = options.get("export_to_file", True)
        export_to_google_sheets_flag = options.get("export_to_google_sheets", True)

        from zoneinfo import ZoneInfo
        metorik_tz = ZoneInfo('America/New_York')

        date_from_display = options.get("date_from_display")
        date_to_display = options.get("date_to_display")

        if date_from_display and date_to_display:
            date_from_dt = datetime.strptime(date_from_display, '%Y-%m-%d').replace(tzinfo=metorik_tz)
            date_to_dt = datetime.strptime(date_to_display, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59, tzinfo=metorik_tz
            )
        else:
            date_from_dt_utc = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            date_to_dt_utc = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            date_from_dt_ny = date_from_dt_utc.astimezone(metorik_tz)
            date_to_dt_ny = date_to_dt_utc.astimezone(metorik_tz)
            date_from_dt = datetime(
                date_from_dt_ny.year, date_from_dt_ny.month, date_from_dt_ny.day,
                0, 0, 0, tzinfo=metorik_tz
            )
            date_to_dt = datetime(
                date_to_dt_ny.year, date_to_dt_ny.month, date_to_dt_ny.day,
                23, 59, 59, tzinfo=metorik_tz
            )

        dates_to_process = []
        current_date = date_from_dt
        while current_date <= date_to_dt:
            dates_to_process.append(current_date.strftime('%Y-%m-%d'))
            current_date = current_date + timedelta(days=1)

        total_days = len(dates_to_process)
        logger.info(f"Processing {total_days} days: {dates_to_process[0]} to {dates_to_process[-1]}")

        spreadsheet_id = None
        if export_to_google_sheets_flag:
            spreadsheet_id = getattr(settings, 'one_time_vs_subscription_google_sheets_spreadsheet_id', None)
            if not spreadsheet_id:
                logger.warning("One-Time vs Subscription Google Sheets spreadsheet ID not configured, skipping Sheets export")
                export_to_google_sheets_flag = False

        gs_client = None
        gs_worksheet = None
        all_data_by_date = {}

        def check_job_cancelled():
            try:
                job_check = db.query(Job).filter(Job.id == job_id).first()
                if not job_check:
                    return True
                try:
                    db.refresh(job)
                    if job.status != "running":
                        return True
                except Exception as refresh_error:
                    logger.warning(f"Could not refresh job {job_id}: {refresh_error}")
                    job_check = db.query(Job).filter(Job.id == job_id).first()
                    if not job_check:
                        return True
                return False
            except Exception as e:
                logger.warning(f"Error checking job status: {e}")
                return False

        for day_num, date_str in enumerate(dates_to_process, 1):
            if check_job_cancelled():
                return

            try:
                if check_job_cancelled():
                    return

                progress = int((day_num / total_days) * 90)
                try:
                    update_progress(progress, f'Fetching data for {date_str} ({day_num}/{total_days})...')
                except ValueError:
                    return

                logger.info(f"Processing day {day_num}/{total_days}: {date_str}")

                day_data = fetch_single_day_data(
                    date_str=date_str,
                    woo_base_url=woo_base_url,
                    woo_consumer_key=woo_consumer_key,
                    woo_consumer_secret=woo_consumer_secret,
                    per_page=300,
                )

                if check_job_cancelled():
                    return

                all_data_by_date[date_str] = day_data

                if export_to_google_sheets_flag and spreadsheet_id:
                    if check_job_cancelled():
                        return
                    try:
                        update_progress(progress + 2, f'Exporting {date_str} to Google Sheets ({day_num}/{total_days})...')
                    except ValueError:
                        return

                    gs_client, gs_worksheet = export_single_day_to_google_sheets(
                        date_str=date_str,
                        day_data=day_data,
                        spreadsheet_id=spreadsheet_id,
                        client=gs_client,
                        worksheet=gs_worksheet,
                        oauth_credentials_path=settings.google_sheets_oauth_credentials_path,
                        oauth_token_path=settings.google_sheets_oauth_token_path,
                        service_account_path=settings.google_sheets_service_account_path,
                        update_progress=update_progress,
                    )

                    if gs_client is None:
                        logger.error(f"Failed to export {date_str} to Google Sheets, disabling for remaining days")
                        export_to_google_sheets_flag = False
                    else:
                        logger.info(f"Successfully exported {date_str} to Google Sheets")

            except ValueError as e:
                if "Job was deleted" in str(e) or "Job status is" in str(e):
                    return
                raise
            except Exception as e:
                logger.error(f"Error processing day {date_str}: {e}", exc_info=True)
                if check_job_cancelled():
                    return
                continue

        output_path = None
        if export_to_file:
            try:
                update_progress(90, 'Saving all data to CSV file...')
            except ValueError:
                return

            output_path = os.path.join(
                settings.processed_dir,
                f"one_time_vs_subscription_export_{job.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
            )

            try:
                csv_data = {
                    'daily_data': all_data_by_date,
                    'date_from': date_from,
                    'date_to': date_to,
                    'total_days': total_days,
                }
                save_to_csv(csv_data, output_path, update_progress=update_progress)
                logger.info(f"CSV file saved: {output_path}")
            except Exception as e:
                logger.error(f"Error saving CSV file: {e}", exc_info=True)
                job.status = "error"
                job.error_message = f"Failed to save CSV: {e}"
                db.commit()
                return

        update_progress(100, 'Export completed')
        job.status = "done"
        if output_path:
            job.output_filename = output_path
        db.commit()
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error processing One-Time vs Subscription export job {job_id}: {e}")
        logger.error(error_trace)
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "error"
            job.error_message = f"{e}\n\nTraceback:\n{error_trace}"
            db.commit()
    finally:
        db.close()
