import logging
from datetime import datetime

from ...core.config import get_settings
from ...core.db import SessionLocal
from ...jobs.models import Job
from .service import (
    fetch_zenventory_klb_inventory,
    fetch_shipbob_total_inventory,
    check_low_stock,
    build_low_stock_slack_message,
)
from .slack_client import send_slack_webhook

logger = logging.getLogger(__name__)
settings = get_settings()


def run_low_stock_alert_job(job_id: int):
    """
    Worker function to process a low stock alert check job.
    """
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        options = job.options or {}
        job.status = "running"
        options["progress"] = 10
        options["status_message"] = "Fetching inventory from KLB..."
        job.options = options
        db.commit()
        db.refresh(job)

        zenventory_username = options.get("zenventory_username")
        zenventory_password = options.get("zenventory_password")
        zenventory_base_url = options.get("zenventory_base_url")
        shipbob_api_key = options.get("shipbob_api_key")
        shipbob_base_url = options.get("shipbob_base_url")
        threshold = options.get("threshold", 0)
        klb_threshold = options.get("klb_threshold", threshold)
        shipbob_threshold = options.get("shipbob_threshold", threshold)
        slack_webhook_url = options.get("slack_webhook_url")
        excluded_skus = options.get("excluded_skus") or []
        alert_name = options.get("alert_name", "Low Stock Alert")

        logger.info(f"Starting low stock alert job {job_id} for '{alert_name}'")

        klb_inventory = fetch_zenventory_klb_inventory(
            username=zenventory_username,
            password=zenventory_password,
            base_url=zenventory_base_url,
        )

        options = dict(job.options)
        options["progress"] = 50
        options["status_message"] = "Fetching inventory from ShipBob..."
        job.options = options
        db.commit()
        db.refresh(job)

        shipbob_inventory = fetch_shipbob_total_inventory(
            api_key=shipbob_api_key,
            base_url=shipbob_base_url,
        )

        check_result = check_low_stock(
            klb_inventory=klb_inventory,
            shipbob_inventory=shipbob_inventory,
            klb_threshold=klb_threshold,
            shipbob_threshold=shipbob_threshold,
            excluded_skus=excluded_skus,
        )

        options = dict(job.options)
        options["progress"] = 80
        options["status_message"] = "Evaluating stock levels..."
        options["check_result"] = check_result
        options["items_found"] = check_result["total_low_items"]
        job.options = options
        db.commit()
        db.refresh(job)

        slack_sent = False
        if check_result["total_low_items"] > 0:
            checked_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            message = build_low_stock_slack_message(
                alert_name=alert_name,
                klb_threshold=klb_threshold,
                shipbob_threshold=shipbob_threshold,
                check_result=check_result,
                checked_at=checked_at,
            )
            slack_sent = send_slack_webhook(slack_webhook_url, message)
            if not slack_sent:
                job.status = "error"
                options["status_message"] = "Low stock found but Slack notification failed"
                options["slack_sent"] = False
                job.options = options
                job.error_message = "Failed to send Slack notification"
                db.commit()
                return
        else:
            logger.info(f"No low stock items found for alert '{alert_name}'")

        options = dict(job.options)
        options["progress"] = 100
        options["status_message"] = (
            "Alert sent to Slack" if check_result["total_low_items"] > 0 else "All stock levels OK"
        )
        options["slack_sent"] = slack_sent
        job.options = options
        job.status = "done"
        db.commit()
        logger.info(f"Low stock alert job {job_id} completed successfully")

    except Exception as e:
        import traceback

        error_trace = traceback.format_exc()
        logger.error(f"Error processing low stock alert job {job_id}: {str(e)}")
        logger.error(error_trace)
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "error"
            job.error_message = f"{str(e)}\n\nTraceback:\n{error_trace}"
            db.commit()
    finally:
        db.close()
