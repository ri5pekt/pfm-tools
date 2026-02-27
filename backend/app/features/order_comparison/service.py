import csv
import logging
import time
import zipfile
import os
import tempfile
import shutil
from datetime import datetime
from typing import Dict, List, Set, Optional, Any
from collections import defaultdict
from sqlalchemy.orm import Session
from io import BytesIO
import pytz

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from ...core.config import get_settings
from ...features.sales_tax_processor.woocommerce_client import WooCommerceClient
from ...jobs.models import Job

settings = get_settings()
logger = logging.getLogger(__name__)


def _parse_complyt_date(date_str: str, utc_tz) -> Optional[datetime]:
    """
    Parse a Complyt date string (UTC format) to a datetime object.

    Supports various formats:
    - ISO with Z: "2025-10-01T04:14:19.000Z"
    - ISO without Z: "2025-10-01T04:14:19.000"
    - Timestamp (milliseconds): 1727782459000
    - Space-separated: "2025-10-01 04:14:19"

    Args:
        date_str: Date string in various formats
        utc_tz: UTC timezone object

    Returns:
        datetime object in UTC, or None if parsing fails
    """
    try:
        transaction_date = None

        # Try parsing as timestamp (milliseconds or seconds)
        if date_str.isdigit():
            try:
                timestamp = int(date_str)
                # If timestamp is in milliseconds (13 digits), convert to seconds
                if timestamp > 1e12:  # Likely milliseconds
                    timestamp = timestamp / 1000
                transaction_date = datetime.fromtimestamp(timestamp, tz=utc_tz)
                return transaction_date
            except (ValueError, OSError):
                pass

        # Try ISO format with Z suffix (UTC)
        if date_str.endswith('Z'):
            # Remove Z and parse as UTC
            date_str_no_z = date_str[:-1]
            if '.' in date_str_no_z:
                # Has milliseconds: "2025-10-01T04:14:19.000"
                transaction_date = datetime.strptime(date_str_no_z, '%Y-%m-%dT%H:%M:%S.%f')
            else:
                # No milliseconds: "2025-10-01T04:14:19"
                transaction_date = datetime.strptime(date_str_no_z, '%Y-%m-%dT%H:%M:%S')
            transaction_date = utc_tz.localize(transaction_date)
        elif 'T' in date_str:
            # ISO format without Z, try parsing with fromisoformat
            try:
                transaction_date = datetime.fromisoformat(date_str.replace('Z', ''))
                if transaction_date.tzinfo is None:
                    transaction_date = utc_tz.localize(transaction_date)
            except:
                # Fallback to strptime
                if '.' in date_str:
                    transaction_date = datetime.strptime(date_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
                else:
                    transaction_date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
                transaction_date = utc_tz.localize(transaction_date)
        else:
            # Try other formats (space-separated)
            transaction_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            transaction_date = utc_tz.localize(transaction_date)

        return transaction_date
    except Exception as e:
        logger.debug(f"Error parsing date '{date_str}': {str(e)}")
        return None


def _process_complyt_row(row: Dict, order_id_header: str, result: Dict) -> None:
    """
    Process a single Complyt CSV row and add to result dictionary.

    Args:
        row: CSV row as dictionary
        order_id_header: Column name for order ID
        result: Result dictionary to update
    """
    order_id = str(row.get(order_id_header, '')).strip()
    if not order_id:
        return

    # Normalize order ID: remove any leading zeros or whitespace issues
    # Convert to string and strip to ensure consistent format
    order_id = str(order_id).strip()

    transaction_type = row.get('transactionType', '').strip()
    total_items_amount = row.get('totalItemsAmount', '0')

    # Extract transaction date - try multiple possible column names
    # Complyt CSV uses 'externalTimestamps.createdDate' (e.g., "2025-10-01T04:05:27.000Z")
    transaction_date = ''
    date_fields = ['externalTimestamps.createdDate', 'externalTimestamps.created_date', 'transactionDate', 'date', 'createdAt', 'created_at', 'transaction_date', 'dateCreated', 'date_created', 'externalTimestamps.created', 'createdDate']
    for field in date_fields:
        if field in row and row[field]:
            transaction_date = str(row[field]).strip()
            if transaction_date:
                break

    # Try to parse and format the date if found
    formatted_date = 'N/A'
    if transaction_date:
        try:
            utc_tz = pytz.UTC
            parsed_date = _parse_complyt_date(transaction_date, utc_tz)
            if parsed_date:
                formatted_date = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
            else:
                formatted_date = transaction_date  # Keep original if parsing fails
        except Exception as e:
            logger.debug(f"Error parsing date '{transaction_date}': {str(e)}")
            formatted_date = transaction_date  # Keep original if parsing fails

    try:
        amount = float(total_items_amount) if total_items_amount else 0.0
    except (ValueError, TypeError):
        amount = 0.0

    if transaction_type == 'INVOICE':
        result['invoices'].append(order_id)
        result['invoice_amounts'][order_id] = amount
        result['invoice_dates'][order_id] = formatted_date
    elif transaction_type == 'TAXABLE_REFUND':
        result['taxable_refunds'].append(order_id)
        result['taxable_refund_amounts'][order_id] = abs(amount)  # Make positive for reporting
        result['taxable_refund_dates'][order_id] = formatted_date
        # Try to find parent order ID - refund IDs might match order IDs or be in a separate field
        parent_order_id = ''
        parent_id_fields = ['orderId', 'parentOrderId', 'externalId', 'order_id', 'parent_order_id', 'parentId', 'parent_id']
        for field in parent_id_fields:
            if field in row and row[field]:
                parent_order_id = str(row[field]).strip()
                if parent_order_id:
                    break
        if parent_order_id:
            result['taxable_refund_parent_order_ids'][order_id] = parent_order_id
        else:
            result['taxable_refund_parent_order_ids'][order_id] = 'N/A'
    elif transaction_type == 'REFUND':
        result['refunds'].append(order_id)
        result['refund_amounts'][order_id] = abs(amount)  # Make positive for reporting
        result['refund_dates'][order_id] = formatted_date
        # Try to find parent order ID - refund IDs might match order IDs or be in a separate field
        parent_order_id = ''
        parent_id_fields = ['orderId', 'parentOrderId', 'externalId', 'order_id', 'parent_order_id', 'parentId', 'parent_id']
        for field in parent_id_fields:
            if field in row and row[field]:
                parent_order_id = str(row[field]).strip()
                if parent_order_id:
                    break
        if parent_order_id:
            result['refund_parent_order_ids'][order_id] = parent_order_id
        else:
            result['refund_parent_order_ids'][order_id] = 'N/A'


def parse_complyt_csv(file_path: str, order_id_header: str, date_from: str = None, date_to: str = None, exclude_states: Optional[List[str]] = None, usa_only: bool = False) -> Dict[str, Any]:
    """
    Parse Complyt CSV file and extract orders and refunds by transactionType.

    Note: Date filtering is not performed - it is the admin's responsibility to upload
    a CSV file that matches the selected date range.

    State filtering: Complyt CSV uses full state names in 'shippingAddress.state' column.
    The exclude_states parameter should contain full state names (e.g., 'Montana', 'Delaware').

    Country filtering: If usa_only is True, only orders with 'shippingAddress.country' == 'USA' are included.

    Args:
        file_path: Path to the Complyt CSV file
        order_id_header: Column name for order ID (e.g., 'externalId')
        date_from: Not used for filtering (kept for backward compatibility)
        date_to: Not used for filtering (kept for backward compatibility)
        exclude_states: List of full state names to exclude (e.g., ['Montana', 'Delaware', 'Oregon'])
        usa_only: If True, only include orders with shippingAddress.country == 'USA'

    Returns:
        Dictionary with:
        - 'invoices': list of order IDs (transactionType == 'INVOICE')
        - 'taxable_refunds': list of refund IDs (transactionType == 'TAXABLE_REFUND')
        - 'refunds': list of refund IDs (transactionType == 'REFUND')
        - 'invoice_amounts': dict mapping order_id -> amount
        - 'taxable_refund_amounts': dict mapping refund_id -> amount
        - 'refund_amounts': dict mapping refund_id -> amount
    """
    result = {
        'invoices': [],
        'taxable_refunds': [],
        'refunds': [],
        'invoice_amounts': {},
        'taxable_refund_amounts': {},
        'refund_amounts': {},
        'invoice_dates': {},
        'taxable_refund_dates': {},
        'refund_dates': {},
        'taxable_refund_parent_order_ids': {},
        'refund_parent_order_ids': {},
    }

    # Country filtering: Complyt CSV uses 'shippingAddress.country' column with value 'USA'
    country_filter_enabled = usa_only
    if country_filter_enabled:
        logger.info("Country filtering enabled: including only Complyt CSV orders with shippingAddress.country == 'USA'")
    else:
        logger.info("Country filtering disabled - all countries included")

    # State filtering: Complyt CSV uses full state names (e.g., "Montana", "Delaware")
    # The exclude_states parameter contains full state names directly
    state_filter_enabled = exclude_states and len(exclude_states) > 0
    excluded_state_names = set()
    if state_filter_enabled:
        # Normalize state names (strip whitespace, handle case-insensitive matching)
        for state_name in exclude_states:
            state_name_normalized = state_name.strip()
            if state_name_normalized:
                excluded_state_names.add(state_name_normalized.lower())  # Store lowercase for case-insensitive comparison
        if excluded_state_names:
            logger.info(f"State filtering enabled: excluding Complyt CSV orders from states: {', '.join(sorted(excluded_state_names))}")
        else:
            state_filter_enabled = False
    else:
        logger.info("State filtering disabled - all states included")

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            total_rows = 0
            filtered_rows = 0

            if state_filter_enabled:
                logger.info(f"State filtering enabled: excluding Complyt CSV orders from states: {', '.join(sorted(excluded_state_names))}")
            else:
                logger.info(f"State filtering disabled - all states included")

            # Try to find the country and state fields
            country_field_candidates = ['shippingAddress.country', 'shipping_address.country', 'country', 'shippingCountry', 'shipping_country']
            country_field = None
            state_field_candidates = ['shippingAddress.state', 'shipping_address.state', 'state', 'shippingState', 'shipping_state']
            state_field = None

            # Read first row to identify country and state fields if needed
            first_row = None
            csv_columns = None
            if country_filter_enabled or state_filter_enabled:
                try:
                    first_row = next(reader, None)
                    if first_row:
                        csv_columns = list(first_row.keys())
                        logger.info(f"Complyt CSV columns available: {csv_columns}")
                        # Log which date and parent order ID columns are found
                        date_fields = ['externalTimestamps.createdDate', 'externalTimestamps.created_date', 'transactionDate', 'date', 'createdAt', 'created_at', 'transaction_date', 'dateCreated', 'date_created', 'externalTimestamps.created', 'createdDate']
                        found_date_field = None
                        for field in date_fields:
                            if field in first_row:
                                found_date_field = field
                                logger.info(f"Found date field in CSV: '{found_date_field}'")
                                break
                        if not found_date_field:
                            logger.warning(f"No date field found in CSV. Tried: {date_fields}")
                            logger.warning(f"Available columns containing 'date' or 'timestamp': {[c for c in csv_columns if 'date' in c.lower() or 'timestamp' in c.lower()]}")

                        parent_id_fields = ['orderId', 'parentOrderId', 'externalId', 'order_id', 'parent_order_id', 'parentId', 'parent_id']
                        found_parent_id_field = None
                        for field in parent_id_fields:
                            if field in first_row:
                                found_parent_id_field = field
                                logger.info(f"Found parent order ID field in CSV: '{found_parent_id_field}'")
                                break
                        if not found_parent_id_field:
                            logger.warning(f"No parent order ID field found in CSV. Tried: {parent_id_fields}")
                        # Find country field
                        if country_filter_enabled:
                            for candidate in country_field_candidates:
                                if candidate in first_row:
                                    country_field = candidate
                                    logger.info(f"Found country field in CSV: '{country_field}'")
                                    break

                            if not country_field:
                                logger.warning(f"Country filtering requested but no country field found. Tried: {country_field_candidates}")
                                logger.warning(f"Available CSV columns: {list(first_row.keys())}")
                                country_filter_enabled = False

                        # Find state field
                        if state_filter_enabled:
                            for candidate in state_field_candidates:
                                if candidate in first_row:
                                    state_field = candidate
                                    logger.info(f"Found state field in CSV: '{state_field}'")
                                    break

                            if not state_field:
                                logger.warning(f"State filtering requested but no state field found. Tried: {state_field_candidates}")
                                logger.warning(f"Available CSV columns: {list(first_row.keys())}")
                                state_filter_enabled = False
                except StopIteration:
                    first_row = None

            # Process first row if we read it
            if first_row:
                total_rows += 1
                row = first_row

                # Apply country filtering if enabled
                if country_filter_enabled and country_field:
                    shipping_country = row.get(country_field, '').strip()
                    # Check if country is 'USA' (case-insensitive)
                    if not shipping_country or shipping_country.upper() != 'USA':
                        filtered_rows += 1
                        row = None

                # Apply state filtering if enabled
                if row and state_filter_enabled and state_field:
                    shipping_state = row.get(state_field, '').strip()
                    # Case-insensitive comparison
                    if shipping_state and shipping_state.lower() in excluded_state_names:
                        filtered_rows += 1
                        row = None

                # Process first row if it passed all filters
                if row:
                    _process_complyt_row(row, order_id_header, result)

            # Process remaining rows
            skipped_by_country = 0
            skipped_by_state = 0
            skipped_no_order_id = 0
            for row in reader:
                total_rows += 1

                # Apply country filtering if enabled
                if country_filter_enabled and country_field:
                    shipping_country = row.get(country_field, '').strip()
                    # Check if country is 'USA' (case-insensitive)
                    if not shipping_country or shipping_country.upper() != 'USA':
                        filtered_rows += 1
                        skipped_by_country += 1
                        continue

                # Apply state filtering if enabled
                if state_filter_enabled and state_field:
                    shipping_state = row.get(state_field, '').strip()
                    # Case-insensitive comparison
                    if shipping_state and shipping_state.lower() in excluded_state_names:
                        filtered_rows += 1
                        skipped_by_state += 1
                        continue

                # Check if order ID exists before processing
                order_id = str(row.get(order_id_header, '')).strip()
                if not order_id:
                    skipped_no_order_id += 1
                    logger.debug(f"Skipping row with no order ID in column '{order_id_header}'")
                    continue

                _process_complyt_row(row, order_id_header, result)

            # Log detailed filtering statistics
            if country_filter_enabled or state_filter_enabled:
                logger.info(f"Filtering breakdown: {skipped_by_country} skipped by country, {skipped_by_state} skipped by state, {skipped_no_order_id} skipped (no order ID)")

            if country_filter_enabled or state_filter_enabled:
                filter_reasons = []
                if country_filter_enabled:
                    filter_reasons.append("country")
                if state_filter_enabled:
                    filter_reasons.append("state")
                logger.info(f"Parsed Complyt CSV: {total_rows} total rows, {filtered_rows} filtered out by {', '.join(filter_reasons)}, {total_rows - filtered_rows} included")
            else:
                logger.info(f"Parsed Complyt CSV: {total_rows} total rows processed (all rows included)")
            logger.info(f"  - Invoices: {len(result['invoices'])}")
            logger.info(f"  - Taxable refunds: {len(result['taxable_refunds'])}")
            logger.info(f"  - Refunds: {len(result['refunds'])}")

            # Log sample of extracted order IDs for debugging
            if result['invoices']:
                sample_ids = sorted(result['invoices'], key=lambda x: int(x) if x.isdigit() else 0)[:10]
                logger.info(f"  - Sample invoice order IDs: {', '.join(sample_ids)}")
                logger.debug(f"  - All invoice order IDs: {sorted(result['invoices'], key=lambda x: int(x) if x.isdigit() else 0)}")

    except Exception as e:
        logger.error(f"Error parsing Complyt CSV: {str(e)}", exc_info=True)
        raise

    return result


def fetch_woocommerce_orders(
    date_from: str,
    date_to: str,
    woo_client: WooCommerceClient,
    job_id: int = None,
    db: Session = None,
    usa_only: bool = True,
    exclude_states: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Fetch WooCommerce orders and refunds for the given date range.

    Returns:
        Dictionary with:
        - 'orders': dict mapping order_id -> order_data
        - 'refunds': dict mapping refund_id -> refund_data
        - 'order_amounts': dict mapping order_id -> amount
        - 'refund_amounts': dict mapping refund_id -> amount
    """
    result = {
        'orders': {},
        'refunds': {},
        'order_amounts': {},
        'refund_amounts': {},
    }

    try:
        # Fetch orders from custom PFM Tools endpoint
        # Custom endpoint uses date_after/date_before parameters with SPACE format
        # Format: YYYY-MM-DD HH:MM:SS (e.g., 2025-10-01 00:00:00)
        # Dates are interpreted in UTC timezone (matches Complyt CSV timezone)
        api_base = f"{woo_client.base_url}/wp-json/pfm-tools/v1"

        # Format dates with SPACE (not T) - this is critical for date filtering to work
        # IMPORTANT: The PHP plugin interprets these dates in America/New_York timezone to match Metorik
        # Metorik displays orders in America/New_York timezone (EDT = UTC-4 in summer, EST = UTC-5 in winter)
        # Example: Order 3312544 shows as "Oct 1, 2025 12:05 AM" in Metorik = "Oct 1, 2025 04:05:27 UTC" in WooCommerce
        # The plugin converts America/New_York dates to UTC timestamps for WooCommerce filtering
        #
        # We send dates in America/New_York timezone format (YYYY-MM-DD HH:MM:SS)
        # The plugin interprets these as America/New_York and converts to UTC for WooCommerce queries
        # For date_to, we use the end of the day (23:59:59) to ensure we include the entire day
        from datetime import datetime

        # Parse the date_from and date_to strings
        date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
        date_to_dt = datetime.strptime(date_to, '%Y-%m-%d')

        # Format dates for America/New_York timezone (Metorik timezone)
        # Start of day: 00:00:00
        after_date = date_from_dt.strftime('%Y-%m-%d 00:00:00')
        # End of day: 23:59:59
        before_date = date_to_dt.strftime('%Y-%m-%d 23:59:59')

        logger.info(f"Fetching WooCommerce orders:")
        logger.info(f"  User selected date range: {date_from} to {date_to}")
        logger.info(f"  Date range (America/New_York): {after_date} to {before_date}")
        logger.info(f"  Plugin will convert these to UTC timestamps for WooCommerce filtering")

        # Verify API keys are set
        if not woo_client.consumer_key or not woo_client.consumer_secret:
            raise ValueError("WooCommerce consumer_key and consumer_secret must be set in environment variables")

        # Fetch orders from custom endpoint
        orders_url = f"{api_base}/orders"
        params = {
            'date_after': after_date,
            'date_before': before_date,
            'per_page': 300,  # Increased to 300 to maximize performance. Monitor PHP memory if issues occur.
            'page': 1,
        }


        # Add filtering parameters
        if usa_only:
            params['country'] = 'US'
        if exclude_states and len(exclude_states) > 0:
            params['exclude_states'] = ','.join(exclude_states)

        # Create a separate session for custom endpoint with explicit Authorization header
        # The custom endpoint uses hardcoded credentials check, so we need to send Basic Auth
        import base64
        import requests
        auth_string = f"{woo_client.consumer_key}:{woo_client.consumer_secret}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')

        # Create a new session for custom endpoint (without session.auth to avoid conflicts)
        # Use X-PFM-Authorization instead of Authorization to avoid WordPress core
        # intercepting the standard Basic Auth header on WP Engine hosting.
        custom_session = requests.Session()
        custom_session.headers.update({
            'Accept': '*/*',
            'User-Agent': 'curl/7.68.0',
            'Accept-Encoding': 'gzip, deflate',
            'X-PFM-Authorization': f'Basic {auth_b64}'
        })
        logger.info(f"Created custom session for PFM Tools endpoint with explicit X-PFM-Authorization header")
        logger.debug(f"X-PFM-Authorization header (first 30 chars): Basic {auth_b64[:30]}...")

        all_orders = []
        all_order_ids = []
        page_num = 1
        total_pages = None
        fetch_start_time = time.time()

        logger.info(f"Starting to fetch orders from URL: {orders_url}")
        logger.info(f"Request parameters: {params}")

        # Helper function to update progress if job_id and db are provided
        def update_progress(progress, message):
            if job_id and db:
                try:
                    job = db.query(Job).filter(Job.id == job_id).first()
                    if job:
                        new_options = dict(job.options) if job.options else {}
                        new_options['progress'] = progress
                        new_options['status_message'] = message
                        job.options = new_options
                        db.commit()
                        logger.debug(f"Progress updated: {progress}% - {message}")
                except Exception as e:
                    logger.warning(f"Failed to update progress: {str(e)}")

        while True:
            logger.info(f"=== Fetching page {page_num} ===")

            try:
                request_start_time = time.time()
                full_url = f"{orders_url}?date_after={params['date_after']}&date_before={params['date_before']}&per_page={params['per_page']}&page={params['page']}"

                # Use custom session for PFM Tools endpoint
                response = custom_session.get(orders_url, params=params, timeout=30)

                request_end_time = time.time()
                request_duration = request_end_time - request_start_time

                # Extract total pages from response headers
                if 'X-WP-TotalPages' in response.headers:
                    total_pages = int(response.headers['X-WP-TotalPages'])
                    logger.debug(f"Total pages available: {total_pages}")

                if response.status_code != 200:
                    logger.error(f"=== AUTHENTICATION ERROR ===")
                    logger.error(f"Status code: {response.status_code}")
                    logger.error(f"Request URL: {response.request.url}")
                    logger.error(f"Request method: {response.request.method}")

                    # Log request headers (mask auth)
                    req_headers = dict(response.request.headers)
                    if 'Authorization' in req_headers:
                        auth_val = req_headers['Authorization']
                        if auth_val.startswith('Basic '):
                            # Show first 30 chars to verify it's being sent
                            logger.error(f"Authorization header present: {auth_val[:30]}...")
                            req_headers['Authorization'] = f"Basic {auth_val[6:30]}..."  # Mask
                    else:
                        logger.error("WARNING: Authorization header NOT found in request!")
                    logger.error(f"All request headers: {req_headers}")

                    # Log full response for debugging
                    logger.error(f"Response headers: {dict(response.headers)}")
                    logger.error(f"Response text (first 1000 chars): {response.text[:1000]}")
                    logger.error(f"=== END AUTHENTICATION ERROR ===")
                    response.raise_for_status()

                orders = response.json()

                # Update progress during pagination (5-95% range)
                # WooCommerce fetching takes 90-95% of total time, so progress should reflect that
                if total_pages and job_id and db:
                    pagination_progress = 5 + int((page_num / total_pages) * 90)  # 5-95%
                    update_progress(pagination_progress, f'Fetching WooCommerce orders... Page {page_num}/{total_pages} ({len(all_orders)} orders)')

                if not orders:
                    logger.info(f"No orders returned for page {page_num}, stopping pagination")
                    break

                all_orders.extend(orders)
                logger.info(f"Total orders collected so far: {len(all_orders)}")

                # Collect order IDs for logging
                page_order_ids = [str(order.get('id', '')) for order in orders if order.get('id')]
                all_order_ids.extend(page_order_ids)
                logger.debug(f"Page {page_num}: Fetched {len(orders)} orders")

                # Check if there are more pages
                if len(orders) < params['per_page']:
                    logger.info(f"Received {len(orders)} orders (less than per_page {params['per_page']}), this is the last page")
                    break

                page_num += 1
                params['page'] = page_num
                logger.debug(f"More pages available, continuing to page {page_num}")

            except Exception as e:
                logger.error(f"Error fetching page {page_num}: {str(e)}", exc_info=True)
                raise

        fetch_end_time = time.time()
        total_fetch_duration = fetch_end_time - fetch_start_time
        logger.info(f"Fetched {len(all_orders)} orders in {total_fetch_duration:.3f} seconds ({page_num} pages)")

        fetched_order_ids = [str(o.get('id')) for o in all_orders]

        # Apply filtering after fetching all orders
        logger.info(f"Applying filters: usa_only={usa_only}, exclude_states={exclude_states}")
        if usa_only or (exclude_states and len(exclude_states) > 0):
            original_count = len(all_orders)
            filtered_orders = []
            excluded_by_country = 0
            excluded_by_state = 0

            # Sample first order to check if shipping fields are present
            if len(all_orders) > 0:
                sample_order = all_orders[0]
                logger.info(f"Sample order fields: {list(sample_order.keys())}")
                logger.info(f"Sample order {sample_order.get('id')}: shipping_country='{sample_order.get('shipping_country', 'MISSING')}', shipping_state='{sample_order.get('shipping_state', 'MISSING')}'")

                # Warn if shipping fields are missing
                if 'shipping_country' not in sample_order or 'shipping_state' not in sample_order:
                    logger.warning("WARNING: shipping_country or shipping_state not found in order response. Plugin may need update.")

            for order in all_orders:
                # Get shipping country and state from order data (shipping address determines tax jurisdiction)
                shipping_country = order.get('shipping_country', '')
                shipping_state = order.get('shipping_state', '')

                # Filter by country
                if usa_only:
                    if not shipping_country or shipping_country.upper() != 'US':
                        excluded_by_country += 1
                        if excluded_by_country <= 5:  # Log first 5 exclusions
                            logger.info(f"Excluding order {order.get('id')}: shipping_country='{shipping_country}' (not US)")
                        continue

                # Exclude states
                if exclude_states and len(exclude_states) > 0:
                    if shipping_state and shipping_state.upper() in [s.upper() for s in exclude_states]:
                        excluded_by_state += 1
                        if excluded_by_state <= 5:  # Log first 5 exclusions
                            logger.info(f"Excluding order {order.get('id')}: shipping_state='{shipping_state}' (in exclude list)")
                        continue

                filtered_orders.append(order)

            all_orders = filtered_orders


            logger.info(f"Filtered orders: {original_count} -> {len(all_orders)} (removed {original_count - len(all_orders)})")
            if usa_only:
                logger.info(f"  - USA only filter: enabled (excluded {excluded_by_country} non-US orders)")
            if exclude_states:
                logger.info(f"  - Excluded states: {', '.join(exclude_states)} (excluded {excluded_by_state} orders)")
        else:
            logger.info("No filtering applied (usa_only=False and no exclude_states)")

        processing_start_time = time.time()

        # Update progress to processing phase (95%)
        # Processing is very fast, so it's near the end
        update_progress(95, f'Processing {len(all_orders)} orders...')

        # Process orders and extract refunds from order response
        # Note: Refunds are now included directly in the orders response from the API
        # This eliminates the need for separate API calls, making it much faster
        processed_count = 0
        total_orders = len(all_orders)
        total_refunds_found = 0
        orders_with_refunds_count = 0
        processing_start_time = time.time()

        for order in all_orders:
            processed_count += 1
            if processed_count % 100 == 0:
                logger.info(f"Processing order {processed_count}/{total_orders}...")
                # Update progress during processing (95-98% range)
                # Processing is very fast, so it's near the end
                if job_id and db:
                    processing_progress = 95 + int((processed_count / total_orders) * 3)  # 95-98%
                    update_progress(processing_progress, f'Processing orders... {processed_count}/{total_orders} ({total_refunds_found} refunds)')

            # Get order ID - plugin should return 'id' field, but handle None case
            order_id_raw = order.get('id')
            if order_id_raw is None:
                # Plugin might not have 'id' field yet (needs update), try to get from order data
                # Check if there's an index or other identifier
                logger.warning(f"Order missing 'id' field: {list(order.keys())[:10]}")
                # Skip orders without ID - they can't be matched
                continue

            order_id = str(order_id_raw).strip()
            if not order_id or order_id == 'None':
                logger.warning(f"Skipping order with invalid ID: {order_id_raw}, order keys: {list(order.keys())[:10]}")
                continue

            status = order.get('status', '')
            total = float(order.get('total', '0') or '0')

            logger.debug(f"Processing order {order_id}: status={status}, total={total}")

            # Include ALL orders in the comparison, including refunded ones
            # Refunded orders are still orders that exist in WooCommerce and should be compared
            # Previously we were filtering them out, which caused them to appear in
            # "Orders in Complyt but not in WooCommerce" even though they exist in WooCommerce
            result['orders'][order_id] = order
            result['order_amounts'][order_id] = total
            logger.debug(f"Added order {order_id} to orders list (status: {status})")

            # Extract refunds from order response (refunds are now included in the API response)
            # The API includes a 'refunds' array in each order object
            refunds = order.get('refunds', [])
            has_refunds_flag = order.get('has_refunds', False)

            if has_refunds_flag and not refunds:
                logger.warning(f"Order {order_id} has has_refunds=True but no refunds in response - plugin may need update")

            if refunds:
                orders_with_refunds_count += 1
                logger.debug(f"Order {order_id} has {len(refunds)} refund(s) in response")
                for refund in refunds:
                    # Get refund ID - plugin now includes 'id' field
                    refund_id = str(refund.get('id', ''))
                    if not refund_id:
                        # Fallback: if no ID, skip this refund (shouldn't happen with updated plugin)
                        logger.warning(f"Refund missing ID in order {order_id}, skipping")
                        continue

                    # Custom endpoint uses 'amount' field instead of 'total'
                    refund_amount = float(refund.get('amount', '0') or '0')

                    # Get parent order ID - plugin now includes 'order_id' field, but keep fallback
                    parent_order_id = refund.get('order_id', order_id)
                    refund['order_id'] = parent_order_id  # Ensure order_id is stored

                    result['refunds'][refund_id] = refund
                    result['refund_amounts'][refund_id] = abs(refund_amount)
                    total_refunds_found += 1
                    logger.debug(f"Added refund {refund_id} for order {parent_order_id}, amount: {abs(refund_amount)}")

        processing_end_time = time.time()
        total_processing_duration = processing_end_time - processing_start_time

        logger.info(f"[TIMING SUMMARY] Total processing time: {total_processing_duration:.3f} seconds")
        logger.info(f"[TIMING SUMMARY] No additional API calls needed - refunds included in orders response")
        logger.info(f"Processed {processed_count} orders, found {orders_with_refunds_count} orders with refunds ({total_refunds_found} total refunds)")

        logger.info(f"Processed {len(result['orders'])} orders and {len(result['refunds'])} refunds")

    except Exception as e:
        logger.error(f"Error fetching WooCommerce orders: {str(e)}", exc_info=True)
        raise

    return result


def generate_comparison_report(
    complyt_data: Dict[str, Any],
    woo_data: Dict[str, Any]
) -> str:
    """
    Generate a text report comparing Complyt and WooCommerce data.
    """
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("ORDER COMPARISON REPORT")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Counts
    complyt_order_count = len(complyt_data['invoices'])
    complyt_taxable_refund_count = len(complyt_data['taxable_refunds'])
    complyt_refund_count = len(complyt_data['refunds'])
    complyt_total_refund_count = complyt_taxable_refund_count + complyt_refund_count

    woo_order_count = len(woo_data['orders'])
    woo_refund_count = len(woo_data['refunds'])

    report_lines.append("COUNTS:")
    report_lines.append(f"Complyt orders: {complyt_order_count}")
    report_lines.append(f"Complyt TAXABLE REFUNDs: {complyt_taxable_refund_count}")
    report_lines.append(f"Complyt REFUNDs: {complyt_refund_count}")
    report_lines.append(f"Complyt total refunds: {complyt_total_refund_count}")
    report_lines.append(f"WooCommerce orders: {woo_order_count}")
    report_lines.append(f"WooCommerce refunds: {woo_refund_count}")
    report_lines.append("")

    # Find differences
    # Normalize order IDs to strings for consistent comparison
    complyt_order_ids = set(str(oid).strip() for oid in complyt_data['invoices'])
    woo_order_ids = set(str(oid).strip() for oid in woo_data['orders'].keys())

    complyt_refund_ids = set(str(oid).strip() for oid in complyt_data['taxable_refunds'] + complyt_data['refunds'])
    woo_refund_ids = set(str(oid).strip() for oid in woo_data['refunds'].keys())

    # Check if any refund IDs are incorrectly in the orders dictionary and remove them
    refund_ids_in_orders = woo_order_ids & woo_refund_ids
    if refund_ids_in_orders:
        woo_order_ids = woo_order_ids - refund_ids_in_orders

    # Orders in Complyt but not in WooCommerce
    orders_in_complyt_not_woo = sorted(complyt_order_ids - woo_order_ids, key=lambda x: int(x) if x.isdigit() else 0)

    # Orders in WooCommerce but not in Complyt
    orders_in_woo_not_complyt = sorted(woo_order_ids - complyt_order_ids, key=lambda x: int(x) if x.isdigit() else 0)

    # Refunds in Complyt but not in WooCommerce
    refunds_in_complyt_not_woo = sorted(complyt_refund_ids - woo_refund_ids, key=lambda x: int(x) if x.isdigit() else 0)

    # Refunds in WooCommerce but not in Complyt
    refunds_in_woo_not_complyt = sorted(woo_refund_ids - complyt_refund_ids, key=lambda x: int(x) if x.isdigit() else 0)

    report_lines.append("DIFFERENCES:")
    report_lines.append("")

    report_lines.append("orders ids that are in complyt but not in woo:")
    if orders_in_complyt_not_woo:
        report_lines.append(f"  {', '.join(orders_in_complyt_not_woo)}")
    else:
        report_lines.append("  None")
    report_lines.append("")

    report_lines.append("orders ids that are in woo but not in complyt:")
    if orders_in_woo_not_complyt:
        report_lines.append(f"  {', '.join(orders_in_woo_not_complyt)}")
    else:
        report_lines.append("  None")
    report_lines.append("")

    report_lines.append("REFUNDs ids that are in complyt but not in woo:")
    if refunds_in_complyt_not_woo:
        report_lines.append(f"  {', '.join(refunds_in_complyt_not_woo)}")
    else:
        report_lines.append("  None")
    report_lines.append("")

    report_lines.append("REFUNDs ids that are in woo but not in complyt:")
    if refunds_in_woo_not_complyt:
        report_lines.append(f"  {', '.join(refunds_in_woo_not_complyt)}")
    else:
        report_lines.append("  None")
    report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("=" * 80)

    return "\n".join(report_lines)


def generate_comparison_report_pdf(
    complyt_data: Dict[str, Any],
    woo_data: Dict[str, Any],
    output_path: str,
    date_from: str = None,
    date_to: str = None
) -> str:
    """
    Generate a PDF report comparing Complyt and WooCommerce data.

    Returns:
        Path to the generated PDF file
    """
    # Create PDF document
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    story = []

    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )

    # Style for section titles (like "Orders in Complyt but not in WooCommerce")
    section_title_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Normal'],
        fontSize=13,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=8,
        spaceBefore=12,
        fontName='Helvetica-Bold',
        leading=16
    )

    normal_style = styles['Normal']
    normal_style.fontSize = 10
    normal_style.leading = 14

    # Title
    title = Paragraph("ORDER COMPARISON REPORT", title_style)
    story.append(title)
    story.append(Spacer(1, 0.2*inch))

    # Date range info
    if date_from and date_to:
        date_info = Paragraph(f"<b>Date Range:</b> {date_from} to {date_to}", normal_style)
        story.append(date_info)
        story.append(Spacer(1, 0.1*inch))

    report_date = Paragraph(
        f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        normal_style
    )
    story.append(report_date)
    story.append(Spacer(1, 0.3*inch))

    # Counts section
    complyt_order_count = len(complyt_data['invoices'])
    complyt_taxable_refund_count = len(complyt_data['taxable_refunds'])
    complyt_refund_count = len(complyt_data['refunds'])
    complyt_total_refund_count = complyt_taxable_refund_count + complyt_refund_count

    woo_order_count = len(woo_data['orders'])
    woo_refund_count = len(woo_data['refunds'])

    counts_heading = Paragraph("COUNTS", heading_style)
    story.append(counts_heading)

    # Create counts table
    counts_data = [
        ['Source', 'Orders', 'Taxable Refunds', 'Refunds', 'Total Refunds'],
        [
            'Complyt',
            str(complyt_order_count),
            str(complyt_taxable_refund_count),
            str(complyt_refund_count),
            str(complyt_total_refund_count)
        ],
        [
            'WooCommerce',
            str(woo_order_count),
            '-',
            str(woo_refund_count),
            str(woo_refund_count)
        ]
    ]

    counts_table = Table(counts_data, colWidths=[2*inch, 1*inch, 1.2*inch, 1*inch, 1.2*inch])
    counts_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
    ]))

    story.append(counts_table)
    story.append(Spacer(1, 0.4*inch))

    # Differences section
    differences_heading = Paragraph("DIFFERENCES", heading_style)
    story.append(differences_heading)

    # Find differences
    # Normalize order IDs to strings for consistent comparison
    complyt_order_ids = set(str(oid).strip() for oid in complyt_data['invoices'])
    woo_order_ids = set(str(oid).strip() for oid in woo_data['orders'].keys())

    complyt_refund_ids = set(complyt_data['taxable_refunds'] + complyt_data['refunds'])
    woo_refund_ids = set(woo_data['refunds'].keys())

    # Check if any refund IDs are incorrectly in the orders dictionary and remove them
    refund_ids_in_orders = woo_order_ids & woo_refund_ids
    if refund_ids_in_orders:
        woo_order_ids = woo_order_ids - refund_ids_in_orders

    orders_in_complyt_not_woo = sorted(complyt_order_ids - woo_order_ids, key=lambda x: int(x) if x.isdigit() else 0)
    orders_in_woo_not_complyt = sorted(woo_order_ids - complyt_order_ids, key=lambda x: int(x) if x.isdigit() else 0)
    refunds_in_complyt_not_woo = sorted(complyt_refund_ids - woo_refund_ids, key=lambda x: int(x) if x.isdigit() else 0)
    refunds_in_woo_not_complyt = sorted(woo_refund_ids - complyt_refund_ids, key=lambda x: int(x) if x.isdigit() else 0)

    # Orders in Complyt but not in WooCommerce
    if orders_in_complyt_not_woo:
        story.append(Paragraph(
            f"Orders in Complyt but not in WooCommerce ({len(orders_in_complyt_not_woo)}):",
            section_title_style
        ))
        # Split into chunks for better formatting
        chunk_size = 10
        for i in range(0, len(orders_in_complyt_not_woo), chunk_size):
            chunk = orders_in_complyt_not_woo[i:i+chunk_size]
            ids_text = ', '.join(chunk)
            story.append(Paragraph(f"  {ids_text}", normal_style))
        story.append(Spacer(1, 0.15*inch))
    else:
        story.append(Paragraph(
            "Orders in Complyt but not in WooCommerce: None",
            section_title_style
        ))
        story.append(Spacer(1, 0.15*inch))

    # Orders in WooCommerce but not in Complyt
    if orders_in_woo_not_complyt:
        story.append(Paragraph(
            f"Orders in WooCommerce but not in Complyt ({len(orders_in_woo_not_complyt)}):",
            section_title_style
        ))
        chunk_size = 10
        for i in range(0, len(orders_in_woo_not_complyt), chunk_size):
            chunk = orders_in_woo_not_complyt[i:i+chunk_size]
            ids_text = ', '.join(chunk)
            story.append(Paragraph(f"  {ids_text}", normal_style))
        story.append(Spacer(1, 0.15*inch))
    else:
        story.append(Paragraph(
            "Orders in WooCommerce but not in Complyt: None",
            section_title_style
        ))
        story.append(Spacer(1, 0.15*inch))

    # Refunds in Complyt but not in WooCommerce
    if refunds_in_complyt_not_woo:
        story.append(Paragraph(
            f"Refunds in Complyt but not in WooCommerce ({len(refunds_in_complyt_not_woo)}):",
            section_title_style
        ))
        # Create table with Refund ID (Complyt doesn't have order IDs for refunds)
        refund_table_data = [['Refund ID']]
        for refund_id in refunds_in_complyt_not_woo:
            refund_table_data.append([refund_id])

        refund_table = Table(refund_table_data, colWidths=[2*inch])
        refund_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))
        story.append(refund_table)
        story.append(Spacer(1, 0.15*inch))
    else:
        story.append(Paragraph(
            "Refunds in Complyt but not in WooCommerce: None",
            section_title_style
        ))
        story.append(Spacer(1, 0.15*inch))

    # Refunds in WooCommerce but not in Complyt
    if refunds_in_woo_not_complyt:
        story.append(Paragraph(
            f"Refunds in WooCommerce but not in Complyt ({len(refunds_in_woo_not_complyt)}):",
            section_title_style
        ))
        # Create table with Refund ID and Order ID columns
        refund_table_data = [['Refund ID', 'Order ID']]
        for refund_id in refunds_in_woo_not_complyt:
            # Get order ID from refund data
            refund_data = woo_data['refunds'].get(refund_id, {})
            order_id = str(refund_data.get('order_id', 'N/A'))
            refund_table_data.append([refund_id, order_id])

        refund_table = Table(refund_table_data, colWidths=[1.5*inch, 1.5*inch])
        refund_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))
        story.append(refund_table)
        story.append(Spacer(1, 0.15*inch))
    else:
        story.append(Paragraph(
            "Refunds in WooCommerce but not in Complyt: None",
            section_title_style
        ))
        story.append(Spacer(1, 0.15*inch))

    # Build PDF
    try:
        doc.build(story)
        logger.info(f"PDF successfully generated at: {output_path}")
    except Exception as e:
        logger.error(f"Error building PDF: {str(e)}", exc_info=True)
        raise

    return output_path


def generate_comparison_report_csvs(
    complyt_data: Dict[str, Any],
    woo_data: Dict[str, Any],
    output_dir: str,
    date_from: str = None,
    date_to: str = None
) -> List[str]:
    """
    Generate CSV reports comparing Complyt and WooCommerce data.
    Creates multiple CSV files for different sections of the comparison.

    Returns:
        List of paths to generated CSV files
    """
    csv_files = []

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Find differences
    # Normalize order IDs to strings for consistent comparison
    complyt_order_ids = set(str(oid).strip() for oid in complyt_data['invoices'])

    # Filter WooCommerce orders by the original date range (not the expanded range used for fetching)
    # This prevents false positives in "orders in WooCommerce but not in Complyt" report
    # We fetch with expanded range to ensure we don't miss matches, but filter for comparison
    # IMPORTANT: Plugin returns date_created in local timezone, but we need to compare in UTC
    # to match Complyt CSV dates (which are in UTC)
    woo_order_ids_filtered = set()
    if date_from and date_to:
        # Parse dates for filtering (user-selected dates are interpreted as UTC, matching Complyt CSV)
        date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
        date_to_dt = datetime.strptime(date_to, '%Y-%m-%d')
        # Use start of date_from and end of date_to (inclusive) in UTC
        filter_start = pytz.UTC.localize(date_from_dt.replace(hour=0, minute=0, second=0))
        filter_end = pytz.UTC.localize(date_to_dt.replace(hour=23, minute=59, second=59))

        logger.info(f"Filtering WooCommerce orders by original date range: {date_from} to {date_to} (UTC)")
        filtered_count = 0
        for order_id, order in woo_data['orders'].items():
            # Always use date_created_gmt (UTC) for filtering - this is the correct UTC date
            order_date_str = order.get('date_created_gmt')
            if not order_date_str:
                # Fallback to date_created if date_created_gmt is not available (shouldn't happen with updated plugin)
                order_date_str = order.get('date_created', '')
                logger.warning(f"Order {order_id} missing date_created_gmt, using date_created: {order_date_str}")

            if order_date_str:
                try:
                    # Parse order date (format: "2025-10-31 19:00:03" or "2025-10-31T19:00:03")
                    if 'T' in order_date_str:
                        order_date_naive = datetime.strptime(order_date_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
                    else:
                        order_date_naive = datetime.strptime(order_date_str.split('.')[0], '%Y-%m-%d %H:%M:%S')

                    # date_created_gmt is already UTC, so localize it as UTC
                    order_date_utc = pytz.UTC.localize(order_date_naive)

                    # Check if order date falls within the original date range (UTC comparison)
                    if filter_start <= order_date_utc <= filter_end:
                        woo_order_ids_filtered.add(str(order_id).strip())
                    else:
                        filtered_count += 1
                        # Log first few filtered orders for debugging
                        if filtered_count <= 5:
                            logger.debug(f"Filtered out order {order_id}: date_created_gmt={order_date_str} (UTC) is outside range {date_from} to {date_to}")
                except (ValueError, AttributeError) as e:
                    # If date parsing fails, include the order (better to have false positives than miss matches)
                    logger.warning(f"Could not parse date for order {order_id}: {order_date_str}, including in comparison")
                    woo_order_ids_filtered.add(str(order_id).strip())
            else:
                # If no date, include the order (better to have false positives than miss matches)
                woo_order_ids_filtered.add(str(order_id).strip())

        logger.info(f"Filtered out {filtered_count} WooCommerce orders outside original date range")
        logger.info(f"WooCommerce orders within date range: {len(woo_order_ids_filtered)}")
    else:
        # No date filtering - use all orders
        woo_order_ids_filtered = set(str(oid).strip() for oid in woo_data['orders'].keys())

    woo_order_ids = woo_order_ids_filtered

    complyt_refund_ids = set(str(oid).strip() for oid in complyt_data['taxable_refunds'] + complyt_data['refunds'])
    woo_refund_ids = set(str(oid).strip() for oid in woo_data['refunds'].keys())

    # Log summary statistics
    logger.info(f"Order comparison: Complyt={len(complyt_order_ids)}, WooCommerce={len(woo_order_ids)}")

    # Check for ID format mismatches
    sample_complyt_ids = sorted(list(complyt_order_ids), key=lambda x: int(x) if x.isdigit() else 0)[:5]
    for sample_id in sample_complyt_ids:
        # Check if this ID exists in WooCommerce with different formatting
        found_match = False
        for woo_id in woo_order_ids:
            if str(sample_id).strip() == str(woo_id).strip():
                found_match = True
                logger.debug(f"Order ID {sample_id} matches WooCommerce ID {woo_id} (exact match)")
                break
            # Check if they're the same when converted to int (handles leading zeros)
            try:
                if int(sample_id) == int(woo_id):
                    logger.warning(f"Order ID {sample_id} matches WooCommerce ID {woo_id} (numeric match, format differs)")
                    found_match = True
                    break
            except ValueError:
                pass

        if not found_match and sample_id in complyt_order_ids:
            logger.warning(f"Order ID {sample_id} from Complyt NOT found in WooCommerce order IDs")
            # Try to find this order in WooCommerce by querying
            logger.warning(f"  Checking if order {sample_id} exists in WooCommerce data...")
            if sample_id in woo_data['orders']:
                logger.error(f"  ERROR: Order {sample_id} EXISTS in woo_data['orders'] but not in woo_order_ids set!")
                logger.error(f"    Order data: {woo_data['orders'][sample_id]}")
            else:
                logger.warning(f"  Order {sample_id} not found in woo_data['orders'] dictionary")

    # Check if any refund IDs are incorrectly in the orders dictionary and remove them
    refund_ids_in_orders = woo_order_ids & woo_refund_ids
    if refund_ids_in_orders:
        logger.warning(f"Found {len(refund_ids_in_orders)} refund IDs incorrectly in orders dictionary: {list(refund_ids_in_orders)[:10]}")
        woo_order_ids = woo_order_ids - refund_ids_in_orders

    orders_in_complyt_not_woo = sorted(complyt_order_ids - woo_order_ids, key=lambda x: int(x) if x.isdigit() else 0)
    orders_in_woo_not_complyt = sorted(woo_order_ids - complyt_order_ids, key=lambda x: int(x) if x.isdigit() else 0)

    logger.info(f"Orders in Complyt but not in WooCommerce: {len(orders_in_complyt_not_woo)}")
    if orders_in_complyt_not_woo:
        logger.warning(f"  Sample order IDs: {orders_in_complyt_not_woo[:20]}")
        # For each missing order, check if it exists in WooCommerce with different formatting
        for missing_id in orders_in_complyt_not_woo[:10]:
            logger.warning(f"  Checking order {missing_id}:")
            # Check if it exists in woo_data['orders'] dictionary
            if missing_id in woo_data['orders']:
                logger.error(f"    ERROR: Order {missing_id} EXISTS in woo_data['orders'] but was excluded from comparison!")
                order_data = woo_data['orders'][missing_id]
                logger.error(f"    Order data: id={order_data.get('id')}, status={order_data.get('status')}, date_created={order_data.get('date_created')}")
            else:
                # Check all WooCommerce orders for potential matches
                for woo_id, woo_order in list(woo_data['orders'].items())[:100]:  # Check first 100
                    try:
                        if int(str(missing_id).strip()) == int(str(woo_id).strip()):
                            logger.warning(f"    Found potential match: WooCommerce has order ID {woo_id} (numeric match with {missing_id})")
                            logger.warning(f"      Order data: status={woo_order.get('status')}, date_created={woo_order.get('date_created')}")
                    except ValueError:
                        pass
    # Log some examples of orders in WooCommerce but not in Complyt
    if orders_in_woo_not_complyt:
        sample_missing = orders_in_woo_not_complyt[:10]
        logger.warning(f"Found {len(orders_in_woo_not_complyt)} orders in WooCommerce but not in Complyt invoices")
        logger.warning(f"  Sample order IDs: {', '.join(sample_missing)}")
        logger.warning(f"  These orders may be in Complyt CSV but:")
        logger.warning(f"    - Have different transactionType (not 'INVOICE')")
        logger.warning(f"    - Were filtered out by country/state filters")
        logger.warning(f"    - Have order ID column name mismatch")
        logger.warning(f"    - Have order ID format differences (whitespace, leading zeros, etc.)")
    refunds_in_complyt_not_woo = sorted(complyt_refund_ids - woo_refund_ids, key=lambda x: int(x) if x.isdigit() else 0)
    refunds_in_woo_not_complyt = sorted(woo_refund_ids - complyt_refund_ids, key=lambda x: int(x) if x.isdigit() else 0)

    # 1. Summary CSV
    summary_path = os.path.join(output_dir, "summary.csv")
    with open(summary_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Metric', 'Complyt', 'WooCommerce'])
        writer.writerow(['Orders', len(complyt_data['invoices']), len(woo_data['orders'])])
        writer.writerow(['Taxable Refunds', len(complyt_data['taxable_refunds']), '-'])
        writer.writerow(['Refunds', len(complyt_data['refunds']), len(woo_data['refunds'])])
        writer.writerow(['Total Refunds', len(complyt_data['taxable_refunds']) + len(complyt_data['refunds']), len(woo_data['refunds'])])
        writer.writerow([''])
        writer.writerow(['Differences'])
        writer.writerow(['Orders in Complyt but not in WooCommerce', len(orders_in_complyt_not_woo)])
        writer.writerow(['Orders in WooCommerce but not in Complyt', len(orders_in_woo_not_complyt)])
        writer.writerow(['Refunds in Complyt but not in WooCommerce', len(refunds_in_complyt_not_woo)])
        writer.writerow(['Refunds in WooCommerce but not in Complyt', len(refunds_in_woo_not_complyt)])
        if date_from and date_to:
            writer.writerow([''])
            writer.writerow(['Date Range', f'{date_from} to {date_to}'])
        writer.writerow(['Generated', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    csv_files.append(summary_path)

    # 2. Orders in Complyt but not in WooCommerce
    if orders_in_complyt_not_woo:
        orders_complyt_not_woo_path = os.path.join(output_dir, "orders_in_complyt_not_woocommerce.csv")
        with open(orders_complyt_not_woo_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Order ID', 'Order Total', 'Order Date'])
            for order_id in orders_in_complyt_not_woo:
                amount = complyt_data['invoice_amounts'].get(order_id, 0)
                # Try to get date from Complyt CSV first
                order_date = complyt_data.get('invoice_dates', {}).get(order_id, 'N/A')
                # If not found in Complyt, try WooCommerce (order might exist but wasn't matched)
                if order_date == 'N/A' or order_date == '':
                    woo_order = woo_data['orders'].get(order_id)
                    if woo_order:
                        order_date = woo_order.get('date_created', 'N/A')
                        logger.info(f"Order {order_id}: Using WooCommerce date {order_date} (not found in Complyt CSV)")
                writer.writerow([order_id, amount, order_date])
        csv_files.append(orders_complyt_not_woo_path)

    # 3. Orders in WooCommerce but not in Complyt
    if orders_in_woo_not_complyt:
        orders_woo_not_complyt_path = os.path.join(output_dir, "orders_in_woocommerce_not_complyt.csv")
        with open(orders_woo_not_complyt_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Order ID', 'Status', 'Order Total', 'Date Created (UTC)'])
            for order_id in orders_in_woo_not_complyt:
                order = woo_data['orders'].get(order_id, {})
                status = order.get('status', 'N/A')
                total = order.get('total', '0')
                # Use date_created_gmt (UTC) for accurate date display - this matches what we filter by
                date_created = order.get('date_created_gmt') or order.get('date_created', 'N/A')
                writer.writerow([order_id, status, total, date_created])
        csv_files.append(orders_woo_not_complyt_path)

    # 4. Refunds in Complyt but not in WooCommerce
    if refunds_in_complyt_not_woo:
        refunds_complyt_not_woo_path = os.path.join(output_dir, "refunds_in_complyt_not_woocommerce.csv")
        with open(refunds_complyt_not_woo_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Refund ID', 'Type', 'Amount', 'Parent Order ID', 'Order Total', 'Refund Date'])
            for refund_id in refunds_in_complyt_not_woo:
                # Determine type
                if refund_id in complyt_data['taxable_refunds']:
                    refund_type = 'TAXABLE_REFUND'
                    amount = complyt_data['taxable_refund_amounts'].get(refund_id, 0)
                    parent_order_id = complyt_data.get('taxable_refund_parent_order_ids', {}).get(refund_id, 'N/A')
                    refund_date = complyt_data.get('taxable_refund_dates', {}).get(refund_id, 'N/A')
                else:
                    refund_type = 'REFUND'
                    amount = complyt_data['refund_amounts'].get(refund_id, 0)
                    parent_order_id = complyt_data.get('refund_parent_order_ids', {}).get(refund_id, 'N/A')
                    refund_date = complyt_data.get('refund_dates', {}).get(refund_id, 'N/A')

                # If parent order ID or date not found in Complyt, try WooCommerce
                if (parent_order_id == 'N/A' or parent_order_id == '') or (refund_date == 'N/A' or refund_date == ''):
                    woo_refund = woo_data['refunds'].get(refund_id)
                    if woo_refund:
                        if parent_order_id == 'N/A' or parent_order_id == '':
                            parent_order_id = woo_refund.get('order_id', 'N/A')
                        if refund_date == 'N/A' or refund_date == '':
                            refund_date = woo_refund.get('date_created', 'N/A')
                        logger.info(f"Refund {refund_id}: Using WooCommerce data (parent_order_id={parent_order_id}, date={refund_date})")

                # Get order total from WooCommerce if parent order ID is available
                order_total = 'N/A'
                if parent_order_id and parent_order_id != 'N/A':
                    parent_order = woo_data['orders'].get(str(parent_order_id))
                    if parent_order:
                        order_total = parent_order.get('total', 'N/A')
                    else:
                        # Try Complyt data if not in WooCommerce
                        order_total = complyt_data['invoice_amounts'].get(str(parent_order_id), 'N/A')

                writer.writerow([refund_id, refund_type, amount, parent_order_id, order_total, refund_date])
        csv_files.append(refunds_complyt_not_woo_path)

    # 5. Refunds in WooCommerce but not in Complyt
    if refunds_in_woo_not_complyt:
        refunds_woo_not_complyt_path = os.path.join(output_dir, "refunds_in_woocommerce_not_complyt.csv")
        with open(refunds_woo_not_complyt_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Refund ID', 'Order ID', 'Amount', 'Order Total', 'Date Created'])
            for refund_id in refunds_in_woo_not_complyt:
                refund = woo_data['refunds'].get(refund_id, {})
                order_id = refund.get('order_id', 'N/A')
                amount = refund.get('amount', '0')
                date_created = refund.get('date_created', 'N/A')
                
                # Get order total from WooCommerce
                order_total = 'N/A'
                if order_id and order_id != 'N/A':
                    parent_order = woo_data['orders'].get(str(order_id))
                    if parent_order:
                        order_total = parent_order.get('total', 'N/A')
                    else:
                        # Try Complyt data if not in WooCommerce
                        order_total = complyt_data['invoice_amounts'].get(str(order_id), 'N/A')
                
                writer.writerow([refund_id, order_id, amount, order_total, date_created])
        csv_files.append(refunds_woo_not_complyt_path)

    logger.info(f"Generated {len(csv_files)} CSV files in {output_dir}")
    return csv_files


def create_comparison_report_zip(
    complyt_data: Dict[str, Any],
    woo_data: Dict[str, Any],
    output_path: str,
    date_from: str = None,
    date_to: str = None
) -> str:
    """
    Generate CSV reports and pack them in a ZIP archive.

    Returns:
        Path to the generated ZIP file
    """
    # Create temporary directory for CSV files
    temp_dir = tempfile.mkdtemp()

    try:
        # Generate CSV files
        csv_files = generate_comparison_report_csvs(
            complyt_data,
            woo_data,
            temp_dir,
            date_from=date_from,
            date_to=date_to
        )

        # Create ZIP archive
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for csv_file in csv_files:
                # Add file to ZIP with just the filename (not full path)
                zipf.write(csv_file, os.path.basename(csv_file))

        logger.info(f"ZIP archive successfully created at: {output_path}")
        logger.info(f"Archive contains {len(csv_files)} CSV files")

    finally:
        # Clean up temporary directory
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up temporary directory {temp_dir}: {str(e)}")

    return output_path

