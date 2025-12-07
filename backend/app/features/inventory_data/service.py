import csv
import logging
import os
import zipfile
from typing import Dict, List, Any
from datetime import datetime

from .zenventory_client import ZenventoryClient
from .shipbob_client import ShipbobClient

logger = logging.getLogger(__name__)

# ====== CONFIG: HARDCODED PRODUCT LIST ======
HARDCODED_PRODUCTS = [
    {"title": "Scalp Massager", "sku": "9162027"},
    {"title": "Ab Firming Cream", "sku": "860010338421"},
    {"title": "Particle Face Cream", "sku": "751889384926"},
    {"title": "Particle Shampoo", "sku": "636665869661"},
    {"title": "Particle Body Wash", "sku": "636665869678"},
    {"title": "Particle Face Mask", "sku": "636665869654"},
    {"title": "Particle Skin Vitamin Gummy", "sku": "860005339747"},
    {"title": "Particle Beard Oil", "sku": "860005339723"},
    {"title": "Particle Face Wash", "sku": "636665869647"},
    {"title": "Particle Brochure", "sku": "6003.0002"},
    {"title": "Particle Neck Cream", "sku": "860005339778"},
    {"title": "Particle Dark Spot Hand Cream", "sku": "00860014497216"},
    {"title": "Particle Hair Vitamin Gummy", "sku": "860005339761"},
    {"title": "Particle Scar Gel", "sku": "860005339716"},
    {"title": "Particle Gravite Cologne", "sku": "860005339785"},
    {"title": "Particle Hair Revival Kit", "sku": "860005339730"},
    {"title": "Particle Mailing box", "sku": "6005.0002"},
    {"title": "Sample Card - Gravite", "sku": "00860010338438"},
    {"title": "Face Cream Sample", "sku": "860010338452"},
    {"title": "Particle Anti-Gray Serum", "sku": "860012469703"},
    {"title": "Particle Invisible Sunscreen", "sku": "860010338483"},
    {"title": "Particle Infinite Male", "sku": "860012469727"},
    {"title": "Amazon Insert", "sku": "00860010338490"},
    {"title": "Particle Gravite Deodorant", "sku": "860012469710"},
    {"title": "Particle Wraping Silk Paper", "sku": "6003.0004"},
    {"title": "Particle Sticker", "sku": "6003.0005"},
    {"title": "Amazon Insert B", "sku": "00860012469734"},
    {"title": "TikTok Marketing Insert", "sku": "00860012469741"},
    {"title": "Branded one-unit shipper box", "sku": "6005.0003"},
    {"title": "One-Unit Shipper Box Stage (Part B)", "sku": "6005.0003B"},
    {"title": "Particle Shaving Cream Stand + Hourglass", "sku": "00860012469758"},
    {"title": "Particle Shaving Cream", "sku": "00860012469772"},
    {"title": "Varros Perfume - 100ml", "sku": "00860012469765"},
]


def fetch_zenventory_klb_inventory(username: str, password: str, base_url: str = None) -> Dict[str, int]:
    """
    Fetch inventory from Zenventory KLB API for all hardcoded products.

    Args:
        username: Zenventory API username
        password: Zenventory API password
        base_url: Zenventory API base URL (optional)

    Returns:
        Dictionary mapping SKU to quantity
    """
    client = ZenventoryClient(username=username, password=password, base_url=base_url)

    # Get all SKUs from hardcoded products
    skus = [product["sku"] for product in HARDCODED_PRODUCTS]

    # Fetch inventory for these SKUs
    inventory = client.get_inventory_by_skus(skus)

    return inventory


def fetch_shipbob_inventory(api_key: str, base_url: str = None) -> Dict[str, int]:
    """
    Fetch inventory from Shipbob API for all hardcoded products.
    DEPRECATED: Use fetch_shipbob_inventory_by_locations instead.

    Args:
        api_key: Shipbob API key
        base_url: Shipbob API base URL (optional)

    Returns:
        Dictionary mapping SKU to quantity
    """
    client = ShipbobClient(api_key=api_key, base_url=base_url)

    # Get all SKUs from hardcoded products
    skus = [product["sku"] for product in HARDCODED_PRODUCTS]

    # Fetch inventory for these SKUs
    inventory = client.get_inventory_by_skus(skus)

    return inventory


def fetch_shipbob_inventory_by_locations(api_key: str, base_url: str = None) -> Dict[str, Dict[str, int]]:
    """
    Fetch inventory from Shipbob API by locations for all hardcoded products.

    Args:
        api_key: Shipbob API key
        base_url: Shipbob API base URL (optional)

    Returns:
        Dictionary mapping SKU to location quantities
        Example: {"SKU123": {"us_pa_ne_hub_1": 10, "dayton_nj": 5}}
    """
    client = ShipbobClient(api_key=api_key, base_url=base_url)

    # Define locations we care about
    locations = {
        "US (PA) Northeast Hub 1": "us_pa_ne_hub_1",
        "Dayton (NJ)": "dayton_nj",
        "US (GA) Southeast Hub 1": "us_ga_se_hub_1",
        "Fresno (CA)": "fresno_ca",
        "Grapevine (TX)": "grapevine_tx",
        "Dropp Logistics (Fairburn) Fulfillment Center": "dropp_fairburn",
        "Fairburn (GA)": "fairburn_ga",
    }

    # Fetch location-based inventory
    all_inventory = client.get_inventory_by_locations(locations)

    # Filter to only include hardcoded product SKUs
    skus = set(str(product["sku"]).strip() for product in HARDCODED_PRODUCTS)
    filtered_inventory = {
        sku: loc_data
        for sku, loc_data in all_inventory.items()
        if str(sku).strip() in skus
    }

    return filtered_inventory, locations


def create_inventory_csv(
    inventory_data: Dict[str, int],
    warehouse_name: str,
    output_path: str,
    export_date: str = None
) -> str:
    """
    Create a CSV file with inventory data.

    Args:
        inventory_data: Dictionary mapping SKU to quantity
        warehouse_name: Name of the warehouse (e.g., "Zenventory KLB")
        output_path: Path where CSV should be saved
        export_date: Export date in YYYY-MM-DD format

    Returns:
        Path to saved CSV file
    """
    logger.info(f"Creating CSV for {warehouse_name}: {output_path}")

    # Get export date (today if not provided)
    if not export_date:
        export_date = datetime.now().strftime("%Y-%m-%d")

    # Create a mapping from SKU to product title for better CSV readability
    sku_to_title = {product["sku"]: product["title"] for product in HARDCODED_PRODUCTS}

    # Write CSV file
    # Use 'utf-8-sig' encoding to add BOM for Excel compatibility
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)

        # Write headers - Date first, then SKU, Product Title, Quantity
        headers = ["Export Date", "SKU", "Product Title", "Quantity"]
        writer.writerow(headers)

        # Write data rows - include all hardcoded products, even if quantity is 0
        for product in HARDCODED_PRODUCTS:
            sku = product["sku"]
            title = product["title"]
            quantity = inventory_data.get(sku, 0)

            # Only write rows with non-zero quantity (matching the original logic)
            if quantity > 0:
                # Save SKU as string with leading apostrophe to force Excel to treat it as text
                # This prevents Excel from converting SKUs like "00860010338438" to numbers
                sku_str = f"'{str(sku)}"
                writer.writerow([export_date, sku_str, title, quantity])

    logger.info(f"Successfully created CSV for {warehouse_name}: {len([q for q in inventory_data.values() if q > 0])} products with inventory")
    return output_path


def create_location_inventory_csv(
    location_inventory_data: Dict[str, Dict[str, int]],
    location_key: str,
    location_name: str,
    output_path: str,
    export_date: str = None
) -> str:
    """
    Create a CSV file with inventory data for a specific location.

    Args:
        location_inventory_data: Dictionary mapping SKU to location quantities
                                Example: {"SKU123": {"us_pa_ne_hub_1": 10, "dayton_nj": 5}}
        location_key: Internal location key (e.g., "us_pa_ne_hub_1")
        location_name: Display name for the location (e.g., "US (PA) Northeast Hub 1")
        output_path: Path where CSV should be saved
        export_date: Export date in YYYY-MM-DD format

    Returns:
        Path to saved CSV file
    """
    logger.info(f"Creating CSV for {location_name}: {output_path}")

    # Get export date (today if not provided)
    if not export_date:
        export_date = datetime.now().strftime("%Y-%m-%d")

    # Create a mapping from SKU to product title for better CSV readability
    sku_to_title = {product["sku"]: product["title"] for product in HARDCODED_PRODUCTS}

    # Write CSV file
    # Use 'utf-8-sig' encoding to add BOM for Excel compatibility
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)

        # Write headers - Date first, then SKU, Product Title, Quantity
        headers = ["Export Date", "SKU", "Product Title", "Quantity"]
        writer.writerow(headers)

        # Write data rows - include all hardcoded products, even if quantity is 0
        for product in HARDCODED_PRODUCTS:
            sku = product["sku"]
            title = product["title"]

            # Get quantity for this location
            quantity = 0
            if sku in location_inventory_data and location_key in location_inventory_data[sku]:
                quantity = location_inventory_data[sku][location_key]

            # Write all products, including those with 0 quantity
            # Save SKU as string with leading apostrophe to force Excel to treat it as text
            sku_str = f"'{str(sku)}"
            writer.writerow([export_date, sku_str, title, quantity])

    logger.info(f"Successfully created CSV for {location_name}: {len([sku for sku, locs in location_inventory_data.items() if locs.get(location_key, 0) > 0])} products with inventory")
    return output_path


def create_inventory_zip(csv_files: List[Dict[str, str]], output_path: str) -> str:
    """
    Create a ZIP archive containing multiple CSV files.

    Args:
        csv_files: List of dictionaries with 'path' and 'name' keys
                   Example: [{"path": "/path/to/file.csv", "name": "zenventory_klb.csv"}]
        output_path: Path where ZIP should be saved

    Returns:
        Path to saved ZIP file
    """
    logger.info(f"Creating ZIP archive: {output_path} with {len(csv_files)} CSV files")

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for csv_file in csv_files:
            csv_path = csv_file.get("path")
            csv_name = csv_file.get("name")

            if not csv_path or not os.path.exists(csv_path):
                logger.warning(f"CSV file not found: {csv_path}, skipping")
                continue

            # Add file to ZIP with the specified name
            zipf.write(csv_path, csv_name)
            logger.info(f"Added {csv_name} to ZIP archive")

    logger.info(f"Successfully created ZIP archive: {output_path}")
    return output_path


def export_inventory_to_google_sheets(
    inventory_data: Dict[str, int],
    spreadsheet_id: str,
    sheet_name: str,
    export_date: str,
    oauth_credentials_path: str = None,
    oauth_token_path: str = None,
    service_account_path: str = None,
) -> bool:
    """
    Export inventory data to Google Sheets in the format: SKU, Item Title, [Date columns]
    Each export adds a new date column to the right if the sheet exists, or creates a new sheet.

    Args:
        inventory_data: Dictionary mapping SKU to quantity
        spreadsheet_id: Google Sheets spreadsheet ID
        sheet_name: Name of the sheet to write to
        export_date: Export date in YYYY-MM-DD format (will be formatted as MM/DD/YY)
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

    logger.info(f"Exporting inventory to Google Sheets: {spreadsheet_id}/{sheet_name}")

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

                    # Refresh token if expired
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

        # Get or create the sheet (case-insensitive matching)
        worksheet = None
        try:
            # List all worksheets to find a case-insensitive match
            all_worksheets = spreadsheet.worksheets()
            logger.info(f"Available sheets in spreadsheet: {[ws.title for ws in all_worksheets]}")

            # Try exact match first
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                logger.info(f"Found existing sheet (exact match): {sheet_name}")
            except gspread.exceptions.WorksheetNotFound:
                # Try case-insensitive match
                for ws in all_worksheets:
                    if ws.title.lower() == sheet_name.lower():
                        worksheet = ws
                        logger.info(f"Found existing sheet (case-insensitive match): '{ws.title}' (requested: '{sheet_name}')")
                        break

                if not worksheet:
                    # Sheet not found, create new one
                    logger.info(f"Sheet '{sheet_name}' not found, creating new sheet...")
                    worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=50)
                    logger.info(f"Created new sheet: {sheet_name}")

        except Exception as e:
            logger.error(f"Error accessing sheet '{sheet_name}': {str(e)}", exc_info=True)
            return False

        # Format date as MM/DD/YY (e.g., "01/01/25")
        try:
            date_obj = datetime.strptime(export_date, "%Y-%m-%d")
            date_formatted = date_obj.strftime("%m/%d/%y")
        except Exception:
            date_formatted = export_date  # Fallback to original format

        # Read existing data with retry logic for rate limiting
        import time
        max_retries = 3
        retry_delay = 5
        existing_data = []
        has_headers = False

        for attempt in range(max_retries):
            try:
                existing_data = worksheet.get_all_values()
                has_headers = len(existing_data) > 0
                break
            except Exception as e:
                if "429" in str(e) or "Quota exceeded" in str(e):
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        logger.warning(f"Rate limit hit, waiting {wait_time} seconds before retry {attempt + 1}/{max_retries}")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Rate limit exceeded after {max_retries} attempts")
                        raise
                else:
                    raise

        # Create SKU to title mapping
        sku_to_title = {product["sku"]: product["title"] for product in HARDCODED_PRODUCTS}

        # Validate headers - should be ["SKU", "Item Title", ...]
        headers_valid = False
        if has_headers and len(existing_data[0]) >= 2:
            first_header = str(existing_data[0][0]).strip() if existing_data[0] else ""
            second_header = str(existing_data[0][1]).strip() if len(existing_data[0]) > 1 else ""
            headers_valid = (first_header == "SKU" and second_header == "Item Title")

        if not has_headers or not headers_valid:
            # Create new sheet with headers or fix existing headers
            if not headers_valid and has_headers:
                logger.warning(f"Sheet '{worksheet.title}' has invalid headers, fixing them...")
                # Clear the sheet and start fresh
                worksheet.clear()
                existing_data = []
                has_headers = False

            logger.info(f"Sheet '{worksheet.title}' is empty or has invalid headers, creating headers and data...")
            headers = ["SKU", "Item Title", date_formatted]
            worksheet.append_row(headers)

            # Add all products in batches for better performance
            all_rows = []
            for product in HARDCODED_PRODUCTS:
                sku = product["sku"]
                title = product["title"]
                quantity = inventory_data.get(sku, 0)
                sku_str = f"'{str(sku)}"  # Add apostrophe to force text format
                all_rows.append([sku_str, title, quantity])

            # Append rows in batches
            batch_size = 100
            for i in range(0, len(all_rows), batch_size):
                batch = all_rows[i:i + batch_size]
                worksheet.append_rows(batch)
                logger.info(f"Appended {len(batch)} rows in batch {i // batch_size + 1}")
                if i + batch_size < len(all_rows):
                    time.sleep(0.5)  # Wait between batches

            logger.info(f"Successfully created new sheet with {len(HARDCODED_PRODUCTS)} products")
        else:
            # Sheet exists - always add new date column (even if same date exists)
            logger.info(f"Sheet '{worksheet.title}' exists, adding new date column: {date_formatted}")

            # Get existing headers
            existing_headers = existing_data[0] if existing_data else []
            logger.info(f"Existing headers: {existing_headers}")

            # Always add new date column to the right (don't check if date already exists)
            new_col_index = len(existing_headers) + 1
            worksheet.update_cell(1, new_col_index, date_formatted)
            logger.info(f"Added new date column header '{date_formatted}' at column {new_col_index}")
            # Wait a moment for the update to complete
            time.sleep(0.5)
            date_col_index = new_col_index - 1  # Convert to 0-based index

            # Update or add rows for all products
            # First, create a mapping of existing SKUs to row numbers
            sku_to_row = {}
            row_to_sku = {}  # Reverse mapping for easier lookup
            for row_idx, row in enumerate(existing_data[1:], start=2):  # Skip header row
                if len(row) > 0:
                    sku = str(row[0]).strip().lstrip("'")  # Remove apostrophe if present
                    sku_to_row[sku] = row_idx
                    row_to_sku[row_idx] = sku

            # Convert column index to letter helper
            def col_index_to_letter(col_idx):
                result = ""
                col_idx += 1  # Convert to 1-based
                while col_idx > 0:
                    col_idx -= 1
                    result = chr(65 + (col_idx % 26)) + result
                    col_idx //= 26
                return result

            col_letter = col_index_to_letter(date_col_index)

            # Update existing rows - build values array in the exact order they appear in the sheet
            if sku_to_row:
                existing_row_nums = sorted(sku_to_row.values())
                values = []
                for row_num in existing_row_nums:
                    sku = row_to_sku[row_num]
                    quantity = inventory_data.get(sku, 0)
                    values.append([quantity])

                # Update the entire column at once
                range_start = f"{col_letter}{existing_row_nums[0]}"
                range_end = f"{col_letter}{existing_row_nums[-1]}"
                range_str = f"{range_start}:{range_end}"

                try:
                    worksheet.update(range_str, values, value_input_option='USER_ENTERED')
                    logger.info(f"Updated {len(values)} existing rows in column {col_letter} (range {range_str})")
                    time.sleep(1.5)  # Wait longer for update to complete
                except Exception as e:
                    logger.warning(f"Column update failed, falling back to individual updates: {e}")
                    # Fallback to individual updates with proper delays
                    for row_num, value_list in zip(existing_row_nums, values):
                        worksheet.update_cell(row_num, date_col_index + 1, value_list[0])
                        time.sleep(0.15)  # Delay between individual updates

            # Add new rows for products that don't exist yet
            rows_to_append = []
            for product in HARDCODED_PRODUCTS:
                sku = str(product["sku"]).strip()
                if sku not in sku_to_row:
                    # Add new row
                    title = product["title"]
                    quantity = inventory_data.get(sku, 0)
                    sku_str = f"'{sku}"
                    new_row = [sku_str, title]
                    # Pad with empty cells to reach the date column
                    while len(new_row) < date_col_index:
                        new_row.append("")
                    new_row.append(quantity)
                    rows_to_append.append(new_row)

            # Append new rows in smaller batches with longer delays
            if rows_to_append:
                try:
                    # Use smaller batches and longer delays for reliability
                    batch_size = 25  # Smaller batches
                    for i in range(0, len(rows_to_append), batch_size):
                        batch = rows_to_append[i:i + batch_size]
                        worksheet.append_rows(batch)
                        logger.info(f"Appended {len(batch)} new rows in batch {i // batch_size + 1}")
                        time.sleep(1.5)  # Wait longer between batches to ensure completion
                except Exception as e:
                    logger.warning(f"Batch append failed, falling back to individual appends: {e}")
                    # Fallback to individual appends with delays
                    for row in rows_to_append:
                        worksheet.append_row(row)
                        time.sleep(0.2)  # Delay between individual appends

            logger.info(f"Successfully updated sheet: {len(sku_to_row)} existing rows updated, {len(rows_to_append)} new rows added")

        logger.info(f"=== Successfully exported inventory data to Google Sheets ===")
        return True

    except Exception as e:
        logger.error(f"Error exporting to Google Sheets: {str(e)}", exc_info=True)
        return False

