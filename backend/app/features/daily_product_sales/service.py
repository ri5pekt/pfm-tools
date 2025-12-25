import csv
import logging
import os
import requests
import base64
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Callable, Tuple
from zoneinfo import ZoneInfo
from collections import defaultdict

logger = logging.getLogger(__name__)

# Timezone offset in seconds (4 hours = Eastern Time offset)
# This matches the export-stats plugin's timezone handling
TIMEZONE_OFFSET_SECONDS = 4 * 3600  # 4 hours in seconds


def fetch_daily_product_sales_data(
    date_from: str,
    date_to: str,
    woo_base_url: str,
    woo_consumer_key: str,
    woo_consumer_secret: str,
    per_page: int = 300,
    update_progress: Optional[Callable[[int, str], None]] = None
) -> Dict[str, Any]:
    """
    Fetch orders and refunds from WooCommerce for a date range, aggregated by product.
    Fetches data per day to avoid server timeouts.

    Args:
        date_from: Start date in ISO format (YYYY-MM-DDTHH:MM:SSZ)
        date_to: End date in ISO format (YYYY-MM-DDTHH:MM:SSZ)
        woo_base_url: WooCommerce store base URL
        woo_consumer_key: WooCommerce API consumer key
        woo_consumer_secret: WooCommerce API consumer secret
        per_page: Maximum records to fetch per page (default 300 for efficiency)
        update_progress: Optional callback function(progress, message) to update progress

    Returns:
        Dictionary with product sales data aggregated by date and SKU
    """
    try:
        metorik_tz = ZoneInfo('America/New_York')

        # Parse date range
        date_from_dt_utc = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        date_to_dt_utc = datetime.fromisoformat(date_to.replace('Z', '+00:00'))

        # Interpret dates as Metorik timezone
        date_from_dt = datetime(
            date_from_dt_utc.year, date_from_dt_utc.month, date_from_dt_utc.day,
            0, 0, 0,
            tzinfo=metorik_tz
        )
        date_to_dt = datetime(
            date_to_dt_utc.year, date_to_dt_utc.month, date_to_dt_utc.day,
            23, 59, 59,
            tzinfo=metorik_tz
        )

        # Create Basic Auth header
        auth_string = f"{woo_consumer_key}:{woo_consumer_secret}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')

        # Create session
        session = requests.Session()
        session.headers.update({
            'Accept': '*/*',
            'User-Agent': 'curl/7.68.0',
            'Accept-Encoding': 'gzip, deflate',
            'Authorization': f'Basic {auth_b64}'
        })

        api_base = f"{woo_base_url.rstrip('/')}/wp-json/pfm-tools/v1"
        data_url = f"{api_base}/daily-product-sales"

        # Aggregate product sales by date and SKU.
        #
        # IMPORTANT ABOUT ORDERS COUNT:
        # The WP endpoint is paginated by *orders* (limit/page). Each order appears in exactly one page.
        # Therefore, the correct total "orders count" for an SKU across all pages is:
        #   sum(per_page_item_orders_count)
        # not a union of order_ids across pages (and we intentionally don't rely on order_ids).
        #
        # Structure: {date_str: {sku: {'gross_sales': float, 'orders_count': int, 'items': int, 'product_name': str}}}
        product_sales_by_date = defaultdict(lambda: defaultdict(lambda: {
            'gross_sales': 0.0,
            'orders_count': 0,
            'items': 0,
            'product_name': ''
        }))

        # Iterate through each day to avoid timeouts
        current_date = date_from_dt
        total_days = (date_to_dt.date() - date_from_dt.date()).days + 1
        day_num = 0

        while current_date <= date_to_dt:
            day_num += 1
            day_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            after_date = day_start.strftime('%Y-%m-%d %H:%M:%S')
            before_date = day_end.strftime('%Y-%m-%d %H:%M:%S')

            date_key = day_start.strftime('%Y-%m-%d')

            logger.info(f"Fetching product sales for {date_key} ({day_num}/{total_days})")

            if update_progress:
                progress = int((day_num / total_days) * 90)
                update_progress(progress, f'Fetching data for {date_key} ({day_num}/{total_days})...')

            # Fetch all pages for this day
            page_num = 1
            while True:
                params = {
                    'date_after': after_date,
                    'date_before': before_date,
                    'per_page': per_page,
                    'page': page_num,
                }

                max_retries = 3
                retry_delay = 2
                last_exception = None

                for attempt in range(max_retries):
                    try:
                        response = session.get(data_url, params=params, timeout=300)
                        response.raise_for_status()
                        last_exception = None
                        break
                    except requests.exceptions.Timeout as e:
                        last_exception = e
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1)
                            logger.warning(f"Timeout fetching page {page_num} for {date_key} (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                            time.sleep(wait_time)
                        else:
                            raise
                    except requests.exceptions.RequestException as e:
                        last_exception = e
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1)
                            logger.warning(f"Error fetching page {page_num} for {date_key} (attempt {attempt + 1}/{max_retries}): {str(e)}, retrying in {wait_time}s...")
                            time.sleep(wait_time)
                        else:
                            raise

                if last_exception:
                    raise last_exception

                data = response.json()
                products = data.get('products', [])

                # Process products for this day
                for product in products:
                    sku = product.get('sku', '')
                    if not sku:
                        continue

                    # Ensure SKU is a string
                    sku = str(sku).strip()
                    if not sku:
                        continue

                    product_name = product.get('product_name', '')
                    gross_sales = float(product.get('gross_sales', 0))
                    per_page_orders_count = product.get('item_orders_count', product.get('orders_count', 0))
                    items = int(product.get('items', 0))

                    product_sales_by_date[date_key][sku]['gross_sales'] += gross_sales
                    try:
                        product_sales_by_date[date_key][sku]['orders_count'] += int(per_page_orders_count or 0)
                    except Exception:
                        # If malformed, ignore (shouldn't happen)
                        pass
                    product_sales_by_date[date_key][sku]['items'] += items
                    if not product_sales_by_date[date_key][sku]['product_name']:
                        product_sales_by_date[date_key][sku]['product_name'] = product_name

                # Check if more pages
                total_pages = int(response.headers.get('X-WP-TotalPages', 1))
                if page_num >= total_pages or len(products) == 0:
                    break

                page_num += 1

            # Move to next day
            current_date = day_end

        session.close()

        # Finalize result
        result = {}
        for date_key, sku_data in product_sales_by_date.items():
            result[date_key] = {}
            for sku, data in sku_data.items():
                result[date_key][sku] = {
                    'gross_sales': data['gross_sales'],
                    'orders_count': int(data.get('orders_count', 0) or 0),
                    'item_orders_count': int(data.get('orders_count', 0) or 0),
                    'items': data['items'],
                    'product_name': data['product_name']
                }

        logger.info(f"Successfully fetched product sales data for {total_days} days")
        return {
            'product_sales': result,
            'date_from': date_from,
            'date_to': date_to,
            'total_days': total_days
        }

    except Exception as e:
        logger.error(f"Error fetching daily product sales data: {str(e)}", exc_info=True)
        raise


def save_daily_product_sales_to_csv(
    data: Dict[str, Any],
    output_path: str,
    update_progress: Optional[Callable[[int, str], None]] = None
) -> str:
    """
    Save product sales data to CSV file in the required format:
    - Row 1: SKUs (Column A empty, then SKU values)
    - Row 2: Headers (Column A: "Date", then for each product: "Product Name - Gross Sales", "Product Name - Orders", "Product Name - Items")
    - Row 3+: Data rows (Column A: date, then values for each product's 3 columns)

    Args:
        data: Product sales data from fetch_daily_product_sales_data
        output_path: Path where CSV should be saved
        update_progress: Optional callback function(progress, message) to update progress

    Returns:
        Path to saved CSV file
    """
    logger.info(f"Saving daily product sales to CSV: {output_path}")

    product_sales = data.get('product_sales', {})

    if not product_sales:
        # Create empty CSV with minimal structure
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([''])  # Row 1: Empty SKU row
            writer.writerow(['Date'])  # Row 2: Header row with just Date
            writer.writerow(['No product sales found for the selected date range'])
        logger.info(f"Created empty CSV file: {output_path}")
        return output_path

    # Collect all unique SKUs and their product names across all dates.
    # If we ever see a better product name for an SKU (existing name is empty/placeholder), update it.
    sku_info = {}  # {sku: product_name}
    for date_key, sku_data in product_sales.items():
        for sku, sales_data in sku_data.items():
            sku_str = str(sku).strip()
            if not sku_str:
                continue
            candidate_name = (sales_data.get('product_name', '') or '').strip()
            if sku_str not in sku_info:
                sku_info[sku_str] = candidate_name or sku_str
            else:
                existing_name = (sku_info.get(sku_str, '') or '').strip()
                if (not existing_name) or (existing_name == sku_str):
                    if candidate_name:
                        sku_info[sku_str] = candidate_name

    # Sort SKUs for consistent column order
    sorted_skus = sorted(sku_info.keys())

    if update_progress:
        update_progress(95, 'Writing CSV file...')

    # Write CSV
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)

        # Row 1: SKUs (Column A empty, then SKU values)
        # Each product has 3 columns in row 2 (Gross Sales, Orders, Items)
        # SKUs align with the first column of each product group (Gross Sales column)
        # Format: ['', SKU1, '', '', SKU2, '', '', SKU3, '', '', ...]
        # This means: SKU in first column of product, then 2 empty cells, then next SKU
        # Ensure SKUs are written as strings (not numbers) - use leading apostrophe like Inventory Data
        sku_row = ['']  # Column A empty
        for sku in sorted_skus:
            # Convert SKU to string with leading apostrophe to force Excel/Google Sheets to treat it as text
            # This prevents numeric SKUs from being converted to numbers (same approach as Inventory Data)
            sku_str = f"'{str(sku)}"
            sku_row.append(sku_str)  # SKU aligns with Gross Sales column
            sku_row.append('')    # Empty (for Orders column in row 2)
            sku_row.append('')    # Empty (for Items column in row 2)
        writer.writerow(sku_row)

        # Row 2: Headers (Column A: "Date", then for each product: "Product Name - Gross Sales", "Product Name - Orders", "Product Name - Items")
        header_row = ['Date']
        for sku in sorted_skus:
            product_name = sku_info[sku]
            header_row.append(f'{product_name} - Gross Sales')
            header_row.append(f'{product_name} - Orders')
            header_row.append(f'{product_name} - Items')
        writer.writerow(header_row)

        # Row 3+: Data rows (sorted by date)
        sorted_dates = sorted(product_sales.keys())
        for date_key in sorted_dates:
            date_formatted = datetime.strptime(date_key, '%Y-%m-%d').strftime('%m/%d/%Y')
            row = [date_formatted]

            for sku in sorted_skus:
                sales_data = product_sales[date_key].get(sku, {})
                gross_sales = round(sales_data.get('gross_sales', 0), 2)
                orders_count = sales_data.get('orders_count', 0)
                items = sales_data.get('items', 0)
                row.append(gross_sales)
                row.append(orders_count)
                row.append(items)

            writer.writerow(row)

    logger.info(f"CSV file saved: {output_path}")
    return output_path


def fetch_single_day_product_sales(
    date_str: str,
    woo_base_url: str,
    woo_consumer_key: str,
    woo_consumer_secret: str,
    per_page: int = 300
) -> Dict[str, Dict[str, Any]]:
    """
    Fetch product sales data for a single day.

    Args:
        date_str: Date in YYYY-MM-DD format
        woo_base_url: WooCommerce store base URL
        woo_consumer_key: WooCommerce API consumer key
        woo_consumer_secret: WooCommerce API secret
        per_page: Maximum records to fetch per page

    Returns:
        Dictionary with product sales data for that day: {sku: {'gross_sales': float, 'orders_count': int, 'items': int, 'product_name': str}}
    """
    try:
        metorik_tz = ZoneInfo('America/New_York')

        # Parse date
        date_dt = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=metorik_tz)
        day_start = date_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        after_date = day_start.strftime('%Y-%m-%d %H:%M:%S')
        before_date = day_end.strftime('%Y-%m-%d %H:%M:%S')

        # Create Basic Auth header
        auth_string = f"{woo_consumer_key}:{woo_consumer_secret}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')

        # Create session
        session = requests.Session()
        session.headers.update({
            'Accept': '*/*',
            'User-Agent': 'curl/7.68.0',
            'Accept-Encoding': 'gzip, deflate',
            'Authorization': f'Basic {auth_b64}'
        })

        api_base = f"{woo_base_url.rstrip('/')}/wp-json/pfm-tools/v1"
        data_url = f"{api_base}/daily-product-sales"

        # Aggregate products by SKU.
        #
        # IMPORTANT ABOUT ORDERS COUNT:
        # The WP endpoint is paginated by *orders* (limit/page). Each order appears in exactly one page.
        # Therefore, the correct total "orders count" for an SKU across all pages is:
        #   sum(per_page_item_orders_count)
        # not a union of order_ids across pages (and we intentionally don't return order_ids anymore).
        products_by_sku = defaultdict(lambda: {
            'gross_sales': 0.0,
            'orders_count': 0,  # summed across pages
            'items': 0,
            'product_name': ''
        })

        # Fetch all pages for this day
        page_num = 1
        while True:
            params = {
                'date_after': after_date,
                'date_before': before_date,
                'per_page': per_page,
                'page': page_num,
            }

            max_retries = 3
            retry_delay = 2
            last_exception = None

            for attempt in range(max_retries):
                try:
                    response = session.get(data_url, params=params, timeout=300)
                    response.raise_for_status()
                    last_exception = None
                    break
                except requests.exceptions.Timeout as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        logger.warning(f"Timeout fetching page {page_num} for {date_str} (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        raise
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        logger.warning(f"Error fetching page {page_num} for {date_str} (attempt {attempt + 1}/{max_retries}): {str(e)}, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        raise

            if last_exception:
                raise last_exception

            data = response.json()
            products = data.get('products', [])

            # Process products
            for product in products:
                sku = product.get('sku', '')
                if not sku:
                    continue

                # Normalize SKU: trim whitespace and convert to string for consistent matching
                sku = str(sku).strip()
                if not sku:
                    continue

                product_name = product.get('product_name', '')
                gross_sales = float(product.get('gross_sales', 0))
                # Prefer item_orders_count (per-page unique order count for this SKU)
                per_page_orders_count = product.get('item_orders_count', product.get('orders_count', 0))
                items = int(product.get('items', 0))

                # Initialize if not exists (only set product_name on first creation)
                if sku not in products_by_sku:
                    products_by_sku[sku] = {
                        'gross_sales': 0.0,
                        'orders_count': 0,
                        'items': 0,
                        'product_name': product_name  # Set title only on first creation
                    }

                # Aggregate data (only compare by SKU when updating)
                products_by_sku[sku]['gross_sales'] += gross_sales
                try:
                    products_by_sku[sku]['orders_count'] += int(per_page_orders_count or 0)
                except Exception:
                    # If malformed, ignore (shouldn't happen)
                    pass
                products_by_sku[sku]['items'] += items
                # Only update product_name if it's empty (preserve first one found)
                if not products_by_sku[sku]['product_name'] and product_name:
                    products_by_sku[sku]['product_name'] = product_name

            # Check if more pages
            total_pages = int(response.headers.get('X-WP-TotalPages', 1))
            if page_num >= total_pages or len(products) == 0:
                break

            page_num += 1

        session.close()

        # Convert to final schema
        result = {}
        for sku, data in products_by_sku.items():
            orders_count = int(data.get('orders_count', 0) or 0)
            result[sku] = {
                'gross_sales': data['gross_sales'],
                'orders_count': orders_count,
                'item_orders_count': orders_count,  # Alias for orders_count
                'items': data['items'],
                'product_name': data['product_name']
            }

        return result

    except Exception as e:
        logger.error(f"Error fetching product sales for {date_str}: {str(e)}", exc_info=True)
        raise


def export_single_day_to_google_sheets(
    date_str: str,
    day_data: Dict[str, Dict[str, Any]],
    spreadsheet_id: str,
    client=None,
    worksheet=None,
    oauth_credentials_path: str = None,
    oauth_token_path: str = None,
    service_account_path: str = None,
    update_progress: Optional[Callable[[int, str], None]] = None
) -> Tuple[object, object]:
    """
    Export a single day's product sales data to Google Sheets incrementally.
    Returns the client and worksheet objects for reuse.

    Args:
        date_str: Date in YYYY-MM-DD format
        day_data: Product sales data for that day: {sku: {'gross_sales': float, 'orders_count': int, 'items': int, 'product_name': str}}
        spreadsheet_id: Google Sheets spreadsheet ID
        client: Existing gspread client (if None, will create new)
        worksheet: Existing worksheet (if None, will get/create)
        oauth_credentials_path: Path to OAuth client credentials JSON file
        oauth_token_path: Path to saved OAuth token file
        service_account_path: Path to service account JSON file
        update_progress: Optional callback function(progress, message) to update progress

    Returns:
        Tuple of (client, worksheet) for reuse in subsequent calls
    """
    import gspread
    import pickle
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import Request

    try:
        # Authenticate if client not provided
        if client is None:
            scope = ['https://www.googleapis.com/auth/spreadsheets',
                     'https://www.googleapis.com/auth/drive']

            creds = None

            # Try OAuth authentication first
            if oauth_credentials_path and oauth_token_path and os.path.exists(oauth_token_path):
                try:
                    with open(oauth_token_path, 'rb') as token:
                        creds = pickle.load(token)

                    if creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                        with open(oauth_token_path, 'wb') as token:
                            pickle.dump(creds, token)
                except Exception as e:
                    logger.warning(f"Could not load OAuth token: {e}")
                    creds = None

            # Fall back to service account authentication
            if not creds and service_account_path and os.path.exists(service_account_path):
                try:
                    creds = Credentials.from_service_account_file(service_account_path, scopes=scope)
                except Exception as e:
                    logger.warning(f"Could not load service account credentials: {e}")
                    creds = None

            if not creds:
                logger.error("No valid Google credentials found.")
                return None, None

            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(spreadsheet_id)

            try:
                worksheet = spreadsheet.sheet1
            except:
                worksheet = spreadsheet.add_worksheet(title="Daily Product Sales", rows=1000, cols=100)

        # Get existing data
        existing_data = worksheet.get_all_values()

        # Parse existing structure
        existing_skus = []
        existing_sku_product_names = {}
        existing_dates = set()
        date_row_map = {}

        def _is_placeholder_title(title: str, sku: str) -> bool:
            t = (title or '').strip()
            s = (sku or '').strip()
            if not t:
                return True
            if s and t == s:
                return True
            if s and t.lower() == s.lower():
                return True
            if t.lower().startswith('sku '):
                return True
            if t.lower() in {'unknown', 'n/a', 'na'}:
                return True
            return False

        if len(existing_data) >= 2:
            # Row 1: SKUs
            if len(existing_data[0]) > 1:
                row1 = existing_data[0]
                for col_idx in range(1, len(row1), 3):
                    sku = row1[col_idx]
                    if sku:
                        sku_str = str(sku).strip().lstrip("'")
                        if sku_str:
                            existing_skus.append(sku_str)

            # Row 2: Headers - extract product names
            if len(existing_data) >= 2 and len(existing_data[1]) > 1:
                headers = existing_data[1][1:]
                for sku_idx, sku in enumerate(existing_skus):
                    header_idx = sku_idx * 3
                    if header_idx < len(headers):
                        header = headers[header_idx]
                        if header and " - Gross Sales" in header:
                            product_name = header.replace(" - Gross Sales", "").strip()
                            existing_sku_product_names[sku] = product_name

            # Row 3+: Data rows
            for row_idx in range(2, len(existing_data)):
                row = existing_data[row_idx]
                if row and row[0]:
                    date_str_existing = row[0]
                    existing_dates.add(date_str_existing)
                    date_row_map[date_str_existing] = row_idx + 1

        # Collect SKUs from new day data
        new_sku_info = {}
        for sku, sales_data in day_data.items():
            sku_str = str(sku)
            if sku_str not in new_sku_info:
                new_sku_info[sku_str] = sales_data.get('product_name', sku_str)

        # Determine all SKUs (existing + new)
        all_skus = list(set([str(s) for s in existing_skus] + list(new_sku_info.keys())))
        all_skus.sort()

        # Merge product names.
        # Prefer existing names unless they look like placeholders; in that case, use the new name.
        all_sku_product_names = {}
        for sku in all_skus:
            existing_name = existing_sku_product_names.get(sku, '')
            new_name = new_sku_info.get(sku, '')
            if existing_name and not _is_placeholder_title(existing_name, sku):
                all_sku_product_names[sku] = existing_name
            elif new_name:
                all_sku_product_names[sku] = new_name
            else:
                all_sku_product_names[sku] = existing_name or sku

        # Add new SKUs as columns if needed
        new_skus = [sku for sku in all_skus if sku not in existing_skus]
        # Also update headers if we have better titles for existing SKUs (placeholder -> real title).
        header_needs_update = False
        for sku in all_skus:
            existing_name = existing_sku_product_names.get(sku, '')
            desired_name = all_sku_product_names.get(sku, sku)
            if _is_placeholder_title(existing_name, sku) and desired_name and desired_name != existing_name:
                header_needs_update = True
                break

        if new_skus or header_needs_update:
            logger.info(f"Adding {len(new_skus)} new SKUs for date {date_str}")

            # Update Row 1: SKUs
            sku_row = ['']
            for sku in all_skus:
                sku_str = f"'{str(sku)}"
                sku_row.append(sku_str)
                sku_row.append('')
                sku_row.append('')

            if len(existing_data) == 0:
                worksheet.append_row(sku_row)
            else:
                worksheet.update('A1', [sku_row])

            # Update Row 2: Headers (ensure SKU titles match)
            header_row = ['Date']
            for sku in all_skus:
                product_name = all_sku_product_names.get(sku, sku)
                header_row.append(f'{product_name} - Gross Sales')
                header_row.append(f'{product_name} - Orders')
                header_row.append(f'{product_name} - Items')

            if len(existing_data) < 2:
                worksheet.append_row(header_row)
            else:
                worksheet.update('A2', [header_row])

            # Re-read existing data after header updates
            existing_data = worksheet.get_all_values()
            existing_dates = set()
            date_row_map = {}
            for row_idx in range(2, len(existing_data)):
                row = existing_data[row_idx]
                if row and row[0]:
                    date_str_existing = row[0]
                    existing_dates.add(date_str_existing)
                    date_row_map[date_str_existing] = row_idx + 1

        # Format date for Google Sheets (MM/DD/YYYY)
        date_formatted = datetime.strptime(date_str, '%Y-%m-%d').strftime('%m/%d/%Y')

        # Build row data for this day
        row_data = [date_formatted]
        for sku in all_skus:
            sales_data = day_data.get(sku, {})
            gross_sales = round(sales_data.get('gross_sales', 0), 2)
            orders_count = sales_data.get('orders_count', 0)
            items = sales_data.get('items', 0)
            row_data.append(gross_sales)
            row_data.append(orders_count)
            row_data.append(items)

        # Update or append row
        if date_formatted in existing_dates:
            # Update existing row
            row_idx = date_row_map[date_formatted]
            worksheet.update(f'A{row_idx}', [row_data])
            logger.info(f"Updated row for date {date_formatted}")
        else:
            # Append new row
            worksheet.append_row(row_data)
            logger.info(f"Appended new row for date {date_formatted}")

        return client, worksheet

    except Exception as e:
        logger.error(f"Error exporting day {date_str} to Google Sheets: {str(e)}", exc_info=True)
        return client, worksheet  # Return what we have even on error


def export_product_sales_to_google_sheets(
    data: Dict[str, Any],
    spreadsheet_id: str,
    oauth_credentials_path: str = None,
    oauth_token_path: str = None,
    service_account_path: str = None,
    update_progress: Optional[Callable[[int, str], None]] = None
) -> bool:
    """
    Export product sales data to Google Sheets in the same format as CSV.
    Handles existing SKUs and dates - adds new SKUs as columns, adds new dates as rows.

    Args:
        data: Product sales data from fetch_daily_product_sales_data
        spreadsheet_id: Google Sheets spreadsheet ID
        oauth_credentials_path: Path to OAuth client credentials JSON file
        oauth_token_path: Path to saved OAuth token file
        service_account_path: Path to service account JSON file
        update_progress: Optional callback function(progress, message) to update progress

    Returns:
        True if successful, False otherwise
    """
    import gspread
    import pickle
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import Request

    logger.info(f"Exporting product sales to Google Sheets: {spreadsheet_id}")
    logger.info(f"OAuth credentials path: {oauth_credentials_path}")
    logger.info(f"OAuth token path: {oauth_token_path}")
    logger.info(f"Service account path: {service_account_path}")

    try:
        # Authenticate with Google Sheets
        scope = ['https://www.googleapis.com/auth/spreadsheets',
                 'https://www.googleapis.com/auth/drive']

        creds = None
        auth_method = None

        # Try OAuth authentication first
        if oauth_credentials_path and oauth_token_path:
            logger.info(f"Checking OAuth token file: {oauth_token_path}, exists: {os.path.exists(oauth_token_path) if oauth_token_path else False}")
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
                        logger.info("OAuth token refreshed successfully")

                    if creds.valid:
                        auth_method = "OAuth"
                        logger.info("OAuth authentication successful")
                    else:
                        logger.warning("OAuth credentials are not valid")
                except Exception as e:
                    logger.warning(f"Could not load OAuth token: {e}", exc_info=True)
                    creds = None
            else:
                logger.warning(f"OAuth token file does not exist: {oauth_token_path}")

        # Fall back to service account authentication
        if not creds and service_account_path:
            logger.info(f"Checking service account file: {service_account_path}, exists: {os.path.exists(service_account_path) if service_account_path else False}")
            if os.path.exists(service_account_path):
                try:
                    logger.info(f"Attempting service account authentication: {service_account_path}")
                    creds = Credentials.from_service_account_file(service_account_path, scopes=scope)
                    auth_method = "Service Account"
                    logger.info("Service account authentication successful")
                except Exception as e:
                    logger.warning(f"Could not load service account credentials: {e}", exc_info=True)
                    creds = None
            else:
                logger.warning(f"Service account file does not exist: {service_account_path}")

        if not creds:
            logger.error("No valid Google credentials found. Cannot export to Google Sheets.")
            logger.error("Please configure either OAuth credentials or service account credentials.")
            return False

        logger.info(f"Using {auth_method} authentication method")

        # Authorize gspread client
        logger.info("Authorizing gspread client...")
        client = gspread.authorize(creds)
        logger.info("Gspread client authorized successfully")

        logger.info(f"Opening spreadsheet with ID: {spreadsheet_id}")
        spreadsheet = client.open_by_key(spreadsheet_id)
        logger.info(f"Successfully opened spreadsheet: {spreadsheet.title}")

        # Use the first sheet (or create one if it doesn't exist)
        logger.info("Accessing worksheet...")
        try:
            worksheet = spreadsheet.sheet1
            logger.info(f"Using existing worksheet: {worksheet.title}")
        except Exception as e:
            logger.info(f"First sheet not accessible ({e}), creating new worksheet...")
            worksheet = spreadsheet.add_worksheet(title="Daily Product Sales", rows=1000, cols=100)
            logger.info("Created new worksheet: Daily Product Sales")

        # Get existing data
        logger.info("Reading existing data from worksheet...")
        existing_data = worksheet.get_all_values()
        logger.info(f"Found {len(existing_data)} existing rows in worksheet")

        # Parse existing structure
        existing_skus = []
        existing_sku_product_names = {}  # {sku: product_name} from existing headers
        existing_dates = set()
        date_row_map = {}  # {date_str: row_index}

        if len(existing_data) >= 2:
            # Row 1: SKUs are in every 3rd column starting from column B (index 1)
            # Format: '', SKU1, '', '', SKU2, '', '', SKU3, '', '', ...
            if len(existing_data[0]) > 1:
                row1 = existing_data[0]
                # Extract SKUs from columns B, E, H, etc. (every 3rd column starting from index 1)
                for col_idx in range(1, len(row1), 3):
                    sku = row1[col_idx]
                    if sku:
                        # Convert to string, strip whitespace, and remove leading apostrophe if present
                        # (SKUs are stored with leading apostrophe to force text format)
                        sku_str = str(sku).strip().lstrip("'")
                        if sku_str:
                            existing_skus.append(sku_str)

            # Row 2: Headers - extract product names
            # Headers are in format: "Product Name - Gross Sales", "Product Name - Orders", "Product Name - Items"
            # Process in groups of 3 (each SKU has 3 columns)
            if len(existing_data) >= 2 and len(existing_data[1]) > 1:
                headers = existing_data[1][1:]  # Skip first column (Date)
                # Headers are in groups of 3, so we need to map them to SKUs
                # SKUs are in row 1 at columns B, E, H, etc. (every 3rd column)
                # Headers start at column B and are in groups of 3
                for sku_idx, sku in enumerate(existing_skus):
                    header_idx = sku_idx * 3
                    if header_idx < len(headers):
                        header = headers[header_idx]
                        # Extract product name by removing " - Gross Sales" suffix
                        if header and " - Gross Sales" in header:
                            product_name = header.replace(" - Gross Sales", "").strip()
                            existing_sku_product_names[sku] = product_name

            # Row 3+: Data rows
            for row_idx in range(2, len(existing_data)):
                row = existing_data[row_idx]
                if row and row[0]:  # Has date in first column
                    date_str = row[0]
                    existing_dates.add(date_str)
                    date_row_map[date_str] = row_idx + 1  # 1-indexed

        # Collect all SKUs from new data
        product_sales = data.get('product_sales', {})
        new_sku_info = {}  # {sku: product_name}
        for date_key, sku_data in product_sales.items():
            for sku, sales_data in sku_data.items():
                # Ensure SKU is a string
                sku_str = str(sku)
                if sku_str not in new_sku_info:
                    new_sku_info[sku_str] = sales_data.get('product_name', sku_str)

        # Determine all SKUs (existing + new) - ensure all are strings
        all_skus = list(set([str(s) for s in existing_skus] + list(new_sku_info.keys())))
        all_skus.sort()  # Sort for consistent order

        # Merge product names (existing takes precedence, then new)
        all_sku_product_names = {}
        for sku in all_skus:
            if sku in existing_sku_product_names:
                all_sku_product_names[sku] = existing_sku_product_names[sku]
            elif sku in new_sku_info:
                all_sku_product_names[sku] = new_sku_info[sku]
            else:
                all_sku_product_names[sku] = sku  # Fallback to SKU

        # Add new SKUs as columns if needed
        logger.info(f"Existing SKUs: {existing_skus}")
        logger.info(f"New SKUs from data: {list(new_sku_info.keys())}")
        logger.info(f"All SKUs (merged): {all_skus}")
        new_skus = [sku for sku in all_skus if sku not in existing_skus]
        logger.info(f"New SKUs to add: {new_skus}")
        if new_skus:
            logger.info(f"Adding {len(new_skus)} new SKUs as columns")
            if update_progress:
                update_progress(50, f'Adding {len(new_skus)} new SKUs...')

            # Update Row 1: SKUs in format: '', SKU1, '', '', SKU2, '', '', ...
            # Ensure SKUs are written as strings (not numbers) - use leading apostrophe like Inventory Data
            logger.info(f"Updating Row 1 with {len(all_skus)} SKUs")
            sku_row = ['']  # Column A empty
            for sku in all_skus:
                # Convert SKU to string with leading apostrophe to force Google Sheets to treat it as text
                # This prevents numeric SKUs from being converted to numbers (same approach as Inventory Data)
                sku_str = f"'{str(sku)}"
                sku_row.append(sku_str)  # SKU aligns with Gross Sales column
                sku_row.append('')    # Empty (for Orders column)
                sku_row.append('')    # Empty (for Items column)

            if len(existing_data) == 0:
                # Create new sheet
                worksheet.append_row(sku_row)
            else:
                # Update existing row 1
                worksheet.update('A1', [sku_row])

            # Update Row 2: Headers
            header_row = ['Date']
            for sku in all_skus:
                product_name = all_sku_product_names.get(sku, sku)
                header_row.append(f'{product_name} - Gross Sales')
                header_row.append(f'{product_name} - Orders')
                header_row.append(f'{product_name} - Items')

            if len(existing_data) < 2:
                worksheet.append_row(header_row)
            else:
                worksheet.update('A2', [header_row])

        # Add/update data rows
        logger.info(f"Preparing to add/update data for {len(product_sales)} dates")
        sorted_dates = sorted(product_sales.keys())
        logger.info(f"Sorted dates: {sorted_dates}")
        new_rows = []
        updated_rows = []

        for date_key in sorted_dates:
            # Format date to match existing format (MM/DD/YYYY)
            date_formatted = datetime.strptime(date_key, '%Y-%m-%d').strftime('%m/%d/%Y')

            # Build row data
            row_data = [date_formatted]
            for sku in all_skus:
                sales_data = product_sales[date_key].get(sku, {})
                row_data.append(round(sales_data.get('gross_sales', 0), 2))
                row_data.append(sales_data.get('orders_count', 0))
                row_data.append(sales_data.get('items', 0))

            if date_formatted in existing_dates:
                # Update existing row
                row_idx = date_row_map[date_formatted]
                updated_rows.append((row_idx, row_data))
            else:
                # New row
                new_rows.append(row_data)

        # Update existing rows
        if updated_rows:
            logger.info(f"Updating {len(updated_rows)} existing date rows")
            if update_progress:
                update_progress(85, f'Updating {len(updated_rows)} existing rows...')
            for row_idx, row_data in updated_rows:
                range_name = f'A{row_idx}'
                logger.debug(f"Updating row {row_idx} with data: {row_data[:5]}...")  # Log first 5 columns
                worksheet.update(range_name, [row_data])
            logger.info(f"Successfully updated {len(updated_rows)} existing rows")

        # Append new rows
        if new_rows:
            logger.info(f"Adding {len(new_rows)} new date rows")
            if update_progress:
                update_progress(90, f'Adding {len(new_rows)} new date rows...')
            logger.debug(f"New rows to append: {[row[0] for row in new_rows]}")  # Log dates
            worksheet.append_rows(new_rows)
            logger.info(f"Successfully appended {len(new_rows)} new rows")

        logger.info(f"Successfully exported product sales data to Google Sheets")
        return True

    except Exception as e:
        logger.error(f"Error exporting to Google Sheets: {str(e)}", exc_info=True)
        return False

