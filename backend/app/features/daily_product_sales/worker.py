import os
import logging
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from ...core.config import get_settings
from ...core.db import SessionLocal
from ...jobs.models import Job
from .service import (
    fetch_daily_product_sales_data,
    save_daily_product_sales_to_csv,
    export_product_sales_to_google_sheets,
    fetch_single_day_product_sales,
    export_single_day_to_google_sheets
)

settings = get_settings()
logger = logging.getLogger(__name__)


def ensure_dirs():
    os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(settings.processed_dir, exist_ok=True)


def run_daily_product_sales_export_job(job_id: int):
    """
    Worker function to process Daily Product Sales export job.
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

        # Double-check job still exists
        if not db.query(Job).filter(Job.id == job_id).first():
            logger.warning(f"Job {job_id} was deleted, stopping")
            return

        # Get options from job
        options = job.options or {}
        date_from = options.get("date_from")
        date_to = options.get("date_to")
        is_manual = options.get("is_manual", True)

        # Get WooCommerce credentials
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

        logger.info(f"Starting Daily Product Sales export job {job_id}")
        logger.info(f"Date range: {date_from} to {date_to}")
        logger.info(f"Manual run: {is_manual}")

        # Progress update callback function
        def update_progress(progress, message):
            try:
                # Check if job still exists before updating
                job_check = db.query(Job).filter(Job.id == job_id).first()
                if not job_check:
                    logger.info(f"Job {job_id} was deleted, cannot update progress")
                    # Raise an exception to signal cancellation
                    raise ValueError("Job was deleted")

                # Try to refresh the job object
                try:
                    db.refresh(job)
                except Exception:
                    # If refresh fails, job might be deleted - re-check
                    job_check = db.query(Job).filter(Job.id == job_id).first()
                    if not job_check:
                        logger.info(f"Job {job_id} was deleted (refresh failed), cannot update progress")
                        raise ValueError("Job was deleted")

                if job.status != "running":
                    logger.info(f"Job {job_id} status is '{job.status}', cannot update progress")
                    raise ValueError(f"Job status is {job.status}")

                new_options = dict(job.options or {})
                new_options['progress'] = progress
                new_options['status_message'] = message
                job.options = new_options
                db.commit()
                db.refresh(job)
            except ValueError as e:
                # Job was deleted or cancelled - re-raise to signal cancellation
                raise
            except Exception as e:
                logger.warning(f"Could not update progress: {e}")
                # If it's a database error indicating job was deleted, raise to signal cancellation
                if "0 were matched" in str(e) or "does not exist" in str(e).lower():
                    logger.info(f"Job {job_id} appears to have been deleted (database error), stopping")
                    raise ValueError("Job was deleted")

        # Check if file export is enabled
        export_to_file = options.get("export_to_file", True)
        export_to_google_sheets = options.get("export_to_google_sheets", True)

        # Parse date range to get list of days
        from zoneinfo import ZoneInfo
        metorik_tz = ZoneInfo('America/New_York')
        date_from_dt_utc = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        date_to_dt_utc = datetime.fromisoformat(date_to.replace('Z', '+00:00'))

        # Convert to NY timezone first, then extract date components
        # This ensures we get the correct calendar day in NY timezone
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

        # Generate list of dates to process
        dates_to_process = []
        current_date = date_from_dt
        while current_date <= date_to_dt:
            dates_to_process.append(current_date.strftime('%Y-%m-%d'))
            current_date = current_date + timedelta(days=1)

        total_days = len(dates_to_process)
        logger.info(f"Processing {total_days} days: {dates_to_process[0]} to {dates_to_process[-1]}")

        # Get spreadsheet ID if Google Sheets export is enabled
        spreadsheet_id = None
        if export_to_google_sheets:
            daily_product_sales_id = getattr(settings, 'daily_product_sales_google_sheets_spreadsheet_id', None)
            general_id = getattr(settings, 'google_sheets_spreadsheet_id', None)
            spreadsheet_id = daily_product_sales_id or general_id

            logger.info(f"Daily Product Sales Google Sheets spreadsheet ID: {daily_product_sales_id}")
            logger.info(f"General Google Sheets spreadsheet ID: {general_id}")
            logger.info(f"Using spreadsheet ID: {spreadsheet_id}")

            if not spreadsheet_id:
                logger.warning("Google Sheets spreadsheet ID not configured, skipping Google Sheets export")
                logger.warning("Please set DAILY_PRODUCT_SALES_GOOGLE_SHEETS_SPREADSHEET_ID in .env file")
                export_to_google_sheets = False

        # Initialize Google Sheets client/worksheet for reuse across days
        gs_client = None
        gs_worksheet = None

        # Accumulate all data for CSV export at the end
        all_data_by_date = {}

        # Helper function to check if job was cancelled/deleted
        def check_job_cancelled():
            try:
                # First check if job exists in database
                job_check = db.query(Job).filter(Job.id == job_id).first()
                if not job_check:
                    logger.info(f"Job {job_id} was deleted from database, stopping processing")
                    return True

                # Try to refresh the job object
                try:
                    db.refresh(job)
                    if job.status != "running":
                        logger.info(f"Job {job_id} status changed to '{job.status}', stopping processing")
                        return True
                except Exception as refresh_error:
                    # If refresh fails, the job might have been deleted
                    logger.warning(f"Could not refresh job {job_id}: {refresh_error}")
                    # Re-query to be sure
                    job_check = db.query(Job).filter(Job.id == job_id).first()
                    if not job_check:
                        logger.info(f"Job {job_id} was deleted (confirmed on re-query), stopping processing")
                        return True

                return False
            except Exception as e:
                # If any error occurs, check one more time if job exists
                logger.warning(f"Error checking job status: {e}")
                try:
                    job_check = db.query(Job).filter(Job.id == job_id).first()
                    if not job_check:
                        logger.info(f"Job {job_id} was deleted (error during check), stopping processing")
                        return True
                except:
                    pass
                return False

        # Process each day: fetch -> export to Google Sheets -> accumulate for CSV
        for day_num, date_str in enumerate(dates_to_process, 1):
            # Check if job was deleted or cancelled before processing each day
            if check_job_cancelled():
                return

            try:
                # Check if job was deleted or cancelled before processing each day
                if check_job_cancelled():
                    logger.info(f"Job {job_id} was cancelled/deleted, stopping before processing {date_str}")
                    return

                # Calculate progress (0-90% for fetching/exporting days, 90-100% for CSV)
                try:
                    progress = int((day_num / total_days) * 90)
                    update_progress(progress, f'Processing {date_str} ({day_num}/{total_days})...')
                except ValueError:
                    # Job was deleted - stop processing
                    logger.info(f"Job {job_id} was deleted during progress update, stopping")
                    return

                logger.info(f"Processing day {day_num}/{total_days}: {date_str}")

                # Fetch data for this day
                try:
                    update_progress(progress, f'Fetching data for {date_str} ({day_num}/{total_days})...')
                except ValueError:
                    logger.info(f"Job {job_id} was deleted, stopping before fetching {date_str}")
                    return

                day_data = fetch_single_day_product_sales(
                    date_str=date_str,
                    woo_base_url=woo_base_url,
                    woo_consumer_key=woo_consumer_key,
                    woo_consumer_secret=woo_consumer_secret,
                    per_page=300
                )

                # Check if job was deleted after fetching
                if check_job_cancelled():
                    logger.info(f"Job {job_id} was cancelled/deleted after fetching {date_str}, stopping")
                    return

                # Store for CSV export
                all_data_by_date[date_str] = day_data

                # (debug logging removed)

                # Export to Google Sheets immediately if enabled
                if export_to_google_sheets and spreadsheet_id:
                    # Check again before exporting
                    if check_job_cancelled():
                        logger.info(f"Job {job_id} was cancelled/deleted before exporting {date_str}, stopping")
                        return
                    try:
                        update_progress(progress + 2, f'Exporting {date_str} to Google Sheets ({day_num}/{total_days})...')
                    except ValueError:
                        logger.info(f"Job {job_id} was deleted, stopping before exporting {date_str}")
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
                        update_progress=update_progress
                    )

                    if gs_client is None:
                        logger.error(f"Failed to export {date_str} to Google Sheets, but continuing...")
                        export_to_google_sheets = False  # Disable for remaining days
                    else:
                        logger.info(f"Successfully exported {date_str} to Google Sheets")

            except ValueError as e:
                # Job was deleted - stop processing
                if "Job was deleted" in str(e) or "Job status is" in str(e):
                    logger.info(f"Job {job_id} was deleted/cancelled: {e}, stopping processing")
                    return
                raise
            except Exception as e:
                logger.error(f"Error processing day {date_str}: {str(e)}", exc_info=True)
                # Continue with next day even if this one fails (unless it's a cancellation)
                if check_job_cancelled():
                    return
                continue

        # Save to CSV if enabled (after all days are processed)
        output_path = None
        if export_to_file:
            update_progress(90, 'Saving all data to CSV file...')
            output_path = os.path.join(
                settings.processed_dir,
                f"daily_product_sales_export_{job.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
            )

            try:
                # Format data for CSV export function
                csv_data = {
                    'product_sales': all_data_by_date,
                    'date_from': date_from,
                    'date_to': date_to,
                    'total_days': total_days
                }

                save_daily_product_sales_to_csv(
                    csv_data,
                    output_path,
                    update_progress=update_progress
                )
                logger.info(f"CSV file saved: {output_path}")
            except Exception as e:
                logger.error(f"Error saving CSV file: {str(e)}", exc_info=True)
                job.status = "error"
                job.error_message = f"Failed to save CSV: {str(e)}"
                db.commit()
                return

        # Update progress to 100%
        update_progress(100, 'Export completed')

        job.status = "done"
        if output_path:
            job.output_filename = output_path
        db.commit()
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error processing Daily Product Sales export job {job_id}: {str(e)}")
        logger.error(error_trace)
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "error"
            job.error_message = f"{str(e)}\n\nTraceback:\n{error_trace}"
            db.commit()
    finally:
        db.close()

