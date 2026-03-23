import os
import logging
from datetime import datetime

from ...core.config import get_settings
from ...core.db import SessionLocal
from ...jobs.models import Job
from .service import fetch_yt_influencers_orders, save_yt_influencers_to_csv, export_to_google_sheets

settings = get_settings()
logger = logging.getLogger(__name__)


def ensure_dirs():
    os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(settings.processed_dir, exist_ok=True)


def run_yt_influencers_export_job(job_id: int):
    """
    Worker function to process a YT Influencers export job.

    Steps:
      1. Fetch orders from WooCommerce (/pfm-tools/v1/yt-influencers-orders)
      2. Optionally save raw orders to CSV
      3. Classify into Segment 1/2/3 using the Creators tab, aggregate, write to Google Sheets
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
        date = options.get("date")
        is_manual = options.get("is_manual", True)

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

        logger.info(f"[yt_influencers] Starting job {job_id} | date={date} | manual={is_manual}")

        def update_progress(progress, message):
            try:
                new_options = dict(job.options or {})
                new_options["progress"] = progress
                new_options["status_message"] = message
                job.options = new_options
                db.commit()
                db.refresh(job)
            except Exception as exc:
                logger.warning(f"Could not update progress: {exc}")

        # --- Step 1: Fetch orders from WooCommerce ---
        update_progress(5, "Fetching YT Influencer orders from WooCommerce…")

        try:
            data = fetch_yt_influencers_orders(
                date=date,
                woo_base_url=woo_base_url,
                woo_consumer_key=woo_consumer_key,
                woo_consumer_secret=woo_consumer_secret,
                update_progress=update_progress,
            )
            orders_count = len(data.get("orders", []))
            logger.info(f"[yt_influencers] Fetched {orders_count} order(s)")
        except Exception as exc:
            logger.error(f"Error fetching YT Influencer orders: {exc}", exc_info=True)
            job.status = "error"
            job.error_message = f"Failed to fetch orders: {str(exc)}"
            db.commit()
            return

        export_to_file = options.get("export_to_file", True)
        export_to_google_sheets_flag = options.get("export_to_google_sheets", True)

        # --- Step 2: Save raw orders to CSV (optional) ---
        output_path = None
        if export_to_file:
            output_path = os.path.join(
                settings.processed_dir,
                f"yt_influencers_export_{job.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
            )
            try:
                save_yt_influencers_to_csv(
                    data,
                    output_path,
                    selected_date=date,
                    update_progress=update_progress,
                )
            except Exception as exc:
                logger.error(f"Error saving CSV: {exc}", exc_info=True)
                job.status = "error"
                job.error_message = f"Failed to save CSV: {str(exc)}"
                db.commit()
                return

        # --- Step 3: Classify + aggregate + write to Google Sheets ---
        if export_to_google_sheets_flag:
            update_progress(75, "Exporting to Google Sheets…")
            try:
                base_date = date.split("T")[0] if "T" in date else date.split(" ")[0]

                spreadsheet_id = (
                    getattr(settings, "yt_influencers_google_sheets_spreadsheet_id", None)
                    or getattr(settings, "google_sheets_spreadsheet_id", None)
                )

                if not spreadsheet_id:
                    logger.warning("[yt_influencers] No spreadsheet ID configured, skipping Sheets export")
                else:
                    success = export_to_google_sheets(
                        data=data,
                        base_date=base_date,
                        spreadsheet_id=spreadsheet_id,
                        oauth_credentials_path=settings.google_sheets_oauth_credentials_path,
                        oauth_token_path=settings.google_sheets_oauth_token_path,
                        service_account_path=settings.google_sheets_service_account_path,
                        update_progress=update_progress,
                    )
                    if success:
                        logger.info("[yt_influencers] Google Sheets export successful")
                    else:
                        logger.warning("[yt_influencers] Google Sheets export failed (non-fatal)")
            except Exception as exc:
                logger.error(f"Error exporting to Google Sheets: {exc}", exc_info=True)
        else:
            logger.info("[yt_influencers] Google Sheets export disabled")

        update_progress(100, "Export completed")

        job.status = "done"
        if output_path:
            job.output_filename = output_path
        db.commit()
        logger.info(f"[yt_influencers] Job {job_id} completed successfully")

    except Exception as exc:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"[yt_influencers] Job {job_id} failed: {exc}")
        logger.error(error_trace)
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "error"
            job.error_message = f"{str(exc)}\n\nTraceback:\n{error_trace}"
            db.commit()
    finally:
        db.close()
