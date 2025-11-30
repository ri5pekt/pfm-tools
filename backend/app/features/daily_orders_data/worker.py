import os
import logging
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from ...core.config import get_settings
from ...core.db import SessionLocal
from ...jobs.models import Job
from .service import fetch_daily_orders_data, save_daily_orders_to_csv, export_stats_to_google_sheets

settings = get_settings()
logger = logging.getLogger(__name__)


def ensure_dirs():
    os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(settings.processed_dir, exist_ok=True)


def run_daily_orders_export_job(job_id: int):
    """
    Worker function to process Daily Orders Data export job.
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
        date = options.get("date")
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

        if not date:
            job.status = "error"
            job.error_message = "Date is required"
            db.commit()
            return

        logger.info(f"Starting Daily Orders export job {job_id}")
        logger.info(f"Date: {date}")
        logger.info(f"Manual run: {is_manual}")

        # Progress update callback function
        def update_progress(progress, message):
            try:
                new_options = dict(job.options or {})
                new_options['progress'] = progress
                new_options['status_message'] = message
                job.options = new_options
                db.commit()
                db.refresh(job)
            except Exception as e:
                logger.warning(f"Could not update progress: {e}")

        # Update progress
        update_progress(5, 'Fetching orders and refunds from WooCommerce...')

        # Fetch orders and refunds from WooCommerce using dedicated endpoint
        try:
            data = fetch_daily_orders_data(
                date=date,
                woo_base_url=woo_base_url,
                woo_consumer_key=woo_consumer_key,
                woo_consumer_secret=woo_consumer_secret,
                per_page=300,  # Use 300 per page for efficiency (matches export-stats plugin)
                update_progress=update_progress
            )
            orders_count = len(data.get('orders', []))
            refunds_count = len(data.get('refunds', []))
            logger.info(f"Successfully fetched {orders_count} orders and {refunds_count} refunds from WooCommerce")
            if refunds_count == 0:
                logger.info("No refunds found for the date range (this is normal if there are no refunds)")
        except Exception as e:
            logger.error(f"Error fetching daily orders data: {str(e)}", exc_info=True)
            job.status = "error"
            job.error_message = f"Failed to fetch data: {str(e)}"
            db.commit()
            return

        # Check if file export is enabled
        export_to_file = options.get("export_to_file", True)
        export_to_google_sheets = options.get("export_to_google_sheets", True)  # Default to True to match schema

        # Save to CSV if enabled
        output_path = None
        if export_to_file:
            output_path = os.path.join(
                settings.processed_dir,
                f"daily_orders_export_{job.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
            )

            try:
                save_daily_orders_to_csv(
                    data,
                    output_path,
                    selected_date=date,
                    update_progress=update_progress
                )
                logger.info(f"CSV file saved: {output_path}")
            except Exception as e:
                logger.error(f"Error saving CSV file: {str(e)}", exc_info=True)
                job.status = "error"
                job.error_message = f"Failed to save CSV: {str(e)}"
                db.commit()
                return

        # Export to Google Sheets if enabled
        if export_to_google_sheets:
            update_progress(90, 'Exporting stats to Google Sheets...')
            try:
                # Extract base date from date string (YYYY-MM-DD format)
                base_date = date.split('T')[0] if 'T' in date else date.split(' ')[0]

                # Get spreadsheet ID from settings (with fallback to general setting)
                daily_orders_id = getattr(settings, 'daily_orders_google_sheets_spreadsheet_id', None)
                general_id = getattr(settings, 'google_sheets_spreadsheet_id', None)
                spreadsheet_id = daily_orders_id or general_id

                if not spreadsheet_id:
                    logger.warning("Google Sheets spreadsheet ID not configured, skipping Google Sheets export")
                else:
                    success = export_stats_to_google_sheets(
                        orders_data=data,
                        base_date=base_date,
                        spreadsheet_id=spreadsheet_id,
                        oauth_credentials_path=settings.google_sheets_oauth_credentials_path,
                        oauth_token_path=settings.google_sheets_oauth_token_path,
                        service_account_path=settings.google_sheets_service_account_path,
                    )

                    if success:
                        logger.info("Successfully exported stats to Google Sheets")
                    else:
                        logger.warning("Google Sheets export failed, but continuing with job completion")
                        # Don't fail the job if Google Sheets export fails, just log it
            except Exception as e:
                logger.error(f"Error exporting to Google Sheets: {str(e)}", exc_info=True)
                # Don't fail the job if Google Sheets export fails, just log it
        else:
            logger.info("Google Sheets export is disabled (export_to_google_sheets=False)")

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
        logger.error(f"Error processing Daily Orders export job {job_id}: {str(e)}")
        logger.error(error_trace)
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "error"
            job.error_message = f"{str(e)}\n\nTraceback:\n{error_trace}"
            db.commit()
    finally:
        db.close()

