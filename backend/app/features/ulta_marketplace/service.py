import csv
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from zoneinfo import ZoneInfo
from .ulta_client import UltaAPIClient

logger = logging.getLogger(__name__)


def fetch_ulta_orders(
    start_date: str,
    end_date: str,
    api_key: str,
    max: int = 999,
    offset: int = 0
) -> Dict[str, Any]:
    """
    Fetch orders from Ulta API with pagination support.

    Args:
        start_date: Start date in ISO format
        end_date: End date in ISO format
        api_key: Ulta API authorization key
        max: Maximum records to fetch per page
        offset: Pagination offset

    Returns:
        Dictionary with orders data (all pages combined)
    """
    client = UltaAPIClient(api_key=api_key)
    try:
        all_orders = []
        current_offset = offset
        total_count = None

        while True:
            response = client.get_orders(
                start_date=start_date,
                end_date=end_date,
                max=max,
                offset=current_offset
            )

            orders = response.get('orders', [])
            if total_count is None:
                total_count = response.get('total_count', len(orders))

            all_orders.extend(orders)

            logger.info(f"Fetched {len(orders)} orders (offset {current_offset}, total so far: {len(all_orders)}/{total_count})")

            # Check if we've got all orders
            if not orders:
                # No orders returned, we're done
                break

            if total_count and len(all_orders) >= total_count:
                # We've reached the total count
                break

            # Continue fetching if:
            # 1. We got fewer than max orders AND we haven't reached total_count yet
            # 2. Or we got max orders (might be more pages)
            if len(orders) < max:
                # Got fewer than max, check if we need more
                if total_count and len(all_orders) < total_count:
                    # Still have more to fetch according to total_count
                    current_offset += len(orders)
                    continue
                else:
                    # No total_count or we've reached it, this is the last page
                    break

            current_offset += len(orders)

            # Safety limit to prevent infinite loops
            if current_offset > 100000:
                logger.warning(f"Pagination safety limit reached at offset {current_offset}")
                break

        # Return combined response
        return {
            'orders': all_orders,
            'total_count': len(all_orders)
        }
    finally:
        client.close()


def save_ulta_orders_to_csv(
    orders_data: Dict[str, Any],
    output_path: str,
    start_date: str = None,
    end_date: str = None
) -> str:
    """
    Save Ulta orders data to CSV file in aggregated daily format.

    Args:
        orders_data: Orders data from Ulta API (should have 'orders' key with list of orders)
        output_path: Path where CSV should be saved

    Returns:
        Path to saved CSV file
    """
    import json

    logger.info(f"Saving orders to CSV: {output_path}")

    orders = orders_data.get('orders', [])
    total_count = orders_data.get('total_count', len(orders))

    logger.info(f"Processing {len(orders)} orders to CSV (total_count: {total_count})")

    if not orders:
            # Create empty CSV with headers (no product columns if no orders)
            # Use 'utf-8-sig' encoding to add BOM for Excel compatibility
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Date',
                'Total Daily Gross sales',
                'Total Ulta Orders',
                'Total Ulta Commission',
                'Collected Sales Tax',
                'Total Ulta Units',
                'Total Daily Refunds'
            ])
            writer.writerow(['No orders found for the selected date range'])
        logger.info(f"Created empty CSV file: {output_path}")
        return output_path

    # First pass: Collect all unique products
    all_products = set()

    # Deduplicate orders by order_id (in case API returns duplicates)
    seen_order_ids = set()
    unique_orders = []
    for order in orders:
        order_id = order.get('order_id')
        if order_id and order_id not in seen_order_ids:
            seen_order_ids.add(order_id)
            unique_orders.append(order)
        elif not order_id:
            # Include orders without ID (shouldn't happen, but be safe)
            unique_orders.append(order)

    if len(unique_orders) < len(orders):
        logger.warning(f"Found {len(orders) - len(unique_orders)} duplicate orders, deduplicated to {len(unique_orders)} unique orders")

    # Filter orders by date range if provided (to exclude orders outside selected range)
    # This handles cases where API might return orders slightly outside the range due to timezone conversion
    filtered_orders = unique_orders
    if start_date and end_date:
        try:
            # Parse the query date range
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

            # Convert to Chicago timezone for comparison
            chicago_tz = ZoneInfo("America/Chicago")
            start_chicago = start_dt.astimezone(chicago_tz)
            end_chicago = end_dt.astimezone(chicago_tz)

            # Filter orders to only include those within the selected date range
            filtered_orders = []
            for order in unique_orders:
                order_date_value = order.get('created_date')
                if order_date_value:
                    if '.' in order_date_value and 'Z' in order_date_value:
                        order_date_clean = order_date_value.split('.')[0] + 'Z'
                    else:
                        order_date_clean = order_date_value

                    try:
                        order_utc = datetime.fromisoformat(order_date_clean.replace('Z', '+00:00'))
                        order_chicago = order_utc.astimezone(chicago_tz)

                        # Include order if it's within the selected range (inclusive)
                        if start_chicago <= order_chicago <= end_chicago:
                            filtered_orders.append(order)
                    except:
                        # If we can't parse the date, include it to be safe
                        filtered_orders.append(order)
                else:
                    # If no date, include it to be safe
                    filtered_orders.append(order)

            if len(filtered_orders) < len(unique_orders):
                logger.info(f"Filtered {len(unique_orders) - len(filtered_orders)} orders outside date range {start_date} to {end_date}")
        except Exception as e:
            logger.warning(f"Could not filter orders by date range: {e}, including all orders")
            filtered_orders = unique_orders

    # Aggregate orders by date
    daily_totals = {}

    for order in filtered_orders:
        if not isinstance(order, dict):
            continue

        # Extract date from order - Use created_date to match the API date filter
        # Convert UTC created_date to local timezone (America/Chicago with DST) to match Ulta dashboard
        # This ensures orders are grouped by the same date that Ulta dashboard uses
        date_key = None
        date_value = order.get('created_date')

        if date_value and isinstance(date_value, str):
            try:
                # Parse the UTC date from API
                # Handle milliseconds if present
                if '.' in date_value and 'Z' in date_value:
                    # Format: 2025-11-02T14:55:10.000Z
                    date_value_clean = date_value.split('.')[0] + 'Z'
                else:
                    date_value_clean = date_value

                # Parse as UTC datetime
                utc_datetime = datetime.fromisoformat(date_value_clean.replace('Z', '+00:00'))

                # Convert to America/Chicago timezone (with DST) to match Zapier/Ulta dashboard
                # This handles DST automatically (CDT UTC-5 in summer, CST UTC-6 in winter)
                chicago_tz = ZoneInfo("America/Chicago")
                local_datetime = utc_datetime.astimezone(chicago_tz)

                # Extract date part (YYYY-MM-DD) from the local timezone date
                date_key = local_datetime.strftime('%Y-%m-%d')

                # Store the local date for formatting
                order_date = local_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
            except Exception as e:
                logger.warning(f"Could not parse date '{date_value}': {e}")
                continue

        if not date_key:
            logger.warning(f"Could not extract date from order: {order.get('order_id', 'unknown')}")
            continue

        if date_key not in daily_totals:
            daily_totals[date_key] = {
                'date': order_date,
                'gross_sales': 0.0,
                'orders_count': 0,
                'units': 0,
                'commission': 0.0,
                'sales_tax': 0.0,
                'refunds': 0.0,  # Total refund amount in dollars
                'products': {}  # Dictionary to track quantity per product
            }

        # Aggregate values
        daily_totals[date_key]['orders_count'] += 1

        # Gross sales - Use order-level 'total_price' or 'price'
        price = order.get('total_price') or order.get('price', 0)
        try:
            daily_totals[date_key]['gross_sales'] += float(price)
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse price for order {order.get('order_id')}: {e}")

        # Process order lines for units, commission, and tax
        order_lines = order.get('order_lines', [])
        if not isinstance(order_lines, list):
            # If order_lines is a string (JSON), parse it
            if isinstance(order_lines, str):
                try:
                    order_lines = json.loads(order_lines)
                except Exception as e:
                    logger.warning(f"Could not parse order_lines JSON for order {order.get('order_id')}: {e}")
                    order_lines = []
            else:
                order_lines = []

        if not order_lines:
            logger.warning(f"No order lines found for order {order.get('order_id')}")

        for line in order_lines:
            if not isinstance(line, dict):
                logger.warning(f"Order line is not a dict: {type(line)}")
                continue

            # Get product title
            product_title = line.get('product_title', '').strip()
            if not product_title:
                # Fallback to product_sku if title is missing
                product_title = line.get('product_sku', 'Unknown Product')
                logger.warning(f"No product_title in order line: {line.get('order_line_id', 'unknown')}, using SKU: {product_title}")

            # Track unique products
            all_products.add(product_title)

            # Units - sum quantity from each line
            quantity = line.get('quantity', 0)
            try:
                quantity_int = int(float(quantity))
                daily_totals[date_key]['units'] += quantity_int

                # Track quantity per product
                if product_title not in daily_totals[date_key]['products']:
                    daily_totals[date_key]['products'][product_title] = 0
                daily_totals[date_key]['products'][product_title] += quantity_int
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse quantity '{quantity}' for order line {line.get('order_line_id')}: {e}")

            # Commission - use 'total_commission' from line (per line item)
            commission = line.get('total_commission', 0)
            try:
                daily_totals[date_key]['commission'] += float(commission)
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse commission '{commission}' for order line {line.get('order_line_id')}: {e}")

            # Sales Tax - sum 'amount' from taxes array in each line
            taxes = line.get('taxes', [])
            if not isinstance(taxes, list):
                taxes = []

            for tax in taxes:
                if isinstance(tax, dict):
                    tax_amount = tax.get('amount', 0)
                    try:
                        daily_totals[date_key]['sales_tax'] += float(tax_amount)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse tax amount '{tax_amount}': {e}")

            # Process refunds - group by order date (not refund date)
            # This ensures refunds appear on the same row as the order for daily exports
            refunds = line.get('refunds', [])
            if not isinstance(refunds, list):
                refunds = []

            for refund in refunds:
                if not isinstance(refund, dict):
                    continue

                # Add refund amount to the order date's totals (not refund date)
                # Use the same date_key as the order so refunds appear on the same row
                refund_amount = refund.get('amount', 0)
                try:
                    daily_totals[date_key]['refunds'] += float(refund_amount)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse refund amount '{refund_amount}': {e}")

    # Sort by date
    sorted_dates = sorted(daily_totals.keys())

    # Sort products alphabetically for consistent column order
    sorted_products = sorted(all_products)

    # Write CSV file with the required format
    # Use 'utf-8-sig' encoding to add BOM for Excel compatibility
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)

        # Write headers: base columns + product columns
        headers = [
            'Date',
            'Total Daily Gross sales',
            'Total Ulta Orders',
            'Total Ulta Commission',
            'Collected Sales Tax',
            'Total Ulta Units',
            'Total Daily Refunds'
        ]
        # Add product columns
        headers.extend(sorted_products)
        writer.writerow(headers)

        # Write data rows
        for date_key in sorted_dates:
            totals = daily_totals[date_key]
            # Format date as "Nov 1, 2025"
            date_formatted = totals['date'].strftime('%b %d, %Y')

            row = [
                date_formatted,
                round(totals['gross_sales'], 2),
                totals['orders_count'],
                round(totals['commission'], 2),
                round(totals['sales_tax'], 2),
                totals['units'],
                round(totals.get('refunds', 0.0), 2)
            ]
            # Add product quantities (0 if product not sold on this date)
            for product in sorted_products:
                quantity = totals['products'].get(product, 0)
                row.append(quantity)

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
    Export Ulta orders to Google Sheets in the same format as CSV export.

    Supports both OAuth 2.0 and Service Account authentication.

    Args:
        orders_data: Orders data from Ulta API (should have 'orders' key with list of orders)
        spreadsheet_id: Google Sheets spreadsheet ID
        sheet_name: Name of the sheet to write to
        oauth_credentials_path: Path to OAuth client credentials JSON file (for OAuth auth)
        oauth_token_path: Path to saved OAuth token file (for OAuth auth)
        service_account_path: Path to service account JSON file (for service account auth)
        start_date: Optional start date for filtering
        end_date: Optional end date for filtering

    Returns:
        True if successful, False otherwise
    """
    import json
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

        # Try OAuth authentication first (for organization projects)
        if oauth_credentials_path and oauth_token_path:
            if os.path.exists(oauth_token_path):
                try:
                    logger.info(f"Attempting OAuth authentication with token: {oauth_token_path}")
                    with open(oauth_token_path, 'rb') as token:
                        creds = pickle.load(token)

                    # Refresh token if expired
                    if creds.expired and creds.refresh_token:
                        logger.info("OAuth token expired, refreshing...")
                        creds.refresh(Request())
                        # Save refreshed token
                        with open(oauth_token_path, 'wb') as token:
                            pickle.dump(creds, token)

                    if creds.valid:
                        auth_method = "OAuth"
                        logger.info("OAuth authentication successful")
                except Exception as e:
                    logger.warning(f"Could not load OAuth token: {e}")
                    creds = None
            else:
                logger.warning(f"OAuth token file not found: {oauth_token_path}")

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
            else:
                logger.warning(f"Service account file not found: {service_account_path}")

        if not creds:
            logger.error("No valid Google credentials found. Please run setup script or configure credentials.")
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

        # Generate month+year sheet name from date range
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
                    first_order_date = orders[0].get('created_date')
                    if first_order_date:
                        if '.' in first_order_date and 'Z' in first_order_date:
                            first_order_date_clean = first_order_date.split('.')[0] + 'Z'
                        else:
                            first_order_date_clean = first_order_date
                        first_dt = datetime.fromisoformat(first_order_date_clean.replace('Z', '+00:00'))
                        chicago_tz = ZoneInfo("America/Chicago")
                        first_chicago = first_dt.astimezone(chicago_tz)
                        month_year_sheet_name = first_chicago.strftime('%B %Y')
                except Exception as e:
                    logger.warning(f"Could not parse first order date for sheet name: {e}")

        # Fall back to provided sheet_name if we couldn't generate month+year
        if not month_year_sheet_name:
            month_year_sheet_name = sheet_name

        logger.info(f"Using sheet name: {month_year_sheet_name}")

        # Get or create the sheet (case-insensitive matching)
        # Initialize variables
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
            existing_products = set()

            if has_headers:
                existing_header = existing_data[0] if existing_data else []
                # Determine the number of fixed columns based on whether "Total Daily Refunds" exists
                # Old format: 6 columns (before refunds column was added)
                # New format: 7 columns (with refunds column)
                fixed_columns = 7  # Default to new format
                if len(existing_header) >= 6:
                    # Check if column 7 (index 6) is "Total Daily Refunds" or if we have old format
                    if len(existing_header) == 6 or (len(existing_header) > 6 and existing_header[6].strip() != 'Total Daily Refunds'):
                        # Old format - products start at column 7 (index 6)
                        fixed_columns = 6

                # Extract existing product columns (everything after the fixed columns)
                # Normalize by stripping whitespace
                if len(existing_header) > fixed_columns:
                    existing_products = {col.strip() for col in existing_header[fixed_columns:] if col and col.strip()}
                logger.info(f"Sheet '{worksheet.title}' has existing data: {len(existing_data)} rows")
                logger.info(f"Existing header has {len(existing_header)} columns, {len(existing_products)} product columns")
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
        logger.info(f"Orders data keys: {list(orders_data.keys()) if isinstance(orders_data, dict) else 'Not a dict'}")

        if not orders:
            # Only write headers if sheet is empty
            if not has_headers:
                headers = [
                    'Date',
                    'Total Daily Gross sales',
                    'Total Ulta Orders',
                    'Total Ulta Commission',
                    'Collected Sales Tax',
                    'Total Ulta Units',
                    'Total Daily Refunds'
                ]
                worksheet.append_row(headers)
                worksheet.append_row(['No orders found for the selected date range'])
                logger.info(f"Created empty sheet with headers")
            else:
                logger.info(f"Sheet already has data, skipping empty export")
            return True

        # Deduplicate orders by order_id
        seen_order_ids = set()
        unique_orders = []
        for order in orders:
            order_id = order.get('order_id')
            if order_id and order_id not in seen_order_ids:
                seen_order_ids.add(order_id)
                unique_orders.append(order)
            elif not order_id:
                unique_orders.append(order)

        if len(unique_orders) < len(orders):
            logger.warning(f"Found {len(orders) - len(unique_orders)} duplicate orders, deduplicated to {len(unique_orders)} unique orders")

        # Filter orders by date range if provided
        filtered_orders = unique_orders
        if start_date and end_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                chicago_tz = ZoneInfo("America/Chicago")
                start_chicago = start_dt.astimezone(chicago_tz)
                end_chicago = end_dt.astimezone(chicago_tz)

                filtered_orders = []
                for order in unique_orders:
                    order_date_value = order.get('created_date')
                    if order_date_value:
                        if '.' in order_date_value and 'Z' in order_date_value:
                            order_date_clean = order_date_value.split('.')[0] + 'Z'
                        else:
                            order_date_clean = order_date_value

                        try:
                            order_utc = datetime.fromisoformat(order_date_clean.replace('Z', '+00:00'))
                            order_chicago = order_utc.astimezone(chicago_tz)
                            if start_chicago <= order_chicago <= end_chicago:
                                filtered_orders.append(order)
                        except:
                            filtered_orders.append(order)
                    else:
                        filtered_orders.append(order)

                if len(filtered_orders) < len(unique_orders):
                    logger.info(f"Filtered {len(unique_orders) - len(filtered_orders)} orders outside date range")
            except Exception as e:
                logger.warning(f"Could not filter orders by date range: {e}, including all orders")
                filtered_orders = unique_orders

        logger.info(f"Processing {len(filtered_orders)} orders after filtering")

        # Aggregate orders by date (same logic as CSV)
        logger.info("Starting order aggregation by date...")
        daily_totals = {}
        all_products = set()

        for order in filtered_orders:
            if not isinstance(order, dict):
                continue

            date_key = None
            date_value = order.get('created_date')

            if date_value and isinstance(date_value, str):
                try:
                    if '.' in date_value and 'Z' in date_value:
                        date_value_clean = date_value.split('.')[0] + 'Z'
                    else:
                        date_value_clean = date_value

                    utc_datetime = datetime.fromisoformat(date_value_clean.replace('Z', '+00:00'))
                    chicago_tz = ZoneInfo("America/Chicago")
                    local_datetime = utc_datetime.astimezone(chicago_tz)
                    date_key = local_datetime.strftime('%Y-%m-%d')
                    order_date = local_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
                except Exception as e:
                    logger.warning(f"Could not parse date '{date_value}': {e}")
                    continue

            if not date_key:
                logger.warning(f"Could not extract date from order: {order.get('order_id', 'unknown')}")
                continue

            if date_key not in daily_totals:
                daily_totals[date_key] = {
                    'date': order_date,
                    'gross_sales': 0.0,
                    'orders_count': 0,
                    'units': 0,
                    'commission': 0.0,
                    'sales_tax': 0.0,
                    'refunds': 0.0,
                    'products': {}
                }

            daily_totals[date_key]['orders_count'] += 1

            price = order.get('total_price') or order.get('price', 0)
            try:
                daily_totals[date_key]['gross_sales'] += float(price)
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse price for order {order.get('order_id')}: {e}")

            order_lines = order.get('order_lines', [])
            if not isinstance(order_lines, list):
                if isinstance(order_lines, str):
                    try:
                        order_lines = json.loads(order_lines)
                    except Exception as e:
                        logger.warning(f"Could not parse order_lines JSON for order {order.get('order_id')}: {e}")
                        order_lines = []
                else:
                    order_lines = []

            if not order_lines:
                logger.warning(f"No order lines found for order {order.get('order_id')}")

            for line in order_lines:
                if not isinstance(line, dict):
                    continue

                product_title = line.get('product_title', '').strip()
                if not product_title:
                    product_title = line.get('product_sku', 'Unknown Product')
                    logger.warning(f"No product_title in order line: {line.get('order_line_id', 'unknown')}, using SKU: {product_title}")

                all_products.add(product_title)

                quantity = line.get('quantity', 0)
                try:
                    quantity_int = int(float(quantity))
                    daily_totals[date_key]['units'] += quantity_int

                    if product_title not in daily_totals[date_key]['products']:
                        daily_totals[date_key]['products'][product_title] = 0
                    daily_totals[date_key]['products'][product_title] += quantity_int
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse quantity '{quantity}' for order line {line.get('order_line_id')}: {e}")

                commission = line.get('total_commission', 0)
                try:
                    daily_totals[date_key]['commission'] += float(commission)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse commission '{commission}' for order line {line.get('order_line_id')}: {e}")

                taxes = line.get('taxes', [])
                if not isinstance(taxes, list):
                    taxes = []

                for tax in taxes:
                    if isinstance(tax, dict):
                        tax_amount = tax.get('amount', 0)
                        try:
                            daily_totals[date_key]['sales_tax'] += float(tax_amount)
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Could not parse tax amount '{tax_amount}': {e}")

                # Process refunds - group by order date (not refund date)
                # This ensures refunds appear on the same row as the order for daily exports
                refunds = line.get('refunds', [])
                if not isinstance(refunds, list):
                    refunds = []

                for refund in refunds:
                    if not isinstance(refund, dict):
                        continue

                    # Add refund amount to the order date's totals (not refund date)
                    # Use the same date_key as the order so refunds appear on the same row
                    refund_amount = refund.get('amount', 0)
                    try:
                        daily_totals[date_key]['refunds'] += float(refund_amount)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse refund amount '{refund_amount}': {e}")

        # Sort by date
        sorted_dates = sorted(daily_totals.keys())
        sorted_products = sorted(all_products)

        logger.info(f"Aggregation complete: {len(sorted_dates)} unique dates, {len(sorted_products)} unique products")
        logger.info(f"Date range: {sorted_dates[0] if sorted_dates else 'N/A'} to {sorted_dates[-1] if sorted_dates else 'N/A'}")
        logger.info(f"Products: {sorted_products[:10]}{'...' if len(sorted_products) > 10 else ''}")

        # Prepare headers - merge existing products with new products
        base_headers = [
            'Date',
            'Total Daily Gross sales',
            'Total Ulta Orders',
            'Total Ulta Commission',
            'Collected Sales Tax',
            'Total Ulta Units',
            'Total Daily Refunds'
        ]

        # Merge existing products with new products, maintaining order
        # First add existing products (to preserve order), then add new ones
        all_products_ordered = []
        if has_headers and existing_header:
            # Determine fixed columns based on header format
            fixed_columns = 7  # Default to new format
            if len(existing_header) >= 6:
                if len(existing_header) == 6 or (len(existing_header) > 6 and existing_header[6].strip() != 'Total Daily Refunds'):
                    fixed_columns = 6

            # Preserve existing product order from header
            for col in existing_header[fixed_columns:]:
                if col and col.strip():
                    all_products_ordered.append(col.strip())

        # Add new products that aren't already in the header
        for product in sorted_products:
            if product not in all_products_ordered:
                all_products_ordered.append(product)

        # Sort all products alphabetically for consistency
        all_products_ordered = sorted(all_products_ordered)

        headers = base_headers + all_products_ordered

        logger.info(f"Prepared headers: {len(headers)} columns ({len(headers) - 7} product columns)")
        logger.info(f"Products in header: {len(existing_products)} existing + {len(set(sorted_products) - existing_products)} new = {len(all_products_ordered)} total")

        # Write or update headers
        if not has_headers:
            try:
                logger.info("Writing headers to Google Sheets...")
                worksheet.append_row(headers)
                logger.info(f"Successfully wrote headers: {headers[:10]}{'...' if len(headers) > 10 else ''}")
            except Exception as e:
                logger.error(f"Error writing headers: {str(e)}", exc_info=True)
                return False
        else:
            # Check if header needs to be updated (new products added)
            new_products_set = set(all_products_ordered)
            if len(new_products_set) > len(existing_products) or new_products_set != existing_products:
                new_products_count = len(new_products_set - existing_products)
                try:
                    logger.info(f"Updating header row: adding {new_products_count} new product columns")
                    # Update the header row (row 1 in gspread is 1-indexed)
                    worksheet.update('1:1', [headers])
                    logger.info(f"Successfully updated headers: {headers[:10]}{'...' if len(headers) > 10 else ''}")
                except Exception as e:
                    logger.error(f"Error updating headers: {str(e)}", exc_info=True)
                    return False
            else:
                logger.info("Headers already contain all products, no update needed")

        # Prepare data rows (always append, no duplicate checking)
        # Use all_products_ordered to match the header structure
        rows = []
        for date_key in sorted_dates:
            totals = daily_totals[date_key]
            date_formatted = totals['date'].strftime('%b %d, %Y')

            row = [
                date_formatted,
                round(totals['gross_sales'], 2),
                totals['orders_count'],
                round(totals['commission'], 2),
                round(totals['sales_tax'], 2),
                totals['units'],
                round(totals.get('refunds', 0.0), 2)
            ]
            # Add product quantities - use all_products_ordered to match header
            for product in all_products_ordered:
                quantity = totals['products'].get(product, 0)
                row.append(quantity)

            rows.append(row)
            logger.debug(f"Prepared row for {date_formatted}: {row[:10]}{'...' if len(row) > 10 else ''}")

        logger.info(f"Prepared {len(rows)} data rows to append")

        # Batch write all new rows for better performance
        if rows:
            try:
                logger.info(f"Appending {len(rows)} new rows to Google Sheets (batch operation)...")
                worksheet.append_rows(rows)
                logger.info(f"Successfully appended {len(rows)} rows to Google Sheets")

                # Verify by reading back
                try:
                    all_values = worksheet.get_all_values()
                    logger.info(f"Verification: Sheet now contains {len(all_values)} rows (including header)")
                    if len(all_values) > 1:
                        logger.info(f"Last data row: {all_values[-1][:10]}{'...' if len(all_values[-1]) > 10 else ''}")
                except Exception as e:
                    logger.warning(f"Could not verify written data: {e}")
            except Exception as e:
                logger.error(f"Error writing rows to Google Sheets: {str(e)}", exc_info=True)
                return False
        else:
            logger.warning("No rows to write to Google Sheets!")

        logger.info(f"=== Successfully exported {len(sorted_dates)} days of aggregated data to Google Sheets ===")
        return True

    except Exception as e:
        logger.error(f"Error exporting to Google Sheets: {str(e)}", exc_info=True)
        return False

