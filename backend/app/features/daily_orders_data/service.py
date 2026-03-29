import csv
import logging
import os
import random
import requests
import base64
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Callable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Timezone offset in seconds (4 hours = Eastern Time offset)
# This matches the export-stats plugin's timezone handling
TIMEZONE_OFFSET_SECONDS = 4 * 3600  # 4 hours in seconds


def fetch_daily_orders_data(
    date: str,
    woo_base_url: str,
    woo_consumer_key: str,
    woo_consumer_secret: str,
    per_page: int = 300,
    update_progress: Optional[Callable[[int, str], None]] = None
) -> Dict[str, Any]:
    """
    Fetch orders and refunds from WooCommerce using the dedicated daily-orders-data endpoint.
    This endpoint returns both orders and refunds with all necessary data in a single call.
    Loads all orders for the selected date (from 00:00:00 to next day 00:00:00) in Metorik timezone.

    Args:
        date: Date in ISO format (YYYY-MM-DDTHH:MM:SSZ) - single date to export
        woo_base_url: WooCommerce store base URL
        woo_consumer_key: WooCommerce API consumer key
        woo_consumer_secret: WooCommerce API consumer secret
        per_page: Maximum records to fetch per page (default 300 for efficiency)
        update_progress: Optional callback function(progress, message) to update progress

    Returns:
        Dictionary with orders and refunds data and metadata
    """
    try:
        # Convert ISO date to the format expected by the WooCommerce plugin
        # The plugin expects: YYYY-MM-DD HH:MM:SS in Metorik timezone (America/New_York)
        # The date from frontend is in UTC format, but we interpret it as Metorik timezone date
        # (i.e., if user selects Nov 26, 2025, we want Nov 26 00:00:00 in Metorik timezone, not UTC)
        metorik_tz = ZoneInfo('America/New_York')

        # Parse the UTC date string and extract the date components
        date_dt_utc = datetime.fromisoformat(date.replace('Z', '+00:00'))

        # Interpret the date components as Metorik timezone (not convert from UTC)
        # This means if the user selects Nov 26, 2025, we want Nov 26, 2025 00:00:00 in Metorik timezone
        date_dt_metorik = datetime(
            date_dt_utc.year, date_dt_utc.month, date_dt_utc.day,
            0, 0, 0,  # Start of day: 00:00:00
            tzinfo=metorik_tz
        )

        # End of day: next day 00:00:00 (to include orders at exactly midnight of the next day, matching Metorik)
        from datetime import timedelta
        end_dt_metorik = date_dt_metorik + timedelta(days=1)

        # Format as YYYY-MM-DD HH:MM:SS (Metorik timezone)
        after_date = date_dt_metorik.strftime('%Y-%m-%d %H:%M:%S')
        before_date = end_dt_metorik.strftime('%Y-%m-%d %H:%M:%S')

        api_base = f"{woo_base_url.rstrip('/')}/wp-json/pfm-tools/v1"
        data_url = f"{api_base}/daily-orders-data"

        # Create Basic Auth header
        auth_string = f"{woo_consumer_key}:{woo_consumer_secret}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')

        # Create session for custom endpoint with connection pooling
        # Use X-PFM-Authorization instead of Authorization to avoid WordPress core
        # intercepting the standard Basic Auth header on WP Engine hosting.
        session = requests.Session()
        session.headers.update({
            'Accept': '*/*',
            'User-Agent': 'curl/7.68.0',
            'Accept-Encoding': 'gzip, deflate',
            'X-PFM-Authorization': f'Basic {auth_b64}'
        })

        all_orders = []
        all_refunds = []
        page_num = 1
        total_order_pages = None
        total_refund_pages = None
        total_order_count = None
        total_refund_count = None
        fetch_start_time = time.time()

        logger.info(f"Fetching daily orders data for {after_date} to {before_date} (Metorik timezone: America/New_York)")

        while True:
            params = {
                'date_after': after_date,
                'date_before': before_date,
                'per_page': per_page,
                'page': page_num,
            }

            # Retry logic for transient failures
            max_retries = 3
            retry_delay = 2  # seconds
            last_exception = None

            for attempt in range(max_retries):
                try:
                    # Increased timeout to 5 minutes (300 seconds) to handle large datasets
                    # The server may need time to process and return large amounts of data
                    response = session.get(data_url, params=params, timeout=300)
                    response.raise_for_status()
                    last_exception = None
                    break  # Success, exit retry loop
                except requests.exceptions.Timeout as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)  # Exponential backoff
                        logger.warning(f"Timeout fetching page {page_num} (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Timeout fetching page {page_num} after {max_retries} attempts")
                        raise
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        logger.warning(f"Error fetching page {page_num} (attempt {attempt + 1}/{max_retries}): {str(e)}, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Error fetching page {page_num} after {max_retries} attempts: {str(e)}")
                        raise

            if last_exception:
                raise last_exception

            data = response.json()

            # Get pagination info from headers (first page only)
            if total_order_pages is None:
                total_order_pages = int(response.headers.get('X-WP-Total-OrderPages', 1))
                total_order_count = int(response.headers.get('X-WP-Total-Orders', 0))
                total_refund_pages = int(response.headers.get('X-WP-Total-RefundPages', 1))
                total_refund_count = int(response.headers.get('X-WP-Total-Refunds', 0))
                logger.info(f"Total orders available: {total_order_count} (across {total_order_pages} pages)")
                logger.info(f"Total refunds available: {total_refund_count} (across {total_refund_pages} pages)")

            # Extract orders and refunds from response
            orders = data.get('orders', [])
            refunds = data.get('refunds', [])

            all_orders.extend(orders)
            all_refunds.extend(refunds)

            # Calculate progress (0-90% for fetching, remaining 10% for processing)
            # Use the maximum of order pages and refund pages for progress calculation
            max_pages = max(total_order_pages, total_refund_pages) if total_order_pages and total_refund_pages else (total_order_pages or total_refund_pages or 1)
            if max_pages and update_progress:
                fetch_progress = min(90, int((page_num / max_pages) * 90))
                update_progress(fetch_progress, f'Fetching data... Page {page_num}/{max_pages} ({len(all_orders)} orders, {len(all_refunds)} refunds)')

            logger.info(f"Fetched {len(orders)} orders and {len(refunds)} refunds (page {page_num}/{max_pages})")

            # Check if we've fetched all pages (both orders and refunds)
            if (page_num >= total_order_pages and page_num >= total_refund_pages) or (len(orders) == 0 and len(refunds) == 0):
                break

            page_num += 1

        session.close()

        fetch_time = time.time() - fetch_start_time

        # Log first and last order IDs for timezone verification (after fetching all pages)
        first_order_id = None
        last_order_id = None
        if all_orders:
            first_order_id = all_orders[0].get('id') if isinstance(all_orders[0], dict) else None
            last_order_id = all_orders[-1].get('id') if isinstance(all_orders[-1], dict) else None

        # Log first and last refund IDs for timezone verification
        first_refund_id = None
        last_refund_id = None
        if all_refunds:
            first_refund_id = all_refunds[0].get('id') if isinstance(all_refunds[0], dict) else None
            last_refund_id = all_refunds[-1].get('id') if isinstance(all_refunds[-1], dict) else None

        logger.info(f"Successfully fetched {len(all_orders)} orders and {len(all_refunds)} refunds in {fetch_time:.2f} seconds")
        logger.info(f"[Daily Orders Data] Date range: {after_date} to {before_date} (Metorik timezone: America/New_York) | First Order ID: {first_order_id or 'N/A'} | Last Order ID: {last_order_id or 'N/A'} | Total Orders: {len(all_orders)}")
        logger.info(f"[Daily Orders Data] First Refund ID: {first_refund_id or 'N/A'} | Last Refund ID: {last_refund_id or 'N/A'} | Total Refunds: {len(all_refunds)}")

        return {
            'orders': all_orders,
            'refunds': all_refunds,
            'total_order_count': len(all_orders),
            'total_refund_count': len(all_refunds),
            'pages_fetched': page_num,
            'fetch_time': fetch_time
        }
    except Exception as e:
        logger.error(f"Error fetching daily orders data: {str(e)}", exc_info=True)
        raise


def apply_timezone_offset_to_order_date(date_value: str) -> Optional[datetime]:
    """
    Parse order date and ensure it's in Metorik timezone (America/New_York) for grouping.

    The PHP endpoint's get_date_created()->date('Y-m-d H:i:s') returns dates in the site's timezone.
    Since the site timezone is set to America/New_York (Metorik timezone), the dates are already
    in the correct timezone. We just need to parse them and assign the timezone for grouping.

    Args:
        date_value: Order date string (YYYY-MM-DD HH:MM:SS or ISO format)

    Returns:
        Datetime object in Metorik timezone (America/New_York), or None if parsing fails
    """
    try:
        from zoneinfo import ZoneInfo
        metorik_tz = ZoneInfo('America/New_York')

        # Parse the date (format: YYYY-MM-DD HH:MM:SS or ISO)
        if 'T' in date_value:
            # ISO format: 2025-11-01T12:00:00Z or 2025-11-01T12:00:00.000Z
            if '.' in date_value and 'Z' in date_value:
                date_value = date_value.split('.')[0] + 'Z'
            order_dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            # If it has Z, it's UTC, convert to Metorik timezone
            if 'Z' in date_value or order_dt.tzinfo == timezone.utc:
                adjusted_dt = order_dt.astimezone(metorik_tz)
            else:
                # Already in a timezone, convert to Metorik timezone
                adjusted_dt = order_dt.astimezone(metorik_tz) if order_dt.tzinfo else order_dt.replace(tzinfo=metorik_tz)
        else:
            # Space format: YYYY-MM-DD HH:MM:SS
            # The PHP endpoint returns dates in the site's timezone (America/New_York)
            # So we parse it and assign Metorik timezone (no conversion needed)
            order_dt = datetime.strptime(date_value, '%Y-%m-%d %H:%M:%S')
            # The date is already in Metorik timezone (as returned by PHP endpoint)
            # Just assign the timezone for proper datetime handling
            adjusted_dt = order_dt.replace(tzinfo=metorik_tz)

        return adjusted_dt
    except Exception as e:
        logger.warning(f"Could not parse date '{date_value}': {e}")
        return None




def save_daily_orders_to_csv(
    data: Dict[str, Any],
    output_path: str,
    selected_date: str = None,
    update_progress: Optional[Callable[[int, str], None]] = None
) -> str:
    """
    Save WooCommerce orders data to CSV file in daily aggregated format.
    Only includes orders for the selected date (filters out orders from next day).

    Args:
        data: Daily orders data from WooCommerce API (should have 'orders' and 'refunds' keys)
        output_path: Path where CSV should be saved
        selected_date: Selected date in ISO format (YYYY-MM-DDTHH:MM:SSZ) - only orders for this date will be included
        update_progress: Optional callback function(progress, message) to update progress

    Returns:
        Path to saved CSV file
    """
    logger.info(f"Saving daily orders to CSV: {output_path}")

    orders = data.get('orders', [])
    refunds = data.get('refunds', [])
    total_count = data.get('total_order_count', len(orders))

    logger.info(f"Processing {len(orders)} orders to CSV (total_count: {total_count})")

    if not orders:
        # Create empty CSV with headers (matching export-stats format)
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Date',
                'Net Revenue',
                'Total Refunds',
                'New Customers',
                'Total Orders',
                'Units Sold',
                'New Gravite Non-Subscription',
                'New Subscriptions',
                'New Non-Gravite Non-Subscription'
            ])
            writer.writerow(['No orders found for the selected date range'])
        logger.info(f"Created empty CSV file: {output_path}")
        return output_path

    # Get currency exchange rates (for converting non-USD orders)
    # Note: For now, we'll skip currency conversion. If needed, we can add it later.
    # The export-stats plugin uses: https://v6.exchangerate-api.com/v6/871e5e2ef51033185690c90e/latest/USD

    # Format the selected date for display (trust WooCommerce returns only orders for this date)
    display_date = None
    if selected_date:
        try:
            from zoneinfo import ZoneInfo
            metorik_tz = ZoneInfo('America/New_York')
            date_dt_utc = datetime.fromisoformat(selected_date.replace('Z', '+00:00'))
            display_date_dt = datetime(
                date_dt_utc.year, date_dt_utc.month, date_dt_utc.day,
                0, 0, 0,
                tzinfo=metorik_tz
            )
            display_date = display_date_dt
        except Exception as e:
            logger.warning(f"Could not parse selected_date for display: {e}")
            # Fallback to current date
            display_date = datetime.now(ZoneInfo('America/New_York')).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # Fallback to current date
        from zoneinfo import ZoneInfo
        display_date = datetime.now(ZoneInfo('America/New_York')).replace(hour=0, minute=0, second=0, microsecond=0)

    # Aggregate all orders into a single totals object (no date parsing - trust WooCommerce)
    totals = {
        'date': display_date,
        'total_orders': 0,
        'total_sales': 0.0,
        'total_taxes': 0.0,
        'units_sold': 0,
        'new_customers': 0,
        'new_gravite_non_subscription': 0,
        'new_subscriptions': 0,
        'new_non_gravite_non_subscription': 0,
        'total_refunds': 0.0,
    }
    processed_count = 0

    for order in orders:
        if not isinstance(order, dict):
            continue

        # Get order values
        order_total = order.get('total', 0)
        order_tax = order.get('total_tax', 0)
        order_currency = order.get('currency', 'USD')

        # Currency conversion (if needed - for now, assume USD or skip conversion)
        # TODO: Add currency conversion if needed
        # exchange_rate = get_exchange_rate(order_currency)
        # if exchange_rate:
        #     order_total = order_total / exchange_rate
        #     order_tax = order_tax / exchange_rate

        # Get units sold (from line items or total_units field)
        units = order.get('total_units', 0)
        if units == 0:
            # Fallback: sum from line_items if total_units not available
            line_items = order.get('line_items', [])
            units = sum(item.get('quantity', 0) for item in line_items if isinstance(item, dict))

        # Count all orders (matching Metorik behavior)
        # Note: export-stats plugin skips orders with 0 units, but Metorik counts all orders
        # We'll count all orders to match Metorik, but units_sold will be 0 for orders with no units
        totals['total_orders'] += 1
        totals['total_sales'] += float(order_total)
        totals['total_taxes'] += float(order_tax)
        totals['units_sold'] += int(units) if units > 0 else 0

        # Check for new customers
        new_or_returning = order.get('new_or_returning', '')
        if new_or_returning == 'new':
            totals['new_customers'] += 1

            # Check subscription status
            subscription_parent = order.get('subscription_parent', '')
            subscription_renewal = order.get('subscription_renewal', '')
            is_subscription = bool(subscription_parent) or bool(subscription_renewal)

            if subscription_parent:
                totals['new_subscriptions'] += 1

            if not is_subscription:
                # Check if order contains only Gravite product (SKU: 860005339785)
                line_items = order.get('line_items', [])
                only_gravite = True
                has_gravite = False

                for item in line_items:
                    if not isinstance(item, dict):
                        continue
                    sku = item.get('sku', '')
                    if sku != '860005339785':
                        only_gravite = False
                    else:
                        has_gravite = True

                if only_gravite and has_gravite:
                    totals['new_gravite_non_subscription'] += 1
                else:
                    totals['new_non_gravite_non_subscription'] += 1

        processed_count += 1

        # Update progress (90-100% for processing)
        if update_progress and total_count > 0:
            processing_progress = 90 + int((processed_count / total_count) * 10)
            update_progress(min(100, processing_progress), f'Processing orders... {processed_count}/{total_count}')

    # Process refunds separately (matching export-stats plugin)
    logger.info(f"Processing {len(refunds)} refunds")

    if not refunds:
        logger.info("No refunds found (this is normal if there are no refunds)")

    for refund in refunds:
        if not isinstance(refund, dict):
            continue

        # Add refund amount (absolute value, matching export-stats plugin)
        # Trust WooCommerce returns only refunds for the requested date
        refund_amount = abs(float(refund.get('amount', 0)))
        # TODO: Currency conversion if needed
        totals['total_refunds'] += refund_amount

    # Calculate net_revenue (matching export-stats plugin)
    # net_revenue = total_sales - total_refunds - total_taxes
    total_refunds = totals.get('total_refunds', 0.0)
    total_taxes = totals.get('total_taxes', 0.0)
    total_sales = totals.get('total_sales', 0.0)
    totals['net_revenue'] = total_sales - total_refunds - total_taxes

    logger.info(f"Order processing summary: {processed_count} orders processed, {len(refunds)} refunds processed")

    # Write CSV file (matching export-stats plugin format)
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)

        # Write headers (matching export-stats plugin structure)
        headers = [
            'Date',
            'Net Revenue',
            'Total Refunds',
            'New Customers',
            'Total Orders',
            'Units Sold',
            'New Gravite Non-Subscription',
            'New Subscriptions',
            'New Non-Gravite Non-Subscription'
        ]
        writer.writerow(headers)

        # Write single data row (all orders aggregated - trust WooCommerce returned only orders for selected date)
        # Format date as "Nov 1, 2025"
        date_formatted = totals['date'].strftime('%b %d, %Y')

        row = [
            date_formatted,
            round(totals.get('net_revenue', 0.0), 2),
            round(totals.get('total_refunds', 0.0), 2),
            totals.get('new_customers', 0),
            totals.get('total_orders', 0),
            totals.get('units_sold', 0),
            totals.get('new_gravite_non_subscription', 0),
            totals.get('new_subscriptions', 0),
            totals.get('new_non_gravite_non_subscription', 0),
        ]

        writer.writerow(row)

    logger.info(f"Successfully saved aggregated data to CSV: {output_path}")
    return output_path


def export_to_google_sheets(
    orders_data: Dict[str, Any],
    spreadsheet_id: str,
    sheet_name: str,
    oauth_credentials_path: str = None,
    oauth_token_path: str = None,
    service_account_path: str = None,
    start_date: str = None,
    end_date: str = None
) -> bool:
    """
    Export daily orders data to Google Sheets in the same format as CSV export.

    Args:
        orders_data: Orders data from WooCommerce API
        spreadsheet_id: Google Sheets spreadsheet ID
        sheet_name: Name of the sheet to write to
        oauth_credentials_path: Path to OAuth client credentials JSON file
        oauth_token_path: Path to saved OAuth token file
        service_account_path: Path to service account JSON file
        start_date: Optional start date for filtering
        end_date: Optional end date for filtering

    Returns:
        True if successful, False otherwise
    """
    import gspread
    import pickle
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import Request

    logger.info(f"Exporting to Google Sheets: {spreadsheet_id}/{sheet_name}")

    try:
        # Authenticate with Google Sheets
        scope = ['https://www.googleapis.com/auth/spreadsheets',
                 'https://www.googleapis.com/auth/drive']

        creds = None
        auth_method = None

        # Try OAuth authentication first
        if oauth_credentials_path and oauth_token_path:
            if os.path.exists(oauth_token_path):
                try:
                    logger.info("Attempting OAuth authentication")
                    with open(oauth_token_path, 'rb') as token:
                        creds = pickle.load(token)

                    if creds.expired and creds.refresh_token:
                        logger.info("OAuth token expired, refreshing...")
                        creds.refresh(Request())
                        with open(oauth_token_path, 'wb') as token:
                            pickle.dump(creds, token)

                    if creds.valid:
                        auth_method = "OAuth"
                        logger.info("OAuth authentication successful")
                except Exception as e:
                    logger.warning(f"Could not load OAuth token: {e}")
                    creds = None

        # Fall back to service account authentication
        if not creds and service_account_path:
            if os.path.exists(service_account_path):
                try:
                    logger.info(f"Attempting service account authentication: {service_account_path}")
                    creds = Credentials.from_service_account_file(service_account_path, scopes=scope)
                    auth_method = "Service Account"
                    logger.info("Service account authentication successful")
                except Exception as e:
                    logger.warning(f"Could not load service account credentials: {e}")
                    creds = None

        if not creds:
            logger.error("No valid Google credentials found.")
            return False

        # Authorize gspread client
        client = gspread.authorize(creds)
        logger.info(f"Authenticated using {auth_method}")

        # Open the spreadsheet
        try:
            logger.info(f"Opening spreadsheet with ID: {spreadsheet_id}")
            spreadsheet = client.open_by_key(spreadsheet_id)
            logger.info(f"Successfully opened spreadsheet: {spreadsheet.title}")
        except Exception as e:
            logger.error(f"Failed to open spreadsheet {spreadsheet_id}: {str(e)}", exc_info=True)
            return False

        # Get or create the sheet
        worksheet = None
        has_headers = False

        try:
            logger.info(f"Looking for sheet: {sheet_name}")
            all_worksheets = spreadsheet.worksheets()
            logger.info(f"Available sheets: {[ws.title for ws in all_worksheets]}")

            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                logger.info(f"Found existing sheet: {sheet_name}")
            except gspread.exceptions.WorksheetNotFound:
                for ws in all_worksheets:
                    if ws.title.lower() == sheet_name.lower():
                        worksheet = ws
                        logger.info(f"Found existing sheet (case-insensitive): '{ws.title}'")
                        break

                if not worksheet:
                    logger.info(f"Sheet '{sheet_name}' not found, creating new sheet...")
                    worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
                    logger.info(f"Created new sheet: {sheet_name}")

            existing_data = worksheet.get_all_values()
            has_headers = len(existing_data) > 0

        except Exception as e:
            logger.error(f"Error accessing sheet '{sheet_name}': {str(e)}", exc_info=True)
            return False

        # Process orders data (same logic as CSV export)
        orders = orders_data.get('orders', [])

        if not orders:
            if not has_headers:
                headers = [
                    'Date',
                    'Total Orders',
                    'Total Revenue',
                    'Total Tax',
                    'Total Shipping',
                    'Total Discount'
                ]
                worksheet.append_row(headers)
                worksheet.append_row(['No orders found for the selected date range'])
            return True

        # Aggregate orders by date (same logic as CSV)
        daily_totals = {}

        for order in orders:
            if not isinstance(order, dict):
                continue

            date_key = None
            date_value = order.get('date_created')

            if date_value and isinstance(date_value, str):
                try:
                    if 'T' in date_value:
                        order_dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                    else:
                        order_dt = datetime.strptime(date_value, '%Y-%m-%d %H:%M:%S')
                        if order_dt.tzinfo is None:
                            order_dt = order_dt.replace(tzinfo=timezone.utc)

                    date_key = order_dt.strftime('%Y-%m-%d')
                    order_date = order_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                except Exception as e:
                    logger.warning(f"Could not parse date '{date_value}': {e}")
                    continue

            if not date_key:
                continue

            if date_key not in daily_totals:
                daily_totals[date_key] = {
                    'date': order_date,
                    'orders_count': 0,
                    'revenue': 0.0,
                    'tax': 0.0,
                    'shipping': 0.0,
                    'discount': 0.0,
                }

            daily_totals[date_key]['orders_count'] += 1

            try:
                daily_totals[date_key]['revenue'] += float(order.get('total', 0))
                daily_totals[date_key]['tax'] += float(order.get('total_tax', 0))
                daily_totals[date_key]['shipping'] += float(order.get('shipping_total', 0))
                daily_totals[date_key]['discount'] += float(order.get('discount_total', 0))
            except (ValueError, TypeError):
                pass

        # Sort by date
        sorted_dates = sorted(daily_totals.keys())

        # Prepare headers
        headers = [
            'Date',
            'Total Orders',
            'Total Revenue',
            'Total Tax',
            'Total Shipping',
            'Total Discount'
        ]

        # Write or update headers
        if not has_headers:
            try:
                logger.info("Writing headers to Google Sheets...")
                worksheet.append_row(headers)
            except Exception as e:
                logger.error(f"Error writing headers: {str(e)}", exc_info=True)
                return False

        # Prepare data rows
        rows = []
        for date_key in sorted_dates:
            totals = daily_totals[date_key]
            date_formatted = totals['date'].strftime('%b %d, %Y')

            row = [
                date_formatted,
                totals['orders_count'],
                round(totals['revenue'], 2),
                round(totals['tax'], 2),
                round(totals['shipping'], 2),
                round(totals['discount'], 2),
            ]

            rows.append(row)

        # Batch write all new rows
        if rows:
            try:
                logger.info(f"Appending {len(rows)} new rows to Google Sheets...")
                worksheet.append_rows(rows)
                logger.info(f"Successfully appended {len(rows)} rows to Google Sheets")
            except Exception as e:
                logger.error(f"Error writing rows to Google Sheets: {str(e)}", exc_info=True)
                return False

        logger.info(f"Successfully exported {len(sorted_dates)} days of aggregated data to Google Sheets")
        return True

    except Exception as e:
        logger.error(f"Error exporting to Google Sheets: {str(e)}", exc_info=True)
        return False


def export_stats_to_google_sheets(
    orders_data: Dict[str, Any],
    base_date: str,
    spreadsheet_id: str,
    oauth_credentials_path: str = None,
    oauth_token_path: str = None,
    service_account_path: str = None,
) -> bool:
    """
    Export daily stats to Google Sheets in the same format as export-stats.php.
    Calculates net_revenue, total_refunds, new_customers, total_orders, units_sold,
    and media stats (new_gravite_non_subscription, new_subscriptions, new_non_gravite_non_subscription).

    Args:
        orders_data: Orders data from WooCommerce API (should have 'orders' key with list of orders)
        base_date: Base date in YYYY-MM-DD format
        spreadsheet_id: Google Sheets spreadsheet ID (from settings)
        oauth_credentials_path: Path to OAuth client credentials JSON file
        oauth_token_path: Path to saved OAuth token file
        service_account_path: Path to service account JSON file

    Returns:
        True if successful, False otherwise
    """
    import gspread
    import pickle
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import Request

    logger.info(f"Exporting to Google Sheets: {spreadsheet_id}")

    try:
        # Authenticate with Google Sheets
        scope = ['https://www.googleapis.com/auth/spreadsheets',
                 'https://www.googleapis.com/auth/drive']

        creds = None
        auth_method = None

        # Try OAuth authentication first
        if oauth_credentials_path and oauth_token_path:
            if os.path.exists(oauth_token_path):
                try:
                    logger.info("Attempting OAuth authentication")
                    with open(oauth_token_path, 'rb') as token:
                        creds = pickle.load(token)

                    if creds.expired and creds.refresh_token:
                        logger.info("OAuth token expired, refreshing...")
                        creds.refresh(Request())
                        with open(oauth_token_path, 'wb') as token:
                            pickle.dump(creds, token)

                    if creds.valid:
                        auth_method = "OAuth"
                        logger.info("OAuth authentication successful")
                except Exception as e:
                    logger.warning(f"Could not load OAuth token: {e}")
                    creds = None

        # Fall back to service account authentication
        if not creds and service_account_path:
            if os.path.exists(service_account_path):
                try:
                    logger.info(f"Attempting service account authentication: {service_account_path}")
                    creds = Credentials.from_service_account_file(service_account_path, scopes=scope)
                    auth_method = "Service Account"
                    logger.info("Service account authentication successful")
                except Exception as e:
                    logger.warning(f"Could not load service account credentials: {e}")
                    creds = None

        if not creds:
            logger.error("No valid Google credentials found.")
            return False

        # Authorize gspread client
        client = gspread.authorize(creds)
        logger.info(f"✓ Authenticated using {auth_method}")

        # Open the spreadsheet
        try:
            logger.info(f"Opening spreadsheet with ID: {spreadsheet_id}")
            spreadsheet = client.open_by_key(spreadsheet_id)
            logger.info(f"✓ Successfully opened spreadsheet: '{spreadsheet.title}' (ID: {spreadsheet.id})")
            logger.info(f"✓ Spreadsheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
        except Exception as e:
            logger.error(f"✗ Failed to open spreadsheet {spreadsheet_id}: {str(e)}", exc_info=True)
            return False

        # Calculate stats from orders data (similar to export-stats.php)
        orders = orders_data.get('orders', [])
        refunds = orders_data.get('refunds', [])

        total_sales = 0.0
        total_taxes = 0.0
        units_sold = 0
        total_orders = 0
        new_customers = 0
        new_gravite_non_subscription = 0
        new_non_gravite_non_subscription = 0
        new_subscriptions = 0
        total_refunds = 0.0

        # Process orders
        for order in orders:
            if not isinstance(order, dict):
                continue

            # Get total quantity of items in the order (only line items)
            line_items = order.get('line_items', [])
            items_in_order = sum(item.get('quantity', 0) for item in line_items)

            if items_in_order <= 0:
                continue

            total_orders += 1

            # Get order totals (already in USD from the API)
            order_total = float(order.get('total', 0))
            tax = float(order.get('total_tax', 0))

            total_sales += order_total
            total_taxes += tax
            units_sold += items_in_order

            # Check for new customers
            new_or_returning = order.get('new_or_returning', '')
            if new_or_returning == 'new':
                new_customers += 1

                subscription_parent = order.get('subscription_parent', '')
                subscription_renewal = order.get('subscription_renewal', '')

                is_subscription = bool(subscription_renewal) or bool(subscription_parent)

                if subscription_parent:
                    new_subscriptions += 1

                if not is_subscription:
                    # Check if order contains only Gravite (SKU: 860005339785)
                    only_gravite = True
                    has_gravite = False

                    for item in line_items:
                        sku = item.get('sku', '')
                        if sku != '860005339785':
                            only_gravite = False
                        else:
                            has_gravite = True

                    if only_gravite and has_gravite:
                        new_gravite_non_subscription += 1
                    else:
                        new_non_gravite_non_subscription += 1

        # Process refunds
        for refund in refunds:
            if not isinstance(refund, dict):
                continue

            refund_amount = abs(float(refund.get('amount', 0)))
            total_refunds += refund_amount

        # Calculate net revenue
        net_revenue = total_sales - total_refunds - total_taxes

        logger.info(f"Calculated stats: total_sales={total_sales}, total_refunds={total_refunds}, total_taxes={total_taxes}, net_revenue={net_revenue}")
        logger.info(f"Calculated stats: total_orders={total_orders}, units_sold={units_sold}, new_customers={new_customers}")
        logger.info(f"Media stats: new_gravite_non_subscription={new_gravite_non_subscription}, new_subscriptions={new_subscriptions}, new_non_gravite_non_subscription={new_non_gravite_non_subscription}")

        # Format date for export (m/d/Y format like export-stats.php)
        try:
            date_obj = datetime.strptime(base_date, '%Y-%m-%d')
            converted_date = date_obj.strftime('%m/%d/%Y')
            logger.info(f"Converted date: {base_date} -> {converted_date}")
        except Exception as e:
            logger.warning(f"Could not parse date {base_date}: {e}")
            converted_date = base_date

        # Format timestamp with domain (like export-stats.php)
        current_time = datetime.now(ZoneInfo("Asia/Jerusalem"))
        timestamp_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
        domain = "https://tools.pfm-qa.com/"

        # Convert empty strings to None (like PHP uses Google_Model::NULL_VALUE)
        # This ensures Google Sheets handles empty cells correctly
        data_to_export = [
            f"{timestamp_str} | Domain: {domain}",
            None,  # Empty cell - use None instead of ""
            net_revenue,
            total_refunds,
            new_customers,
            None,  # Empty cell - use None instead of ""
            total_orders,
            units_sold,
        ]

        media_data_to_export = [
            new_gravite_non_subscription,
            new_subscriptions,
            new_non_gravite_non_subscription,
        ]

        # Determine sheet name from date (e.g., "November'25")
        try:
            date_obj = datetime.strptime(base_date, '%Y-%m-%d')
            sheet_name = date_obj.strftime("%B'%y")  # e.g., "November'25"
        except Exception as e:
            logger.warning(f"Could not determine sheet name from {base_date}: {e}")
            sheet_name = "Sheet1"

        # Export main data
        success = add_data_for_date(
            client, spreadsheet, sheet_name, converted_date, data_to_export
        )

        if not success:
            logger.error("Failed to export main data to Google Sheets")
            return False

        # Export media data
        try:
            date_obj = datetime.strptime(base_date, '%Y-%m-%d')
            media_sheet_name = f"MEDIA_{date_obj.strftime('%B\'%y')}"  # e.g., "MEDIA_November'25"
            success_media = add_media_data_for_date(
                client, spreadsheet, media_sheet_name, date_obj, media_data_to_export
            )

            if not success_media:
                logger.warning("Failed to export media data to Google Sheets, but main data was exported")
        except Exception as e:
            logger.warning(f"Error exporting media data: {e}", exc_info=True)

        logger.info(f"Successfully exported stats to Google Sheets for {base_date}")
        return True

    except Exception as e:
        logger.error(f"Error exporting stats to Google Sheets: {str(e)}", exc_info=True)
        return False


def add_data_for_date(
    client: Any,
    spreadsheet: Any,
    sheet_name: str,
    input_date: str,
    data_to_export: List[Any]
) -> bool:
    """
    Add data for a specific date to Google Sheets (similar to export-stats.php add_data_for_date).

    Args:
        client: Authenticated gspread client
        spreadsheet: Opened spreadsheet object
        sheet_name: Name of the sheet (e.g., "November'25")
        input_date: Date in m/d/Y format (e.g., "11/26/2025")
        data_to_export: List of data values to export to column F

    Returns:
        True if successful, False otherwise
    """
    import gspread
    """
    Add data for a specific date to Google Sheets (similar to export-stats.php add_data_for_date).

    Args:
        client: Authenticated gspread client
        spreadsheet: Opened spreadsheet object
        sheet_name: Name of the sheet (e.g., "November'25")
        input_date: Date in m/d/Y format (e.g., "11/26/2025")
        data_to_export: List of data values to export to column F

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get or create the sheet
        worksheet = None
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            logger.info(f"Found existing sheet: {sheet_name}")
        except gspread.exceptions.WorksheetNotFound:
            # Try case-insensitive match
            all_worksheets = spreadsheet.worksheets()
            for ws in all_worksheets:
                if ws.title.lower() == sheet_name.lower():
                    worksheet = ws
                    logger.info(f"Found existing sheet (case-insensitive): '{ws.title}'")
                    break

            if not worksheet:
                logger.info(f"Sheet '{sheet_name}' not found, creating new sheet...")
                worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
                logger.info(f"Created new sheet: {sheet_name}")

        # Find row by date (similar to export-stats.php find_row_by_date)
        logger.info(f"Finding row for date {input_date} in sheet '{sheet_name}' (worksheet title: '{worksheet.title}')")
        row_number = find_row_by_date(worksheet, input_date)
        if row_number is None:
            logger.warning(f"Date {input_date} not found in sheet {sheet_name}, skipping update")
            return False

        logger.info(f"Found row {row_number} for date {input_date}")

        # Update data in row (similar to export-stats.php update_data_in_row)
        # PHP uses: $sheet_name . '!F' . $rowNumber and passes full data array
        # But we need to specify the full range F:M to ensure all columns are written
        # Using F5:M5 format ensures all 8 columns are updated correctly
        range_str = f"F{row_number}:M{row_number}"

        try:
            # Try worksheet.update() first, but fall back to update_cell() if it fails
            # This handles apostrophes in sheet names (like Inventory Data does)
            try:
                # Add a small random delay to avoid concurrent write conflicts when multiple jobs run simultaneously
                delay = random.uniform(0.1, 0.5)  # 100-500ms random delay
                time.sleep(delay)
                worksheet.update(range_str, [data_to_export], value_input_option='RAW')
            except Exception as update_error:
                logger.warning(f"worksheet.update() failed: {update_error}, falling back to update_cell()")
                # Fall back to individual cell updates (like Inventory Data does)
                columns = ['F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']
                for col, value in zip(columns, data_to_export):
                    col_num = ord(col) - ord('A') + 1
                    if value is not None:  # Skip None values (empty cells)
                        worksheet.update_cell(row_number, col_num, value)

            return True
        except Exception as update_error:
            logger.error(f"Failed to update range '{range_str}': {str(update_error)}", exc_info=True)
            raise

    except Exception as e:
        logger.error(f"Error adding data for date {input_date}: {str(e)}", exc_info=True)
        return False


def find_row_by_date(worksheet: Any, input_date: str) -> Optional[int]:
    """
    Find row number by date in column A (similar to export-stats.php find_row_by_date).

    Args:
        worksheet: gspread worksheet object
        input_date: Date in m/d/Y format (e.g., "11/26/2025")

    Returns:
        Row number (1-indexed) or None if not found
    """
    try:
        logger.info(f"Finding row by date: {input_date} in worksheet '{worksheet.title}'")
        # Read column A from row 5 to row 40 (dates start at row 5 in the sheet)
        range_str = f"A5:A40"
        logger.info(f"Reading range: {range_str}")
        values = worksheet.get(range_str)
        logger.info(f"Found {len(values)} rows in range")

        if not values:
            logger.warning(f"No values found in range {range_str}")
            return None

        logger.info(f"Searching through {len(values)} rows for date matching '{input_date}'")
        found_dates = []

        for row_index, row in enumerate(values, start=5):
            if row and len(row) > 0:
                cell_value = str(row[0]).strip()
                if not cell_value:
                    continue

                found_dates.append(f"Row {row_index}: '{cell_value}'")

                # Try to parse the date from various formats
                try:
                    # Try "l, F d, Y" format (e.g., "Monday, November 26, 2025")
                    from datetime import datetime
                    date_parsed = datetime.strptime(cell_value, '%A, %B %d, %Y')
                    date_formatted = date_parsed.strftime('%m/%d/%Y')
                    if date_formatted == input_date or cell_value == input_date:
                        logger.info(f"✓ Found matching date at row {row_index}: '{cell_value}' matches '{input_date}'")
                        return row_index
                except Exception as parse_error:
                    # Try direct match
                    if cell_value == input_date:
                        logger.info(f"✓ Found exact match at row {row_index}: '{cell_value}' == '{input_date}'")
                        return row_index

        logger.warning(f"Date '{input_date}' not found. Available dates in sheet: {found_dates[:10]}...")  # Show first 10
        return None

    except Exception as e:
        logger.error(f"Error finding row by date {input_date}: {str(e)}", exc_info=True)
        return None


def _find_row_by_date_for_media(
    worksheet: Any,
    input_date: str,
    start_row: int = 39
) -> Optional[int]:
    """
    Find the row number for a given date in column A of a media sheet, starting from start_row.
    Similar to _find_row_by_date but for media sheets which start at row 39.

    Args:
        worksheet: gspread worksheet object
        input_date: Date string in format "MM/DD/YYYY" (e.g., "11/02/2025")
        start_row: Starting row to search from (default 39 for media sheets)

    Returns:
        Row number if found, None otherwise
    """
    try:
        # Read column A starting from start_row (e.g., A39:A70 for a month)
        # Read enough rows to cover a full month (32 rows should be enough)
        range_str = f"A{start_row}:A{start_row + 32}"
        logger.info(f"Reading range: {range_str}")

        values = worksheet.get(range_str)

        if not values:
            logger.warning(f"No values found in range {range_str}")
            return None

        logger.info(f"Searching through {len(values)} rows for date matching '{input_date}'")
        found_dates = []

        for row_index, row in enumerate(values, start=start_row):
            if row and len(row) > 0:
                cell_value = str(row[0]).strip()
                if not cell_value:
                    continue

                found_dates.append(f"Row {row_index}: '{cell_value}'")

                # Try to parse the date from various formats
                try:
                    # Try "l, F d, Y" format (e.g., "Saturday, November 01, 2025") - same as main sheet
                    from datetime import datetime
                    date_parsed = datetime.strptime(cell_value, '%A, %B %d, %Y')
                    date_formatted = date_parsed.strftime('%m/%d/%Y')
                    if date_formatted == input_date or cell_value == input_date:
                        logger.info(f"✓ Found matching date at row {row_index}: '{cell_value}' matches '{input_date}'")
                        return row_index
                except Exception as parse_error:
                    # Try "MM/DD/YYYY" format (e.g., "11/02/2025")
                    try:
                        from datetime import datetime
                        date_parsed = datetime.strptime(cell_value, '%m/%d/%Y')
                        date_formatted = date_parsed.strftime('%m/%d/%Y')
                        if date_formatted == input_date or cell_value == input_date:
                            logger.info(f"✓ Found matching date at row {row_index}: '{cell_value}' matches '{input_date}'")
                            return row_index
                    except Exception:
                        pass
                    # Try direct match
                    if cell_value == input_date:
                        logger.info(f"✓ Found exact match at row {row_index}: '{cell_value}' == '{input_date}'")
                        return row_index

        logger.warning(f"Date '{input_date}' not found. Available dates in sheet: {found_dates[:10]}...")  # Show first 10
        return None

    except Exception as e:
        logger.error(f"Error finding row by date {input_date}: {str(e)}", exc_info=True)
        return None


def add_media_data_for_date(
    client: Any,
    spreadsheet: Any,
    sheet_name: str,
    date_obj: datetime,
    media_data_to_export: List[Any]
) -> bool:
    """
    Add media data for a specific date to Google Sheets (similar to export-stats.php add_media_data_for_date).

    Args:
        client: Authenticated gspread client
        spreadsheet: Opened spreadsheet object
        sheet_name: Name of the sheet (e.g., "MEDIA_November'25")
        date_obj: Date object
        media_data_to_export: List of media data values [new_gravite_non_subscription, new_subscriptions, new_non_gravite_non_subscription]

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get or create the sheet
        logger.info(f"Getting or creating media sheet '{sheet_name}'")
        worksheet = None
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            logger.info(f"✓ Found existing media sheet: '{sheet_name}' (worksheet ID: {worksheet.id}, title: '{worksheet.title}')")
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f"Media sheet '{sheet_name}' not found, trying case-insensitive match...")
            # Try case-insensitive match
            all_worksheets = spreadsheet.worksheets()
            logger.info(f"Available sheets: {[ws.title for ws in all_worksheets]}")
            for ws in all_worksheets:
                if ws.title.lower() == sheet_name.lower():
                    worksheet = ws
                    logger.info(f"✓ Found existing media sheet (case-insensitive): '{ws.title}' (ID: {ws.id})")
                    break

            if not worksheet:
                logger.info(f"Media sheet '{sheet_name}' not found, creating new sheet...")
                worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
                logger.info(f"✓ Created new media sheet: '{sheet_name}' (ID: {worksheet.id})")

        # Find row by date in column A, starting from row 39 (where the 1st day of the month is)
        # Convert date to format matching what's in the sheet (e.g., "11/02/2025")
        converted_date = date_obj.strftime('%m/%d/%Y')
        logger.info(f"Finding row for date {converted_date} in media sheet '{sheet_name}' (worksheet title: '{worksheet.title}')")

        # Use _find_row_by_date but starting from row 39 instead of row 3
        row = _find_row_by_date_for_media(worksheet, converted_date, start_row=39)

        if row is None:
            logger.error(f"Could not find row for date {converted_date} in media sheet '{sheet_name}'")
            return False

        logger.info(f"Found row {row} for date {converted_date} in media sheet '{sheet_name}'")

        # Update data in row (columns B, C, D)
        # Use worksheet.update() directly like other features (Ulta, Inventory)
        range_str = f"B{row}:D{row}"

        try:
            # Try worksheet.update() first, but fall back to update_cell() if it fails
            # This handles apostrophes in sheet names (like Inventory Data does)
            try:
                # Add a small random delay to avoid concurrent write conflicts when multiple jobs run simultaneously
                delay = random.uniform(0.1, 0.5)  # 100-500ms random delay
                time.sleep(delay)
                worksheet.update(range_str, [media_data_to_export], value_input_option='RAW')
            except Exception as update_error:
                logger.warning(f"worksheet.update() failed: {update_error}, falling back to update_cell()")
                # Fall back to individual cell updates (like Inventory Data does)
                columns = ['B', 'C', 'D']
                for col, value in zip(columns, media_data_to_export):
                    col_num = ord(col) - ord('A') + 1
                    worksheet.update_cell(row, col_num, value)

            return True
        except Exception as update_error:
            logger.error(f"Failed to update media data range '{range_str}': {str(update_error)}", exc_info=True)
            raise

    except Exception as e:
        logger.error(f"Error adding media data for date: {str(e)}", exc_info=True)
        return False

