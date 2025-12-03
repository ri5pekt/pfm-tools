import csv
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...jobs.models import Job
from .woocommerce_client import WooCommerceClient
from .braintree_client import BraintreeClient
from .afterpay_client import AfterPayClient

settings = get_settings()

# Set up logger
logger = logging.getLogger(__name__)


def ensure_dirs():
    os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(settings.uploads_dir, exist_ok=True)
    os.makedirs(settings.processed_dir, exist_ok=True)


def find_order_id_column(row: Dict[str, Any], order_id_header: str) -> str:
    """
    Find the order ID value in the row, trying different case variations.
    Returns empty string if not found.
    """
    # Try exact match first
    if order_id_header in row:
        return str(row[order_id_header]) if row[order_id_header] else ""

    # Try case-insensitive match
    for key, value in row.items():
        if key.lower() == order_id_header.lower():
            return str(value) if value else ""

    # Try common variations
    common_variations = ["order_id", "orderid", "order-id", "OrderID", "Order ID"]
    for variation in common_variations:
        if variation in row:
            return str(row[variation]) if row[variation] else ""

    return ""


def process_batch(
    row_batch: List[Dict[str, Any]],
    batch_num: int,
    woo_client: Optional[WooCommerceClient],
    braintree_client: Optional[BraintreeClient],
    afterpay_client: Optional[AfterPayClient],
    order_id_header: str,
    writer: csv.DictWriter,
    rows_processed: int,
    total_rows: int,
    job_id: int,
    db: Session
) -> int:
    """
    Process a batch of CSV rows:
    1. Extract order IDs from the batch
    2. Fetch WooCommerce orders for those IDs
    3. For each order, fetch processor data (Braintree/AfterPay) if needed
    4. Process and write rows with the fetched data

    Returns the number of rows processed in this batch.
    """
    batch_start_time = time.time()

    if not row_batch:
        return 0

    # Extract order IDs from this batch
    order_ids_in_batch = []
    for row in row_batch:
        order_id = find_order_id_column(row, order_id_header)
        if order_id:
            order_ids_in_batch.append(order_id)

    # Fetch WooCommerce orders for this batch
    # Try batch API call first (using 'include' parameter), fall back to parallel individual calls if it fails
    order_data_cache = {}
    if woo_client and order_ids_in_batch:
        batch_results = woo_client.get_orders_batch(order_ids_in_batch)

        # Check if batch fetch failed (all None results indicates batch API failed)
        if batch_results and len(batch_results) == len(order_ids_in_batch) and all(v is None for v in batch_results.values()):
            logger.warning(f"Batch {batch_num}: WooCommerce batch API failed. Falling back to parallel individual calls...")

            # Use ThreadPoolExecutor to make parallel API calls
            # Max 5 concurrent workers to avoid overwhelming the API
            max_workers = min(5, len(order_ids_in_batch))

            def fetch_order(order_id: str) -> tuple[str, Optional[Dict[str, Any]]]:
                """Fetch a single order and return (order_id, order_data)"""
                try:
                    order_data = woo_client.get_order(order_id)
                    return (order_id, order_data)
                except Exception as e:
                    logger.error(f"Batch {batch_num}: Error fetching order {order_id}: {str(e)}")
                    return (order_id, None)

            # Execute all calls in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_order = {executor.submit(fetch_order, order_id): order_id for order_id in order_ids_in_batch}
                for future in as_completed(future_to_order):
                    order_id, order_data = future.result()
                    order_data_cache[order_id] = order_data
        else:
            # Batch API succeeded!
            order_data_cache.update(batch_results)

    # For each order in this batch, fetch processor data if needed
    braintree_transaction_cache = {}
    afterpay_payment_cache = {}

    braintree_tasks = []
    afterpay_tasks = []

    if woo_client:
        for order_id, order_data in order_data_cache.items():
            if not order_data:
                continue

            payment_method = woo_client.get_payment_method_from_data(order_data, order_id)

            # Collect Braintree tasks
            if braintree_client and payment_method and payment_method.startswith("braintree_"):
                transaction_id = woo_client.get_transaction_id_from_data(order_data, order_id)
                if transaction_id:
                    braintree_tasks.append((transaction_id, order_id))

            # Collect AfterPay tasks
            elif afterpay_client and payment_method and payment_method.lower() == "afterpay":
                payment_id = woo_client.get_transaction_id_from_data(order_data, order_id)
                if payment_id:
                    afterpay_tasks.append((payment_id, order_id))

        # Fetch Braintree transactions in parallel
        if braintree_tasks:
            def fetch_braintree(transaction_id: str, order_id: str) -> tuple[str, Optional[Dict[str, Any]]]:
                try:
                    transaction_data = braintree_client.get_transaction(transaction_id)
                    return (transaction_id, transaction_data)
                except Exception as e:
                    logger.error(f"Batch {batch_num}: Error fetching Braintree transaction {transaction_id}: {str(e)}")
                    return (transaction_id, None)

            max_workers = min(5, len(braintree_tasks))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {executor.submit(fetch_braintree, tid, oid): (tid, oid) for tid, oid in braintree_tasks}
                for future in as_completed(future_to_task):
                    transaction_id, transaction_data = future.result()
                    if transaction_data:
                        braintree_transaction_cache[transaction_id] = transaction_data

        # Fetch AfterPay payments in parallel
        if afterpay_tasks:
            def fetch_afterpay(payment_id: str, order_id: str) -> tuple[str, Optional[Dict[str, Any]]]:
                try:
                    payment_data = afterpay_client.get_payment(payment_id)
                    return (payment_id, payment_data)
                except Exception as e:
                    logger.error(f"Batch {batch_num}: Error fetching AfterPay payment {payment_id}: {str(e)}")
                    return (payment_id, None)

            max_workers = min(5, len(afterpay_tasks))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {executor.submit(fetch_afterpay, pid, oid): (pid, oid) for pid, oid in afterpay_tasks}
                for future in as_completed(future_to_task):
                    payment_id, payment_data = future.result()
                    if payment_data:
                        afterpay_payment_cache[payment_id] = payment_data

    # Process and write rows with fetched data
    rows_written = 0
    for row in row_batch:
        order_id_value = find_order_id_column(row, order_id_header)

        # Add basic columns
        row["######"] = "######"
        row["order id copy"] = order_id_value

        # Get WooCommerce data
        if woo_client and order_id_value:
            try:
                order_data = order_data_cache.get(order_id_value)
                totals = woo_client.get_order_totals_from_data(order_data, order_id_value)
                payment_method = woo_client.get_payment_method_from_data(order_data, order_id_value)

                row["woo_total_tax"] = str(totals["total_with_tax"]) if totals["total_with_tax"] is not None else ""
                row["woo_tax"] = str(totals["tax"]) if totals["tax"] is not None else ""
                row["woo_payment_method"] = payment_method if payment_method else ""

                # Get processor data
                processor_data_added = False

                # Braintree
                if braintree_client and payment_method and payment_method.startswith("braintree_"):
                    transaction_id = woo_client.get_transaction_id_from_data(order_data, order_id_value)
                    if transaction_id:
                        transaction_data = braintree_transaction_cache.get(transaction_id)
                        braintree_data = braintree_client.get_transaction_data_from_dict(transaction_data, transaction_id)
                        row["processor_total"] = str(braintree_data["braintree_amount"]) if braintree_data["braintree_amount"] is not None else ""
                        row["processor_tax"] = str(braintree_data["braintree_tax_amount"]) if braintree_data["braintree_tax_amount"] is not None else ""
                        processor_data_added = True

                # AfterPay
                elif afterpay_client and payment_method and payment_method.lower() == "afterpay":
                    payment_id = woo_client.get_transaction_id_from_data(order_data, order_id_value)
                    if payment_id:
                        payment_data = afterpay_payment_cache.get(payment_id)
                        if payment_data:
                            afterpay_data = afterpay_client.get_payment_data_from_dict(payment_data, payment_id)
                            row["processor_total"] = str(afterpay_data["processor_total"]) if afterpay_data["processor_total"] is not None else ""
                            row["processor_tax"] = str(afterpay_data["processor_tax"]) if afterpay_data["processor_tax"] is not None else ""
                            processor_data_added = True

                # Set empty processor columns if not added
                if not processor_data_added and (braintree_client or afterpay_client):
                    row["processor_total"] = ""
                    row["processor_tax"] = ""

            except Exception as e:
                logger.error(f"Error processing WooCommerce data for order {order_id_value}: {str(e)}", exc_info=True)
                row["woo_total_tax"] = ""
                row["woo_tax"] = ""
                row["woo_payment_method"] = ""
                if braintree_client or afterpay_client:
                    row["processor_total"] = ""
                    row["processor_tax"] = ""
        elif woo_client:
            # No order ID
            row["woo_total_tax"] = ""
            row["woo_tax"] = ""
            row["woo_payment_method"] = ""
            if braintree_client or afterpay_client:
                row["processor_total"] = ""
                row["processor_tax"] = ""
        else:
            # WooCommerce disabled
            if braintree_client or afterpay_client:
                row["processor_total"] = ""
                row["processor_tax"] = ""

        writer.writerow(row)
        rows_written += 1

    batch_duration = time.time() - batch_start_time
    logger.info(f"Batch {batch_num}: Processed {rows_written} rows in {batch_duration:.2f}s")
    return rows_written


def process_sales_tax_job(job_id: int, db_session_factory):
    """
    This is the long-running worker function.
    - Load job + CSV
    - Process CSV rows and add new columns
    - Write processed CSV
    """
    job_start_time = time.time()
    logger.info(f"Starting Sales Tax Processor job {job_id}")

    ensure_dirs()
    db = db_session_factory()
    try:
        job: Job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            # Job was deleted, stop processing
            return

        job.status = "running"
        db.commit()
        db.refresh(job)

        # Double-check job still exists (might have been deleted)
        if not db.query(Job).filter(Job.id == job_id).first():
            return

        input_path = job.input_filename
        if not os.path.exists(input_path):
            job.status = "error"
            job.error_message = f"Input file not found: {input_path}"
            db.commit()
            return

        # Get order_id_header from job options
        order_id_header = job.options.get("order_id_header", "OrderID") if job.options else "OrderID"

        # Check if WooCommerce integration is enabled
        woo_enabled = job.options.get("woo", True) if job.options else True

        # Check if Braintree integration is enabled
        braintree_enabled = job.options.get("braintree", True) if job.options else True

        # Check if AfterPay integration is enabled
        afterpay_enabled = job.options.get("afterpay", True) if job.options else True

        # Initialize WooCommerce client if enabled and credentials are available
        woo_client: Optional[WooCommerceClient] = None
        if woo_enabled:
            logger.info(f"WooCommerce integration is enabled for job {job_id}")
            try:
                woo_client = WooCommerceClient()
                logger.info(f"WooCommerce client initialized successfully")
            except (ValueError, Exception) as e:
                # If WooCommerce credentials are not configured, continue without it
                logger.warning(f"WooCommerce integration disabled or misconfigured: {str(e)}")
                woo_client = None
        else:
            logger.info(f"WooCommerce integration is disabled for job {job_id}")

        # Initialize Braintree client if enabled and credentials are available
        braintree_client: Optional[BraintreeClient] = None
        if braintree_enabled:
            logger.info(f"Braintree integration is enabled for job {job_id}")
            try:
                braintree_client = BraintreeClient()
                logger.info(f"Braintree client initialized successfully")
            except (ValueError, Exception) as e:
                # If Braintree credentials are not configured, continue without it
                logger.warning(f"Braintree integration disabled or misconfigured: {str(e)}")
                braintree_client = None
        else:
            logger.info(f"Braintree integration is disabled for job {job_id}")

        # Initialize AfterPay client if enabled and credentials are available
        afterpay_client: Optional[AfterPayClient] = None
        if afterpay_enabled:
            logger.info(f"AfterPay integration is enabled for job {job_id}")
            try:
                afterpay_client = AfterPayClient()
                logger.info(f"AfterPay client initialized successfully")
            except (ValueError, Exception) as e:
                # If AfterPay credentials are not configured, continue without it
                logger.warning(f"AfterPay integration disabled or misconfigured: {str(e)}")
                afterpay_client = None
        else:
            logger.info(f"AfterPay integration is disabled for job {job_id}")

        output_path = os.path.join(
            settings.processed_dir,
            f"job_{job.id}_processed.csv",
        )

        # Count total rows first for progress tracking
        logger.info(f"Counting total rows in input file...")
        total_rows = 0
        with open(input_path, newline="", encoding="utf-8", errors="ignore") as count_file:
            count_reader = csv.DictReader(count_file)
            total_rows = sum(1 for _ in count_reader)
        logger.info(f"Total rows to process: {total_rows}")

        # Initialize progress to 0%
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            new_options = dict(job.options) if job.options else {}
            new_options['progress'] = 0
            new_options['rows_processed'] = 0
            new_options['total_rows'] = total_rows
            job.options = new_options
            db.commit()
            db.refresh(job)
            logger.info(f"Initialized progress: 0% (0/{total_rows})")

        # Process in batches: fetch WooCommerce orders, get processor data, process rows, repeat
        # This is more memory-efficient and provides better progress feedback
        batch_size = 30
        logger.info(f"Processing {total_rows} rows in batches of {batch_size}")

        # Process CSV file - stream processing in batches
        rows_processed = 0
        with open(input_path, newline="", encoding="utf-8", errors="ignore") as infile, open(
            output_path, "w", newline="", encoding="utf-8"
        ) as outfile:
            reader = csv.DictReader(infile)
            original_fieldnames = list(reader.fieldnames or [])

            # Add new columns
            new_columns = ["######", "order id copy"]
            if woo_client:
                new_columns.extend(["woo_total_tax", "woo_tax", "woo_payment_method"])
            if braintree_client or afterpay_client:
                new_columns.extend(["processor_total", "processor_tax"])
            fieldnames = original_fieldnames + new_columns

            logger.info(f"CSV columns: {fieldnames}")
            logger.info(f"New columns added: {new_columns}")

            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            logger.info("CSV header written")

            # Process rows in batches
            row_batch = []
            batch_num = 0

            for row in reader:
                row_batch.append(row)

                # When we have a full batch (or reach end of file), process it
                if len(row_batch) >= batch_size:
                    batch_num += 1
                    rows_processed_in_batch = process_batch(
                        row_batch, batch_num, woo_client, braintree_client, afterpay_client,
                        order_id_header, writer, rows_processed, total_rows, job_id, db
                    )
                    rows_processed += rows_processed_in_batch
                    row_batch = []  # Clear batch for next iteration

                    # Update progress after each batch
                    if total_rows > 0:
                        progress = int((rows_processed / total_rows) * 100)
                        progress = min(99, max(1, progress))

                        # Calculate estimated total batches
                        total_batches = (total_rows + batch_size - 1) // batch_size
                        batch_percentage = int((batch_num / total_batches) * 100) if total_batches > 0 else 0

                        job = db.query(Job).filter(Job.id == job_id).first()
                        if job:
                            # Check if job was deleted
                            if not job:
                                outfile.close()
                                if os.path.exists(output_path):
                                    os.remove(output_path)
                                return

                            new_options = dict(job.options) if job.options else {}
                            new_options['progress'] = progress
                            new_options['rows_processed'] = rows_processed
                            new_options['total_rows'] = total_rows
                            new_options['status_message'] = f'Processing batch {batch_num}/{total_batches} ({rows_processed}/{total_rows} rows)...'
                            job.options = new_options
                            db.commit()
                            logger.info(f"Progress updated: {progress}% - Batch {batch_num}/{total_batches} ({rows_processed}/{total_rows} rows)")

            # Process remaining rows (if any)
            if row_batch:
                batch_num += 1
                rows_processed_in_batch = process_batch(
                    row_batch, batch_num, woo_client, braintree_client, afterpay_client,
                    order_id_header, writer, rows_processed, total_rows, job_id, db
                )
                rows_processed += rows_processed_in_batch

                # Update progress for final batch
                if total_rows > 0:
                    progress = int((rows_processed / total_rows) * 100)
                    progress = min(99, max(1, progress))
                    total_batches = (total_rows + batch_size - 1) // batch_size

                    job = db.query(Job).filter(Job.id == job_id).first()
                    if job:
                        new_options = dict(job.options) if job.options else {}
                        new_options['progress'] = progress
                        new_options['rows_processed'] = rows_processed
                        new_options['total_rows'] = total_rows
                        new_options['status_message'] = f'Processing batch {batch_num}/{total_batches} ({rows_processed}/{total_rows} rows)...'
                        job.options = new_options
                        db.commit()

        # Clean up clients
        if woo_client:
            woo_client.close()
        if afterpay_client:
            afterpay_client.close()
        # Braintree client doesn't need explicit cleanup (no persistent connections)

        # Final check before marking as done
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            # Job was deleted, clean up output file
            if os.path.exists(output_path):
                os.remove(output_path)
            return

        # Set final progress to 100%
        # Create a new dict to ensure SQLAlchemy detects the change to JSONB
        new_options = dict(job.options) if job.options else {}
        new_options['progress'] = 100
        new_options['rows_processed'] = rows_processed
        new_options['total_rows'] = total_rows
        job.options = new_options

        job.status = "done"
        job.output_filename = output_path
        db.commit()

        job_duration = time.time() - job_start_time
        logger.info(f"Job {job_id} completed: Processed {rows_processed} rows in {job_duration/60:.2f} minutes")
        if rows_processed > 0:
            logger.info(f"Average time per row: {job_duration/rows_processed:.3f}s")
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "error"
            job.error_message = f"{str(e)}\n\nTraceback:\n{error_trace}"
            db.commit()
    finally:
        db.close()
