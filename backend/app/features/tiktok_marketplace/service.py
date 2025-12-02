import csv
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from zoneinfo import ZoneInfo
from .orderdesk_client import OrderDeskAPIClient

logger = logging.getLogger(__name__)


def convert_iso_to_orderdesk_date(iso_date_str: str) -> str:
    """
    Convert ISO date string to Order Desk date format.
    Order Desk accepts: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS

    Args:
        iso_date_str: ISO format date string (e.g., 2025-11-01T00:00:00Z)

    Returns:
        Order Desk format date string (YYYY-MM-DD HH:MM:SS)
    """
    try:
        # Parse ISO format
        if '.' in iso_date_str and 'Z' in iso_date_str:
            # Remove milliseconds
            iso_date_str = iso_date_str.split('.')[0] + 'Z'

        dt = datetime.fromisoformat(iso_date_str.replace('Z', '+00:00'))
        # Convert to UTC if not already
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc)
        else:
            dt = dt.replace(tzinfo=timezone.utc)

        # Format as Order Desk expects: YYYY-MM-DD HH:MM:SS
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        logger.warning(f"Could not parse date '{iso_date_str}': {e}, using as-is")
        return iso_date_str


def fetch_tiktok_orders(
    start_date: str,
    end_date: str,
    store_id: str,
    api_key: str,
    base_url: str = None,
    limit: int = 100,
    offset: int = 0,
    progress_callback: callable = None
) -> Dict[str, Any]:
    """
    Fetch TikTok orders from Order Desk API with pagination support.

    Args:
        start_date: Start date in ISO format (e.g., 2025-11-01T00:00:00Z)
        end_date: End date in ISO format (e.g., 2025-11-01T23:59:00Z)
        store_id: Order Desk Store ID
        api_key: Order Desk API Key
        base_url: Order Desk API base URL (optional, defaults to https://app.orderdesk.me/api/v2)
        limit: Maximum records to fetch per page (default: 100, max: 1000)
        offset: Pagination offset

    Returns:
        Dictionary with orders data (all pages combined)
    """
    client = OrderDeskAPIClient(store_id=store_id, api_key=api_key, base_url=base_url)
    try:
        all_orders = []
        current_offset = offset

        # Convert ISO dates to Order Desk format (UTC)
        # Order Desk API expects: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS in UTC
        # TikTok groups orders by Eastern time date (America/New_York), so we need to fetch orders that fall on the selected Eastern date
        # The frontend sends dates converted from Chicago time to UTC, but we convert to Eastern for grouping
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if start_dt.tzinfo:
            start_dt = start_dt.astimezone(timezone.utc)
        else:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        if end_dt.tzinfo:
            end_dt = end_dt.astimezone(timezone.utc)
        else:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        # Convert to Eastern time to determine the actual date range
        # TikTok groups orders by Eastern time date (America/New_York)
        eastern_tz = ZoneInfo("America/New_York")
        start_eastern = start_dt.astimezone(eastern_tz)
        end_eastern = end_dt.astimezone(eastern_tz)

        # Check if this is a single-day export
        # The frontend always adds 1 day to the end date, so we need to detect single-day exports
        # by checking if the dates are consecutive and the time span is less than ~25 hours
        # (frontend typically creates a ~24 hour range for single-day exports)
        start_eastern_date = start_eastern.date()
        end_eastern_date = end_eastern.date()
        time_diff = end_dt - start_dt

        # If dates are the same, it's definitely a single-day export
        # If dates are consecutive (1 day apart) and time difference is less than 25 hours,
        # it's likely a single-day export where frontend added 1 day to end date
        is_single_day = (
            start_eastern_date == end_eastern_date or
            ((end_eastern_date - start_eastern_date).days == 1 and time_diff.total_seconds() < 25 * 3600)
        )

        if is_single_day:
            # Single day export - only fetch the start date's day
            start_eastern_day = start_eastern.replace(hour=0, minute=0, second=0, microsecond=0)
            end_eastern_day = start_eastern.replace(hour=23, minute=59, second=59, microsecond=0)
            logger.info(f"Detected single-day export: only fetching orders for Eastern date {start_eastern_date}")
        else:
            # Multi-day export - fetch full range
            start_eastern_day = start_eastern.replace(hour=0, minute=0, second=0, microsecond=0)
            end_eastern_day = end_eastern.replace(hour=23, minute=59, second=59, microsecond=0)

        start_utc = start_eastern_day.astimezone(timezone.utc)
        end_utc = end_eastern_day.astimezone(timezone.utc)

        start_date_od = start_utc.strftime('%Y-%m-%d %H:%M:%S')
        end_date_od = end_utc.strftime('%Y-%m-%d %H:%M:%S')

        logger.info(f"Fetching TikTok orders from Order Desk: {start_date_od} to {end_date_od} (UTC, covering Eastern dates {start_eastern_day.date()} to {end_eastern_day.date()})")

        # Fetch orders from folders: New, Prepared, Closed
        # We'll need to fetch from each folder separately or use folder_name parameter
        folder_names = ["New", "Prepared", "Closed"]

        for folder_name in folder_names:
            logger.info(f"Fetching orders from folder: {folder_name}")
            current_offset = offset

            while True:
                response = client.get_orders(
                    search_start_date=start_date_od,
                    search_end_date=end_date_od,
                    limit=min(limit, 500),  # Order Desk max is 500
                    offset=current_offset,
                    folder_name=folder_name,
                    source_name="TikTok Shop US"  # Filter for TikTok orders
                )

                # Order Desk returns orders in 'orders' key
                orders = response.get('orders', [])

                # Filter to ensure we only get TikTok orders (in case source_name filter doesn't work)
                tiktok_orders = [
                    order for order in orders
                    if order.get('source_name', '').startswith('TikTok')
                ]

                all_orders.extend(tiktok_orders)

                logger.info(f"Fetched {len(orders)} orders from {folder_name} (offset {current_offset}), {len(tiktok_orders)} TikTok orders, total so far: {len(all_orders)}")

                # Check if we've got all orders from this folder
                if not orders or len(orders) < limit:
                    # No more orders available from this folder
                    break

                current_offset += len(orders)

                # Safety limit to prevent infinite loops
                if current_offset > 100000:
                    logger.warning(f"Pagination safety limit reached at offset {current_offset}")
                    break

        # Return combined response
        logger.info(f"Total orders fetched and filtered: {len(all_orders)}")
        return {
            'orders': all_orders,
            'total_count': len(all_orders)
        }
    finally:
        client.close()


def save_tiktok_orders_to_csv(
    orders_data: Dict[str, Any],
    output_path: str,
    start_date: str = None,
    end_date: str = None
) -> str:
    """
    Save TikTok orders data to CSV file in aggregated daily format.

    Args:
        orders_data: Orders data from Order Desk API (should have 'orders' key with list of orders)
        output_path: Path where CSV should be saved
        start_date: Optional start date for filtering
        end_date: Optional end date for filtering

    Returns:
        Path to saved CSV file
    """
    logger.info(f"Saving orders to CSV: {output_path}")

    orders = orders_data.get('orders', [])
    total_count = orders_data.get('total_count', len(orders))

    logger.info(f"Processing {len(orders)} orders to CSV (total_count: {total_count})")

    if not orders:
        # Create empty CSV with headers
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Date',
                'Total Daily Gross sales',
                'Total TikTok Orders',
                'Collected Sales Tax',
                'Total TikTok Units',
            ])
            writer.writerow(['No orders found for the selected date range'])
        logger.info(f"Created empty CSV file: {output_path}")
        return output_path

    # Aggregate orders by date
    daily_totals = {}

    for order in orders:
        if not isinstance(order, dict):
            continue

        # Order Desk uses 'date_added' field (format: "2025-12-01 09:43:03")
        date_value = order.get('date_added')

        if not date_value:
            logger.warning(f"Order {order.get('id')} has no date_added field")
            continue

        try:
            # Parse Order Desk date format: "YYYY-MM-DD HH:MM:SS" (assumed to be UTC)
            # Parse as UTC datetime
            dt = datetime.strptime(date_value, '%Y-%m-%d %H:%M:%S')
            dt = dt.replace(tzinfo=timezone.utc)

            # Convert to Eastern timezone - TikTok groups orders by Eastern time date (America/New_York)
            eastern_tz = ZoneInfo("America/New_York")
            local_datetime = dt.astimezone(eastern_tz)

            # Use Eastern time date as the key (matching TikTok dashboard grouping)
            date_key = local_datetime.strftime('%Y-%m-%d')
            order_date = local_datetime.replace(hour=0, minute=0, second=0, microsecond=0)

            # Log order date conversion for debugging
            logger.debug(f"Order {order.get('id')}: date_added={date_value} (UTC) -> Eastern date={date_key} ({local_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')})")
        except Exception as e:
            logger.warning(f"Could not parse date '{date_value}' for order {order.get('id')}: {e}")
            continue

        if date_key not in daily_totals:
            daily_totals[date_key] = {
                'date': order_date,
                'gross_sales': 0.0,
                'orders_count': 0,
                'units': 0,
                'sales_tax': 0.0,
            }

        # Aggregate values from Order Desk order structure
        daily_totals[date_key]['orders_count'] += 1

        # Sales tax from order level (total tax applied on all items)
        tax_total = order.get('tax_total', 0)
        try:
            daily_totals[date_key]['sales_tax'] += float(tax_total)
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse tax_total for order {order.get('id')}: {e}")

        # Process order items for gross sales and units
        # TikTok dashboard calculation pattern:
        # - If all items have the same unit price: use unit_price + tax
        # - If items have different prices: use sum of (item_price * quantity) for all items + tax
        order_items = order.get('order_items', [])
        if not isinstance(order_items, list):
            order_items = []

        # Get quantity for units calculation and collect item prices
        # TikTok counts units by NUMBER OF LINE ITEMS, not by sum of quantities
        # Each order_item represents 1 unit regardless of quantity
        item_prices = []
        order_total_units = 0
        item_details = []
        for item in order_items:
            if not isinstance(item, dict):
                continue

            # TikTok counts each line item as 1 unit
            order_total_units += 1
            daily_totals[date_key]['units'] += 1

            # Get quantity for price calculation (but not for unit counting)
            quantity = item.get('quantity', 0)
            try:
                quantity_int = int(float(quantity))
                item_details.append(f"item_{item.get('id', 'unknown')}: qty={quantity_int}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse quantity '{quantity}' for order item {item.get('id')}: {e}")
                item_details.append(f"item_{item.get('id', 'unknown')}: qty=0")
                quantity_int = 0

            # Get item price: use tiktokshopus_sale_price if set, otherwise tiktokshopus_original_price
            item_metadata = item.get('metadata', {})
            if not isinstance(item_metadata, dict):
                item_metadata = {}

            item_price = None
            sale_price = item_metadata.get('tiktokshopus_sale_price')
            if sale_price is not None and sale_price != '':
                try:
                    item_price = float(sale_price)
                except (ValueError, TypeError):
                    pass

            if item_price is None:
                original_price = item_metadata.get('tiktokshopus_original_price')
                if original_price is not None and original_price != '':
                    try:
                        item_price = float(original_price)
                    except (ValueError, TypeError):
                        pass

            # Fallback to item.price if metadata prices are not available
            if item_price is None:
                item_price_from_api = item.get('price')
                if item_price_from_api is not None and item_price_from_api != '':
                    try:
                        item_price = float(item_price_from_api)
                    except (ValueError, TypeError):
                        pass

            if item_price is not None:
                item_prices.append((item_price, quantity_int))
            else:
                logger.warning(f"Order {order.get('id')} item {item.get('id')} has no price data (checked metadata and item.price)")

        # Log order details for debugging
        items_summary = ", ".join(item_details) if item_details else "no items"
        logger.info(f"Order {order.get('id')} date_key={date_key}: {order_total_units} unit(s) from {len(order_items)} item(s) [{items_summary}]")

        # Calculate gross sales based on pattern
        tax_total = order.get('tax_total', 0)
        try:
            tax_total_float = float(tax_total)
        except (ValueError, TypeError):
            tax_total_float = 0.0

        if not item_prices:
            order_gross_sales = tax_total_float
            logger.warning(f"Order {order.get('id')} date_key={date_key}: has no valid item prices, using tax only = {order_gross_sales}")
        else:
            # Check if all items have the same unit price
            first_price = item_prices[0][0]
            all_same_price = all(abs(price - first_price) < 0.01 for price, _ in item_prices)

            if all_same_price:
                # All items same price: use (unit_price * number_of_line_items) + tax
                # TikTok counts each line item separately, so multiply by number of items
                order_gross_sales = first_price * len(item_prices) + tax_total_float
                logger.info(f"Order {order.get('id')} date_key={date_key}: all items same price ({first_price}), using unit_price * {len(item_prices)} + tax = {order_gross_sales}")
            else:
                # Different prices: use sum of item prices (ignoring quantity) + tax
                # TikTok counts each line item once, regardless of quantity
                total_items_value = sum(price for price, _ in item_prices)
                order_gross_sales = total_items_value + tax_total_float
                logger.info(f"Order {order.get('id')} date_key={date_key}: different item prices, using sum(item_prices) ({total_items_value}) + tax = {order_gross_sales}")

        # Add order gross sales to daily total
        daily_totals[date_key]['gross_sales'] += order_gross_sales

    # Sort by date
    sorted_dates = sorted(daily_totals.keys())

    # Log summary of orders by date for debugging
    logger.info("=" * 80)
    logger.info("CSV Export Summary - Orders by Date:")
    for date_key in sorted_dates:
        totals = daily_totals[date_key]
        logger.info(f"  {date_key}: {totals['orders_count']} orders, {totals['units']} units, ${totals['gross_sales']:.2f} gross sales")
    logger.info("=" * 80)

    # Write CSV file
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)

        headers = [
            'Date',
            'Total Daily Gross sales',
            'Total TikTok Orders',
            'Collected Sales Tax',
            'Total TikTok Units',
        ]
        writer.writerow(headers)

        # Write data rows
        for date_key in sorted_dates:
            totals = daily_totals[date_key]
            date_formatted = totals['date'].strftime('%b %d, %Y')

            row = [
                date_formatted,
                round(totals['gross_sales'], 2),
                totals['orders_count'],
                round(totals['sales_tax'], 2),
                totals['units'],
            ]
            logger.info(f"CSV row for {date_key}: gross_sales={totals['gross_sales']:.2f}, orders={totals['orders_count']}, units={totals['units']}, tax={totals['sales_tax']:.2f}")
            writer.writerow(row)

    logger.info(f"Successfully saved {len(sorted_dates)} days of aggregated data to CSV: {output_path}")
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
    Export TikTok orders to Google Sheets in the same format as CSV export.

    Supports both OAuth 2.0 and Service Account authentication.

    Args:
        orders_data: Orders data from Order Desk API
        spreadsheet_id: Google Sheets spreadsheet ID
        sheet_name: Name of the sheet to write to (fallback if date-based name can't be generated)
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
                    logger.info(f"Attempting OAuth authentication with token: {oauth_token_path}")
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

        # Generate month+year sheet name from date range (like Ulta)
        # Use start_date to determine the month/year, or first order date if start_date not provided
        month_year_sheet_name = None
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                chicago_tz = ZoneInfo("America/Chicago")
                start_chicago = start_dt.astimezone(chicago_tz)
                month_year_sheet_name = start_chicago.strftime('%B %Y')  # e.g., "November 2025"
            except Exception as e:
                logger.warning(f"Could not parse start_date for sheet name: {e}, using provided sheet_name")

        # If we couldn't generate from start_date, try to use first order date
        if not month_year_sheet_name:
            orders = orders_data.get('orders', [])
            if orders:
                try:
                    first_order_date = orders[0].get('date_added')
                    if first_order_date:
                        # Order Desk format: "YYYY-MM-DD HH:MM:SS" (assumed UTC)
                        dt = datetime.strptime(first_order_date, '%Y-%m-%d %H:%M:%S')
                        dt = dt.replace(tzinfo=timezone.utc)
                        chicago_tz = ZoneInfo("America/Chicago")
                        first_chicago = dt.astimezone(chicago_tz)
                        month_year_sheet_name = first_chicago.strftime('%B %Y')
                except Exception as e:
                    logger.warning(f"Could not parse first order date for sheet name: {e}")

        # Fall back to provided sheet_name if we couldn't generate month+year
        if not month_year_sheet_name:
            month_year_sheet_name = sheet_name

        logger.info(f"Using sheet name: {month_year_sheet_name}")

        # Get or create the sheet (case-insensitive matching)
        worksheet = None
        has_headers = False
        sheet_was_created = False

        try:
            logger.info(f"Looking for sheet: {month_year_sheet_name}")

            # List all worksheets to find a case-insensitive match
            all_worksheets = spreadsheet.worksheets()
            logger.info(f"Available sheets in spreadsheet: {[ws.title for ws in all_worksheets]}")

            # Try exact match first
            try:
                worksheet = spreadsheet.worksheet(month_year_sheet_name)
                logger.info(f"Found existing sheet (exact match): {month_year_sheet_name}")
            except gspread.exceptions.WorksheetNotFound:
                # Try case-insensitive match
                for ws in all_worksheets:
                    if ws.title.lower() == month_year_sheet_name.lower():
                        worksheet = ws
                        logger.info(f"Found existing sheet (case-insensitive match): '{ws.title}' (requested: '{month_year_sheet_name}')")
                        break

                if not worksheet:
                    # Sheet not found, create new one
                    logger.info(f"Sheet '{month_year_sheet_name}' not found, creating new sheet...")
                    worksheet = spreadsheet.add_worksheet(title=month_year_sheet_name, rows=1000, cols=50)
                    sheet_was_created = True
                    logger.info(f"Created new sheet: {month_year_sheet_name}")

                    # Copy header from first tab (Main or first worksheet)
                    try:
                        first_tab = None
                        # Try to find "Main" tab first
                        for ws in all_worksheets:
                            if ws.title.lower() == 'main':
                                first_tab = ws
                                logger.info(f"Found 'Main' tab, copying header from it")
                                break

                        # If no "Main" tab, use the first worksheet
                        if not first_tab and all_worksheets:
                            first_tab = all_worksheets[0]
                            logger.info(f"No 'Main' tab found, copying header from first tab: '{first_tab.title}'")

                        if first_tab:
                            first_tab_data = first_tab.get_all_values()
                            if first_tab_data and len(first_tab_data) > 0:
                                header_row = first_tab_data[0]
                                worksheet.append_row(header_row)
                                logger.info(f"Copied header from '{first_tab.title}' to new sheet '{month_year_sheet_name}'")
                                has_headers = True
                            else:
                                logger.warning(f"First tab '{first_tab.title}' has no header row to copy")
                        else:
                            logger.warning("No tabs found to copy header from")
                    except Exception as e:
                        logger.warning(f"Could not copy header from first tab: {e}, will create default header")

            # Check if sheet has existing data and read existing header
            existing_data = worksheet.get_all_values()
            has_headers = len(existing_data) > 0

            existing_header = []
            if has_headers:
                existing_header = existing_data[0] if existing_data else []
                logger.info(f"Sheet '{worksheet.title}' has existing data: {len(existing_data)} rows")
                logger.info(f"Existing header has {len(existing_header)} columns")
            else:
                logger.info(f"Sheet '{worksheet.title}' is empty, will create headers")

        except Exception as e:
            logger.error(f"Error accessing sheet '{month_year_sheet_name}': {str(e)}", exc_info=True)
            return False

        # Process orders data (same logic as CSV export)
        orders = orders_data.get('orders', [])
        total_count = orders_data.get('total_count', len(orders))

        logger.info(f"=== Starting Google Sheets export ===")
        logger.info(f"Received {len(orders)} orders from API (total_count: {total_count})")

        if not orders:
            # Only write headers if sheet is empty
            if not has_headers:
                headers = [
                    'Date',
                    'Total Daily Gross sales',
                    'Total TikTok Orders',
                    'Collected Sales Tax',
                    'Total TikTok Units',
                ]
                worksheet.append_row(headers)
                worksheet.append_row(['No orders found for the selected date range'])
                logger.info(f"Created empty sheet with headers")
            else:
                logger.info(f"Sheet already has data, skipping empty export")
            return True

        # Aggregate orders by date (same logic as CSV)
        logger.info("Starting order aggregation by date...")
        daily_totals = {}

        for order in orders:
            if not isinstance(order, dict):
                continue

            # Order Desk uses 'date_added' field (format: "2025-12-01 09:43:03")
            date_value = order.get('date_added')

            if not date_value:
                logger.warning(f"Order {order.get('id')} has no date_added field")
                continue

            try:
                # Parse Order Desk date format: "YYYY-MM-DD HH:MM:SS" (assumed to be UTC)
                dt = datetime.strptime(date_value, '%Y-%m-%d %H:%M:%S')
                dt = dt.replace(tzinfo=timezone.utc)

                # Convert to Eastern timezone - TikTok groups orders by Eastern time date (America/New_York)
                eastern_tz = ZoneInfo("America/New_York")
                local_datetime = dt.astimezone(eastern_tz)

                # Use Eastern time date as the key (matching TikTok dashboard grouping)
                date_key = local_datetime.strftime('%Y-%m-%d')
                order_date = local_datetime.replace(hour=0, minute=0, second=0, microsecond=0)

                # Log order date conversion for debugging
                logger.debug(f"Order {order.get('id')}: date_added={date_value} (UTC) -> Eastern date={date_key} ({local_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')})")
            except Exception as e:
                logger.warning(f"Could not parse date '{date_value}' for order {order.get('id')}: {e}")
                continue

            if date_key not in daily_totals:
                daily_totals[date_key] = {
                    'date': order_date,
                    'gross_sales': 0.0,
                    'orders_count': 0,
                    'units': 0,
                    'sales_tax': 0.0,
                }

            # Aggregate values from Order Desk order structure
            daily_totals[date_key]['orders_count'] += 1

            # Sales tax from order level (total tax applied on all items)
            tax_total = order.get('tax_total', 0)
            try:
                daily_totals[date_key]['sales_tax'] += float(tax_total)
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse tax_total for order {order.get('id')}: {e}")

            # Process order items for gross sales and units
            # TikTok dashboard calculation pattern:
            # - If all items have the same unit price: use unit_price + tax
            # - If items have different prices: use sum of (item_price * quantity) for all items + tax
            order_items = order.get('order_items', [])
            if not isinstance(order_items, list):
                order_items = []

            # Get quantity for units calculation and collect item prices
            # TikTok counts units by NUMBER OF LINE ITEMS, not by sum of quantities
            # Each order_item represents 1 unit regardless of quantity
            item_prices = []
            order_total_units = 0
            item_details = []
            for item in order_items:
                if not isinstance(item, dict):
                    continue

                # TikTok counts each line item as 1 unit
                order_total_units += 1
                daily_totals[date_key]['units'] += 1

                # Get quantity for price calculation (but not for unit counting)
                quantity = item.get('quantity', 0)
                try:
                    quantity_int = int(float(quantity))
                    item_details.append(f"item_{item.get('id', 'unknown')}: qty={quantity_int}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse quantity '{quantity}' for order item {item.get('id')}: {e}")
                    item_details.append(f"item_{item.get('id', 'unknown')}: qty=0")
                    quantity_int = 0

                # Get item price: use tiktokshopus_sale_price if set, otherwise tiktokshopus_original_price
                item_metadata = item.get('metadata', {})
                if not isinstance(item_metadata, dict):
                    item_metadata = {}

                item_price = None
                sale_price = item_metadata.get('tiktokshopus_sale_price')
                if sale_price is not None and sale_price != '':
                    try:
                        item_price = float(sale_price)
                    except (ValueError, TypeError):
                        pass

                if item_price is None:
                    original_price = item_metadata.get('tiktokshopus_original_price')
                    if original_price is not None and original_price != '':
                        try:
                            item_price = float(original_price)
                        except (ValueError, TypeError):
                            pass

                # Fallback to item.price if metadata prices are not available
                if item_price is None:
                    item_price_from_api = item.get('price')
                    if item_price_from_api is not None and item_price_from_api != '':
                        try:
                            item_price = float(item_price_from_api)
                        except (ValueError, TypeError):
                            pass

                if item_price is not None:
                    item_prices.append((item_price, quantity_int))
                else:
                    logger.warning(f"Order {order.get('id')} item {item.get('id')} has no price data (checked metadata and item.price)")

            # Calculate gross sales based on pattern
            tax_total = order.get('tax_total', 0)
            try:
                tax_total_float = float(tax_total)
            except (ValueError, TypeError):
                tax_total_float = 0.0

            if not item_prices:
                order_gross_sales = tax_total_float
                logger.warning(f"Order {order.get('id')} date_key={date_key}: has no valid item prices, using tax only = {order_gross_sales}")
            else:
                # Check if all items have the same unit price
                first_price = item_prices[0][0]
                all_same_price = all(abs(price - first_price) < 0.01 for price, _ in item_prices)

                if all_same_price:
                    # All items same price: use (unit_price * number_of_line_items) + tax
                    # TikTok counts each line item separately, so multiply by number of items
                    order_gross_sales = first_price * len(item_prices) + tax_total_float
                    logger.info(f"Order {order.get('id')} date_key={date_key}: all items same price ({first_price}), using unit_price * {len(item_prices)} + tax = {order_gross_sales}")
                else:
                    # Different prices: use sum of item prices (ignoring quantity) + tax
                    # TikTok counts each line item once, regardless of quantity
                    total_items_value = sum(price for price, _ in item_prices)
                    order_gross_sales = total_items_value + tax_total_float
                    logger.info(f"Order {order.get('id')} date_key={date_key}: different item prices, using sum(item_prices) ({total_items_value}) + tax = {order_gross_sales}")

            # Add order gross sales to daily total
            daily_totals[date_key]['gross_sales'] += order_gross_sales

            # Log order details for debugging
            items_summary = ", ".join(item_details) if item_details else "no items"
            logger.info(f"Order {order.get('id')} date_key={date_key}: {order_total_units} unit(s) from {len(order_items)} item(s) [{items_summary}]")

        # Sort by date
        sorted_dates = sorted(daily_totals.keys())

        # Log summary of orders by date for debugging
        logger.info("=" * 80)
        logger.info("Google Sheets Export Summary - Orders by Date:")
        for date_key in sorted_dates:
            totals = daily_totals[date_key]
            logger.info(f"  {date_key}: {totals['orders_count']} orders, {totals['units']} units, ${totals['gross_sales']:.2f} gross sales")
        logger.info("=" * 80)

        logger.info(f"Aggregation complete: {len(sorted_dates)} unique dates")

        # Prepare headers
        base_headers = [
            'Date',
            'Total Daily Gross sales',
            'Total TikTok Orders',
            'Collected Sales Tax',
            'Total TikTok Units',
        ]

        headers = base_headers

        # Write or update headers
        if not has_headers:
            try:
                logger.info("Writing headers to Google Sheets...")
                worksheet.append_row(headers)
                logger.info(f"Successfully wrote headers: {headers}")
            except Exception as e:
                logger.error(f"Error writing headers: {str(e)}", exc_info=True)
                return False
        else:
            # Check if header needs to be updated
            if len(existing_header) != len(headers) or existing_header != headers:
                try:
                    logger.info(f"Updating header row")
                    worksheet.update('1:1', [headers])
                    logger.info(f"Successfully updated headers: {headers}")
                except Exception as e:
                    logger.error(f"Error updating headers: {str(e)}", exc_info=True)
                    return False
            else:
                logger.info("Headers already match, no update needed")

            # Re-read existing data after header updates
            try:
                existing_data = worksheet.get_all_values()
                logger.debug(f"Re-read existing data: {len(existing_data)} rows")
            except Exception as e:
                logger.warning(f"Could not re-read existing data after header update: {e}")

        # Build mapping of existing dates to row numbers (1-indexed, row 1 is header)
        # Date format in sheet is "Dec 1, 2025" (from strftime('%b %d, %Y'))
        date_to_row = {}
        if has_headers and len(existing_data) > 1:
            for row_idx, row_data in enumerate(existing_data[1:], start=2):  # Skip header, start at row 2
                if row_data and len(row_data) > 0:
                    existing_date = row_data[0].strip() if row_data[0] else ""
                    if existing_date:
                        existing_date_normalized = ' '.join(existing_date.split())
                        date_to_row[existing_date_normalized] = row_idx
                        logger.debug(f"Found existing date row {row_idx}: '{existing_date_normalized}'")
            logger.info(f"Found {len(date_to_row)} existing date rows in sheet")

        # Prepare data rows and determine which to update vs append
        rows_to_update = {}  # row_number -> row_data
        rows_to_append = []  # list of row_data

        for date_key in sorted_dates:
            totals = daily_totals[date_key]
            date_formatted = totals['date'].strftime('%b %d, %Y')

            row = [
                date_formatted,
                round(totals['gross_sales'], 2),
                totals['orders_count'],
                round(totals['sales_tax'], 2),
                totals['units'],
            ]

            # Normalize date format for comparison
            date_formatted_normalized = ' '.join(date_formatted.split())

            # Check if this date already exists in the sheet
            if date_formatted_normalized in date_to_row:
                row_num = date_to_row[date_formatted_normalized]
                rows_to_update[row_num] = row
                logger.info(f"Will UPDATE row {row_num} for date '{date_formatted_normalized}'")
            else:
                rows_to_append.append(row)
                logger.info(f"Will APPEND new row for date '{date_formatted_normalized}'")

        logger.info(f"Prepared {len(rows_to_update)} rows to update and {len(rows_to_append)} rows to append")

        # Update existing rows
        if rows_to_update:
            try:
                logger.info(f"Updating {len(rows_to_update)} existing rows in Google Sheets...")
                for row_num, row_data in rows_to_update.items():
                    range_name = f"{row_num}:{row_num}"
                    worksheet.update(range_name, [row_data])
                logger.info(f"Successfully updated {len(rows_to_update)} rows")
            except Exception as e:
                logger.error(f"Error updating rows in Google Sheets: {str(e)}", exc_info=True)
                return False

        # Append new rows
        if rows_to_append:
            try:
                logger.info(f"Appending {len(rows_to_append)} new rows to Google Sheets...")
                worksheet.append_rows(rows_to_append)
                logger.info(f"Successfully appended {len(rows_to_append)} rows to Google Sheets")
            except Exception as e:
                logger.error(f"Error appending rows to Google Sheets: {str(e)}", exc_info=True)
                return False

        if not rows_to_update and not rows_to_append:
            logger.warning("No rows to write to Google Sheets!")

        logger.info(f"=== Successfully exported {len(sorted_dates)} days of aggregated data to Google Sheets ===")
        return True

    except Exception as e:
        logger.error(f"Error exporting to Google Sheets: {str(e)}", exc_info=True)
        return False

