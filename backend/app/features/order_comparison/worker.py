import os
import logging
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.db import SessionLocal
from ...jobs.models import Job
from ...features.sales_tax_processor.woocommerce_client import WooCommerceClient
from .service import parse_complyt_csv, fetch_woocommerce_orders, generate_comparison_report, create_comparison_report_zip

settings = get_settings()
logger = logging.getLogger(__name__)


def ensure_dirs():
    os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(settings.uploads_dir, exist_ok=True)
    os.makedirs(settings.processed_dir, exist_ok=True)


def run_comparison_job(job_id: int):
    """
    Worker function to process order comparison job.
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

        input_path = job.input_filename
        if not os.path.exists(input_path):
            job.status = "error"
            job.error_message = f"Input file not found: {input_path}"
            db.commit()
            return

        # Get options from job
        options = job.options or {}
        order_id_header = options.get("order_id_header", "externalId")
        date_from = options.get("date_from")
        date_to = options.get("date_to")
        usa_only = options.get("usa_only", True)  # Default to True
        exclude_states = options.get("exclude_states", [])  # Default to empty list
        exclude_complyt_states = options.get("exclude_complyt_states", [])  # Default to empty list


        if not date_from or not date_to:
            job.status = "error"
            job.error_message = "Date range not specified"
            db.commit()
            return

        # Update progress
        new_options = dict(options)
        new_options['progress'] = 5
        new_options['status_message'] = 'Parsing Complyt CSV file...'
        job.options = new_options
        db.commit()
        db.refresh(job)

        # Parse Complyt CSV (with country and state filtering)
        logger.info(f"Parsing Complyt CSV file: {input_path}")
        if usa_only:
            logger.info(f"Filtering Complyt CSV: USA orders only")
        if exclude_complyt_states:
            logger.info(f"Excluding Complyt CSV orders from states: {', '.join(exclude_complyt_states)}")
        complyt_data = parse_complyt_csv(
            input_path,
            order_id_header,
            date_from=date_from,
            date_to=date_to,
            exclude_states=exclude_complyt_states,
            usa_only=usa_only
        )
        logger.info(f"Found {len(complyt_data['invoices'])} invoices, "
                   f"{len(complyt_data['taxable_refunds'])} taxable refunds, "
                   f"{len(complyt_data['refunds'])} refunds in Complyt CSV")

        # Update progress
        new_options = dict(options)
        new_options['progress'] = 5
        new_options['status_message'] = 'Fetching WooCommerce orders...'
        job.options = new_options
        db.commit()
        db.refresh(job)

        # Initialize WooCommerce client
        try:
            woo_client = WooCommerceClient()
            logger.info("WooCommerce client initialized successfully")
        except (ValueError, Exception) as e:
            job.status = "error"
            job.error_message = f"Failed to initialize WooCommerce client: {str(e)}"
            db.commit()
            return

        # Fetch WooCommerce orders
        logger.info(f"Fetching WooCommerce orders for date range: {date_from} to {date_to}")
        if usa_only:
            logger.info(f"Filtering: USA orders only")
        if exclude_states:
            logger.info(f"Excluding states: {', '.join(exclude_states)}")

        try:
            woo_data = fetch_woocommerce_orders(
                date_from,
                date_to,
                woo_client,
                job_id=job.id,
                db=db,
                usa_only=usa_only,
                exclude_states=exclude_states
            )
            logger.info(f"=== WooCommerce fetch completed ===")
            logger.info(f"Found {len(woo_data['orders'])} orders and {len(woo_data['refunds'])} refunds in WooCommerce")
        except Exception as e:
            logger.error(f"Error during WooCommerce fetch: {str(e)}", exc_info=True)
            raise

        # Update progress
        new_options = dict(options)
        new_options['progress'] = 98
        new_options['status_message'] = 'Generating comparison report...'
        job.options = new_options
        db.commit()
        db.refresh(job)

        # Generate comparison report (CSV files in ZIP archive)
        logger.info("Generating comparison report (CSV files in ZIP archive)")
        output_path = os.path.join(
            settings.processed_dir,
            f"job_{job.id}_comparison_report.zip",
        )

        try:
            create_comparison_report_zip(
                complyt_data,
                woo_data,
                output_path,
                date_from=date_from,
                date_to=date_to
            )
            logger.info(f"ZIP report saved to: {output_path}")
        except Exception as e:
            logger.error(f"Error generating ZIP report: {str(e)}", exc_info=True)
            # Fallback to text report if ZIP generation fails
            logger.warning("Falling back to text report format")
            output_path = os.path.join(
                settings.processed_dir,
                f"job_{job.id}_comparison_report.txt",
            )
            report_content = generate_comparison_report(complyt_data, woo_data)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            logger.info(f"Text report saved to: {output_path}")

        # Clean up WooCommerce client
        woo_client.close()

        # Final check before marking as done
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            if os.path.exists(output_path):
                os.remove(output_path)
            return

        # Update progress to 100%
        new_options = dict(options)
        new_options['progress'] = 100
        new_options['status_message'] = 'Comparison completed'
        job.options = new_options

        job.status = "done"
        job.output_filename = output_path
        db.commit()
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error processing comparison job {job_id}: {str(e)}")
        logger.error(error_trace)
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "error"
            job.error_message = f"{str(e)}\n\nTraceback:\n{error_trace}"
            db.commit()
    finally:
        db.close()

