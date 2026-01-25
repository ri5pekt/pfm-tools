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

    # Try case-insensitive match and strip BOM characters
    for key, value in row.items():
        # Strip BOM and other whitespace from the key
        clean_key = key.lstrip('\ufeff').strip()
        if clean_key.lower() == order_id_header.lower():
            return str(value) if value else ""

    # Try common variations
    common_variations = ["order_id", "orderid", "order-id", "OrderID", "Order ID", "externalId", "external_id", "external-id"]
    for variation in common_variations:
        if variation in row:
            return str(row[variation]) if row[variation] else ""
        # Also try with BOM prefix
        bom_variation = '\ufeff' + variation
        if bom_variation in row:
            return str(row[bom_variation]) if row[bom_variation] else ""

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
    skipped_rows_no_order_id = 0
    for row in row_batch:
        order_id = find_order_id_column(row, order_id_header)
        if order_id:
            order_ids_in_batch.append(order_id)
        else:
            skipped_rows_no_order_id += 1
            logger.debug(f"Batch {batch_num}: Row skipped - no order ID found in column '{order_id_header}'")

    if skipped_rows_no_order_id > 0:
        logger.warning(f"Batch {batch_num}: {skipped_rows_no_order_id} rows skipped (no order ID found)")
    logger.info(f"Batch {batch_num}: Processing {len(order_ids_in_batch)} orders out of {len(row_batch)} rows")
    if order_ids_in_batch:
        logger.info(f"Batch {batch_num}: Sample order IDs: {order_ids_in_batch[:10]}{'...' if len(order_ids_in_batch) > 10 else ''}")

    # Fetch WooCommerce orders for this batch
    # Use batch API only, splitting into chunks of 300 orders (WooCommerce REST API supports large batches)
    order_data_cache = {}
    if woo_client and order_ids_in_batch:
        logger.info(f"Batch {batch_num}: Fetching {len(order_ids_in_batch)} WooCommerce orders using batch API...")

        # WooCommerce REST API supports batch loading
        # Use chunks of 30 orders per batch request
        chunk_size = 30
        total_found = 0
        total_not_found = 0

        for i in range(0, len(order_ids_in_batch), chunk_size):
            chunk = order_ids_in_batch[i:i + chunk_size]
            chunk_num = (i // chunk_size) + 1
            total_chunks = (len(order_ids_in_batch) + chunk_size - 1) // chunk_size

            logger.debug(f"Batch {batch_num}: Fetching chunk {chunk_num}/{total_chunks} ({len(chunk)} orders)...")
            chunk_results = woo_client.get_orders_batch(chunk)

            # Count found vs not found in this chunk
            chunk_found = sum(1 for v in chunk_results.values() if v is not None)
            chunk_not_found = sum(1 for v in chunk_results.values() if v is None)
            total_found += chunk_found
            total_not_found += chunk_not_found

            # Add results to cache
            order_data_cache.update(chunk_results)

            if chunk_not_found > 0:
                missing_in_chunk = [oid for oid, data in chunk_results.items() if data is None]
                logger.warning(f"Batch {batch_num}: Chunk {chunk_num} - {chunk_not_found}/{len(chunk)} orders not found: {', '.join(missing_in_chunk[:5])}{'...' if len(missing_in_chunk) > 5 else ''}")

        logger.info(f"Batch {batch_num}: WooCommerce batch fetch complete - Found: {total_found}, Not found: {total_not_found}")

        if total_not_found > 0:
            all_missing = [oid for oid, data in order_data_cache.items() if data is None]
            logger.warning(f"Batch {batch_num}: Total orders not found in WooCommerce: {', '.join(all_missing[:10])}{'...' if len(all_missing) > 10 else ''}")

    # For each order in this batch, fetch processor data if needed
    braintree_transaction_cache = {}
    afterpay_payment_cache = {}

    braintree_tasks = []
    afterpay_tasks = []

    if woo_client:
        payment_method_stats = {"braintree": 0, "afterpay": 0, "other": 0, "none": 0, "no_order_data": 0}
        for order_id, order_data in order_data_cache.items():
            if not order_data:
                payment_method_stats["no_order_data"] += 1
                logger.debug(f"Batch {batch_num}: Order {order_id} - No order data, skipping processor fetch")
                continue

            payment_method = woo_client.get_payment_method_from_data(order_data, order_id)
            logger.debug(f"Batch {batch_num}: Order {order_id} - Payment method: {payment_method}")

            # Collect Braintree tasks
            if braintree_client and payment_method and payment_method.startswith("braintree_"):
                payment_method_stats["braintree"] += 1
                transaction_id = woo_client.get_transaction_id_from_data(order_data, order_id)
                if transaction_id:
                    braintree_tasks.append((transaction_id, order_id))
                    logger.debug(f"Batch {batch_num}: Order {order_id} - Added Braintree task (transaction_id: {transaction_id})")
                else:
                    logger.warning(f"Batch {batch_num}: Order {order_id} - Braintree payment method detected but no transaction_id found")

            # Collect AfterPay tasks - check for variations like "afterpay", "afterpay_us", "afterpay_clearpay", etc.
            elif afterpay_client and payment_method and "afterpay" in payment_method.lower():
                payment_method_stats["afterpay"] += 1
                payment_id = woo_client.get_transaction_id_from_data(order_data, order_id)
                if payment_id:
                    afterpay_tasks.append((payment_id, order_id))
                    logger.info(f"Batch {batch_num}: Order {order_id} - Added AfterPay task (payment_id: {payment_id}, payment_method: {payment_method})")
                else:
                    logger.warning(f"Batch {batch_num}: Order {order_id} - AfterPay payment method detected ({payment_method}) but no transaction_id found")
            elif payment_method:
                payment_method_stats["other"] += 1
                logger.debug(f"Batch {batch_num}: Order {order_id} - Other payment method: {payment_method}")
            else:
                payment_method_stats["none"] += 1
                logger.debug(f"Batch {batch_num}: Order {order_id} - No payment method found")

        logger.info(f"Batch {batch_num}: Payment method stats - Braintree: {payment_method_stats['braintree']}, AfterPay: {payment_method_stats['afterpay']}, Other: {payment_method_stats['other']}, None: {payment_method_stats['none']}, No order data: {payment_method_stats['no_order_data']}")
        logger.info(f"Batch {batch_num}: Collected {len(braintree_tasks)} Braintree tasks, {len(afterpay_tasks)} AfterPay tasks")

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
            logger.info(f"Batch {batch_num}: Fetching {len(afterpay_tasks)} AfterPay payments...")
            def fetch_afterpay(payment_id: str, order_id: str) -> tuple[str, Optional[Dict[str, Any]]]:
                try:
                    logger.debug(f"Batch {batch_num}: Fetching AfterPay payment {payment_id} for order {order_id}")
                    payment_data = afterpay_client.get_payment(payment_id)
                    if payment_data:
                        logger.info(f"Batch {batch_num}: Successfully fetched AfterPay payment {payment_id} for order {order_id}")
                    else:
                        logger.warning(f"Batch {batch_num}: AfterPay payment {payment_id} for order {order_id} returned None")
                    return (payment_id, payment_data)
                except Exception as e:
                    logger.error(f"Batch {batch_num}: Error fetching AfterPay payment {payment_id} for order {order_id}: {str(e)}")
                    return (payment_id, None)

            max_workers = min(5, len(afterpay_tasks))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {executor.submit(fetch_afterpay, pid, oid): (pid, oid) for pid, oid in afterpay_tasks}
                afterpay_fetched = 0
                afterpay_failed = 0
                for future in as_completed(future_to_task):
                    payment_id, payment_data = future.result()
                    if payment_data:
                        afterpay_payment_cache[payment_id] = payment_data
                        afterpay_fetched += 1
                    else:
                        afterpay_failed += 1
                logger.info(f"Batch {batch_num}: AfterPay fetch complete - Success: {afterpay_fetched}, Failed: {afterpay_failed}")

    # Process and write rows with fetched data
    rows_written = 0
    for row in row_batch:
        order_id_value = find_order_id_column(row, order_id_header)

        # Add basic columns
        row["######"] = "######"
        row["order id copy"] = order_id_value
        
        # Extract original CSV values for comparison
        # Try to find taxableItemsAmount and salesTaxAmount columns (case-insensitive, strip BOM)
        taxable_items_amount_original = None
        sales_tax_amount_original = None
        
        for key in row.keys():
            # Strip BOM and whitespace from key before comparing
            clean_key = key.lstrip('\ufeff').strip().lower()
            if clean_key == "taxableitemsamount":
                try:
                    val = row[key]
                    if val and str(val).strip():
                        taxable_items_amount_original = float(val)
                except (ValueError, TypeError):
                    logger.debug(f"Batch {batch_num}: Order {order_id_value} - Could not parse taxableItemsAmount: {row[key]}")
            elif clean_key == "salestaxamount":
                try:
                    val = row[key]
                    if val and str(val).strip():
                        sales_tax_amount_original = float(val)
                except (ValueError, TypeError):
                    logger.debug(f"Batch {batch_num}: Order {order_id_value} - Could not parse salesTaxAmount: {row[key]}")

        # Get WooCommerce data
        if woo_client and order_id_value:
            try:
                order_data = order_data_cache.get(order_id_value)

                if order_data is None:
                    logger.warning(f"Batch {batch_num}: Order {order_id_value} - NOT FOUND in WooCommerce (order_data is None)")
                else:
                    logger.debug(f"Batch {batch_num}: Order {order_id_value} - Found in WooCommerce cache")

                totals = woo_client.get_order_totals_from_data(order_data, order_id_value)
                payment_method = woo_client.get_payment_method_from_data(order_data, order_id_value)
                has_ppu = woo_client.get_ppu_status_from_data(order_data, order_id_value)

                logger.debug(f"Batch {batch_num}: Order {order_id_value} - Totals: {totals}, Payment method: {payment_method}, Has PPU: {has_ppu}")

                row["woo_total_tax"] = str(totals["total_with_tax"]) if totals["total_with_tax"] is not None else ""
                row["woo_tax"] = str(totals["tax"]) if totals["tax"] is not None else ""
                row["woo_payment_method"] = payment_method if payment_method else ""
                row["has_ppu"] = "Yes" if has_ppu else "No"
                
                # Calculate differences for WooCommerce data
                # woo_total_tax_diff: WooCommerce taxable amount (total - tax) vs taxableItemsAmount from origin
                if totals["total_with_tax"] is not None and totals["tax"] is not None and taxable_items_amount_original is not None:
                    woo_taxable_amount = totals["total_with_tax"] - totals["tax"]
                    woo_total_tax_diff = woo_taxable_amount - taxable_items_amount_original
                    row["woo_total_tax_diff"] = str(round(woo_total_tax_diff, 2))
                else:
                    row["woo_total_tax_diff"] = ""
                
                # woo_tax_diff: WooCommerce tax vs salesTaxAmount from origin
                if totals["tax"] is not None and sales_tax_amount_original is not None:
                    woo_tax_diff = totals["tax"] - sales_tax_amount_original
                    row["woo_tax_diff"] = str(round(woo_tax_diff, 2))
                else:
                    row["woo_tax_diff"] = ""

                # Get processor data
                processor_data_added = False
                processor_total_value = None
                processor_tax_value = None

                # Braintree
                if braintree_client and payment_method and payment_method.startswith("braintree_"):
                    transaction_id = woo_client.get_transaction_id_from_data(order_data, order_id_value)
                    if transaction_id:
                        transaction_data = braintree_transaction_cache.get(transaction_id)
                        braintree_data = braintree_client.get_transaction_data_from_dict(transaction_data, transaction_id)
                        processor_total_value = braintree_data["braintree_amount"]
                        processor_tax_value = braintree_data["braintree_tax_amount"]
                        row["processor_total"] = str(processor_total_value) if processor_total_value is not None else ""
                        row["processor_tax"] = str(processor_tax_value) if processor_tax_value is not None else ""
                        processor_data_added = True

                # AfterPay - check for variations like "afterpay", "afterpay_us", "afterpay_clearpay", etc.
                elif afterpay_client and payment_method and "afterpay" in payment_method.lower():
                    payment_id = woo_client.get_transaction_id_from_data(order_data, order_id_value)
                    if payment_id:
                        payment_data = afterpay_payment_cache.get(payment_id)
                        if payment_data:
                            logger.debug(f"Batch {batch_num}: Order {order_id_value} - Processing AfterPay data (payment_id: {payment_id}, payment_method: {payment_method})")
                            afterpay_data = afterpay_client.get_payment_data_from_dict(payment_data, payment_id)
                            processor_total_value = afterpay_data["processor_total"]
                            processor_tax_value = afterpay_data["processor_tax"]
                            row["processor_total"] = str(processor_total_value) if processor_total_value is not None else ""
                            row["processor_tax"] = str(processor_tax_value) if processor_tax_value is not None else ""
                            processor_data_added = True
                            logger.info(f"Batch {batch_num}: Order {order_id_value} - AfterPay data added: total={row['processor_total']}, tax={row['processor_tax']}")
                        else:
                            logger.warning(f"Batch {batch_num}: Order {order_id_value} - AfterPay payment_id {payment_id} found but no payment_data in cache")
                    else:
                        logger.warning(f"Batch {batch_num}: Order {order_id_value} - AfterPay payment method ({payment_method}) detected but no transaction_id found")

                # Calculate processor differences
                if braintree_client or afterpay_client:
                    # processor_total_diff: Processor total vs taxableItemsAmount from origin
                    if processor_total_value is not None and taxable_items_amount_original is not None:
                        try:
                            # Convert processor_total_value to float if it's a string
                            processor_total_float = float(processor_total_value) if isinstance(processor_total_value, str) else processor_total_value
                            processor_total_diff = processor_total_float - taxable_items_amount_original
                            row["processor_total_diff"] = str(round(processor_total_diff, 2))
                        except (ValueError, TypeError) as e:
                            logger.error(f"Batch {batch_num}: Order {order_id_value} - Error calculating processor_total_diff: {str(e)}")
                            row["processor_total_diff"] = ""
                    else:
                        row["processor_total_diff"] = ""
                    
                    # processor_tax_diff: Processor tax vs salesTaxAmount from origin
                    if processor_tax_value is not None and sales_tax_amount_original is not None:
                        try:
                            # Convert processor_tax_value to float if it's a string
                            processor_tax_float = float(processor_tax_value) if isinstance(processor_tax_value, str) else processor_tax_value
                            processor_tax_diff = processor_tax_float - sales_tax_amount_original
                            row["processor_tax_diff"] = str(round(processor_tax_diff, 2))
                        except (ValueError, TypeError) as e:
                            logger.error(f"Batch {batch_num}: Order {order_id_value} - Error calculating processor_tax_diff: {str(e)}")
                            row["processor_tax_diff"] = ""
                    else:
                        row["processor_tax_diff"] = ""

                # Set empty processor columns if not added
                if not processor_data_added and (braintree_client or afterpay_client):
                    row["processor_total"] = ""
                    row["processor_tax"] = ""
                    row["processor_total_diff"] = ""
                    row["processor_tax_diff"] = ""
                    if payment_method:
                        logger.debug(f"Batch {batch_num}: Order {order_id_value} - No processor data added (payment_method: {payment_method})")
                    else:
                        logger.debug(f"Batch {batch_num}: Order {order_id_value} - No processor data added (no payment method)")

            except Exception as e:
                logger.error(f"Error processing WooCommerce data for order {order_id_value}: {str(e)}", exc_info=True)
                row["woo_total_tax"] = ""
                row["woo_tax"] = ""
                row["woo_payment_method"] = ""
                row["woo_total_tax_diff"] = ""
                row["woo_tax_diff"] = ""
                row["has_ppu"] = ""
                if braintree_client or afterpay_client:
                    row["processor_total"] = ""
                    row["processor_tax"] = ""
                    row["processor_total_diff"] = ""
                    row["processor_tax_diff"] = ""
        elif woo_client:
            # No order ID
            logger.debug(f"Batch {batch_num}: Row skipped - no order ID found")
            row["woo_total_tax"] = ""
            row["woo_tax"] = ""
            row["woo_payment_method"] = ""
            row["woo_total_tax_diff"] = ""
            row["woo_tax_diff"] = ""
            row["has_ppu"] = ""
            if braintree_client or afterpay_client:
                row["processor_total"] = ""
                row["processor_tax"] = ""
                row["processor_total_diff"] = ""
                row["processor_tax_diff"] = ""
        else:
            # WooCommerce disabled
            if braintree_client or afterpay_client:
                row["processor_total"] = ""
                row["processor_tax"] = ""
                row["processor_total_diff"] = ""
                row["processor_tax_diff"] = ""

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
        # Default to "externalId" for Complyt CSV files, fallback to "OrderID"
        order_id_header = job.options.get("order_id_header", "externalId") if job.options else "externalId"
        logger.info(f"Using order_id_header: '{order_id_header}'")

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
                new_columns.extend([
                    "woo_total_tax", 
                    "woo_tax", 
                    "woo_payment_method",
                    "woo_total_tax_diff",
                    "woo_tax_diff",
                    "has_ppu"
                ])
            if braintree_client or afterpay_client:
                new_columns.extend([
                    "processor_total", 
                    "processor_tax",
                    "processor_total_diff",
                    "processor_tax_diff"
                ])
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
