import os
import logging
from sqlalchemy.orm import Session
from datetime import datetime

from ...core.config import get_settings
from ...core.db import SessionLocal
from ...jobs.models import Job
from .service import fetch_ulta_orders, export_to_google_sheets

settings = get_settings()
logger = logging.getLogger(__name__)


def ensure_dirs():
    os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(settings.processed_dir, exist_ok=True)


def run_ulta_export_job(job_id: int):
    """
    Worker function to process Ulta Marketplace export job.
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
        start_date = options.get("start_date")
        end_date = options.get("end_date")
        is_manual = options.get("is_manual", True)
        api_key = options.get("ulta_api_key")

        if not api_key:
            job.status = "error"
            job.error_message = "Ulta API key not provided"
            db.commit()
            return

        if not start_date or not end_date:
            job.status = "error"
            job.error_message = "Start date and end date are required"
            db.commit()
            return

        logger.info(f"Starting Ulta export job {job_id}")
        logger.info(f"Date range: {start_date} to {end_date}")
        logger.info(f"Manual run: {is_manual}")

        # Update progress
        new_options = dict(options)
        new_options['progress'] = 10
        new_options['status_message'] = 'Fetching orders from Ulta API...'
        job.options = new_options
        db.commit()
        db.refresh(job)

        # Fetch orders from Ulta API
        try:
            orders_data = fetch_ulta_orders(
                start_date=start_date,
                end_date=end_date,
                api_key=api_key
            )
            logger.info("Successfully fetched orders from Ulta API")
        except Exception as e:
            logger.error(f"Error fetching Ulta orders: {str(e)}", exc_info=True)
            job.status = "error"
            job.error_message = f"Failed to fetch orders: {str(e)}"
            db.commit()
            return

        # Check if file export is enabled
        export_to_file = options.get("export_to_file", True)  # Default to True for backward compatibility

        # Update progress based on export options
        new_options = dict(options)
        if export_to_file:
            new_options['progress'] = 50
            new_options['status_message'] = 'Processing orders...'
        else:
            new_options['progress'] = 60
            new_options['status_message'] = 'Processing orders...'
        job.options = new_options
        db.commit()
        db.refresh(job)

        output_path = None
        if export_to_file:
            # Save to CSV
            output_path = os.path.join(
                settings.processed_dir,
                f"ulta_export_{job.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
            )

            from .service import save_ulta_orders_to_csv
            try:
                save_ulta_orders_to_csv(orders_data, output_path, start_date=start_date, end_date=end_date)
                logger.info(f"CSV file saved: {output_path}")
            except Exception as e:
                logger.error(f"Error saving CSV file: {str(e)}", exc_info=True)
                job.status = "error"
                job.error_message = f"Failed to save CSV: {str(e)}"
                db.commit()
                return
        else:
            logger.info("File export is disabled, skipping CSV creation")

        # Export to Google Sheets if enabled and configured
        export_to_google_sheets_flag = options.get("export_to_google_sheets", True)  # Default to True for backward compatibility

        # Support both GOOGLE_SHEETS_* and ULTA_GOOGLE_SHEETS_* naming
        # Check ULTA_ prefix first since it's more specific, then fall back to generic
        spreadsheet_id = settings.ulta_google_sheets_spreadsheet_id or settings.google_sheets_spreadsheet_id
        sheet_name = settings.ulta_google_sheets_sheet_name or settings.google_sheets_sheet_name or "Ulta Exports"

        logger.info(f"Google Sheets export check:")
        logger.info(f"  Export to Google Sheets flag: {export_to_google_sheets_flag}")
        logger.info(f"  Spreadsheet ID: {spreadsheet_id}")
        logger.info(f"  Sheet name: {sheet_name}")
        logger.info(f"  OAuth credentials path: {settings.google_sheets_oauth_credentials_path}")
        logger.info(f"  OAuth token path: {settings.google_sheets_oauth_token_path}")
        logger.info(f"  Service account path: {settings.google_sheets_service_account_path}")

        # Check for either OAuth or Service Account credentials
        google_sheets_enabled = (
            export_to_google_sheets_flag and
            spreadsheet_id and
            (
                (settings.google_sheets_oauth_credentials_path and settings.google_sheets_oauth_token_path) or
                settings.google_sheets_service_account_path
            )
        )

        if google_sheets_enabled:
            logger.info("Google Sheets export is ENABLED, proceeding with export...")
            # Update progress
            new_options = dict(options)
            new_options['progress'] = 75
            new_options['status_message'] = 'Exporting to Google Sheets...'
            job.options = new_options
            db.commit()
            db.refresh(job)

            try:
                success = export_to_google_sheets(
                    orders_data=orders_data,
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=sheet_name,
                    oauth_credentials_path=settings.google_sheets_oauth_credentials_path,
                    oauth_token_path=settings.google_sheets_oauth_token_path,
                    service_account_path=settings.google_sheets_service_account_path,
                    start_date=start_date,
                    end_date=end_date
                )
                if success:
                    logger.info(f"Successfully exported to Google Sheets: {spreadsheet_id}/{sheet_name}")
                else:
                    logger.warning(f"Google Sheets export failed, but continuing with job completion")
                    # Don't fail the job if Google Sheets export fails, just log it
            except Exception as e:
                logger.error(f"Error exporting to Google Sheets: {str(e)}", exc_info=True)
                # Don't fail the job if Google Sheets export fails, just log it
                # CSV export is the primary output
        else:
            logger.info("Google Sheets export is DISABLED (missing configuration)")
            if not spreadsheet_id:
                logger.info("  Reason: No spreadsheet ID configured")
            if not settings.google_sheets_oauth_credentials_path and not settings.google_sheets_service_account_path:
                logger.info("  Reason: No authentication credentials configured")
            if settings.google_sheets_oauth_credentials_path and not settings.google_sheets_oauth_token_path:
                logger.info("  Reason: OAuth credentials found but token path not configured")

        # Update progress to 100%
        new_options = dict(options)
        new_options['progress'] = 100
        new_options['status_message'] = 'Export completed'
        job.options = new_options

        job.status = "done"
        if output_path:
            job.output_filename = output_path
        db.commit()
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error processing Ulta export job {job_id}: {str(e)}")
        logger.error(error_trace)
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "error"
            job.error_message = f"{str(e)}\n\nTraceback:\n{error_trace}"
            db.commit()
    finally:
        db.close()

