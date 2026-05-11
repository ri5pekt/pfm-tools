import csv
import logging
import os
import requests
import base64
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def fetch_one_time_vs_subscription_data(
    date_from: str,
    date_to: str,
    woo_base_url: str,
    woo_consumer_key: str,
    woo_consumer_secret: str,
    per_page: int = 300,
    update_progress: Optional[Callable[[int, str], None]] = None
) -> Dict[str, Any]:
    """
    Fetch orders from WooCommerce for a date range, aggregated by added_from meta value,
    iterating day by day to avoid server timeouts.

    Returns dict with:
        daily_data: {YYYY-MM-DD: {subscription_count, subscription_revenue,
                                   onetime_count, onetime_revenue}}
        date_from, date_to, total_days
    """
    try:
        metorik_tz = ZoneInfo('America/New_York')

        date_from_dt_utc = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        date_to_dt_utc = datetime.fromisoformat(date_to.replace('Z', '+00:00'))

        date_from_dt = datetime(
            date_from_dt_utc.year, date_from_dt_utc.month, date_from_dt_utc.day,
            0, 0, 0, tzinfo=metorik_tz
        )
        date_to_dt = datetime(
            date_to_dt_utc.year, date_to_dt_utc.month, date_to_dt_utc.day,
            23, 59, 59, tzinfo=metorik_tz
        )

        auth_string = f"{woo_consumer_key}:{woo_consumer_secret}"
        auth_b64 = base64.b64encode(auth_string.encode('ascii')).decode('ascii')

        session = requests.Session()
        session.headers.update({
            'Accept': '*/*',
            'User-Agent': 'curl/7.68.0',
            'Accept-Encoding': 'gzip, deflate',
            'X-PFM-Authorization': f'Basic {auth_b64}'
        })

        api_base = f"{woo_base_url.rstrip('/')}/wp-json/pfm-tools/v1"
        data_url = f"{api_base}/one-time-vs-subscription"

        daily_data = {}
        total_days = (date_to_dt.date() - date_from_dt.date()).days + 1
        day_num = 0
        current_date = date_from_dt

        while current_date <= date_to_dt:
            day_num += 1
            day_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            date_key = day_start.strftime('%Y-%m-%d')

            after_str = day_start.strftime('%Y-%m-%d %H:%M:%S')
            before_str = day_end.strftime('%Y-%m-%d %H:%M:%S')

            logger.info(f"Fetching one-time vs subscription data for {date_key} ({day_num}/{total_days})")

            if update_progress:
                progress = int((day_num / total_days) * 90)
                update_progress(progress, f'Fetching data for {date_key} ({day_num}/{total_days})...')

            day_subscription_count = 0
            day_subscription_revenue = 0.0
            day_onetime_count = 0
            day_onetime_revenue = 0.0

            page_num = 1
            while True:
                params = {
                    'date_after': after_str,
                    'date_before': before_str,
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
                            logger.warning(f"Timeout for {date_key} page {page_num} (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                            time.sleep(wait_time)
                        else:
                            raise
                    except requests.exceptions.RequestException as e:
                        last_exception = e
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1)
                            logger.warning(f"Error for {date_key} page {page_num} (attempt {attempt + 1}/{max_retries}): {e}, retrying in {wait_time}s...")
                            time.sleep(wait_time)
                        else:
                            raise

                if last_exception:
                    raise last_exception

                data = response.json()
                day_subscription_count += int(data.get('subscription_count', 0) or 0)
                day_subscription_revenue += float(data.get('subscription_revenue', 0) or 0)
                day_onetime_count += int(data.get('onetime_count', 0) or 0)
                day_onetime_revenue += float(data.get('onetime_revenue', 0) or 0)

                total_pages = int(response.headers.get('X-WP-TotalPages', 1))
                if page_num >= total_pages:
                    break
                page_num += 1

            daily_data[date_key] = {
                'subscription_count': day_subscription_count,
                'subscription_revenue': round(day_subscription_revenue, 2),
                'onetime_count': day_onetime_count,
                'onetime_revenue': round(day_onetime_revenue, 2),
            }

            current_date = day_end

        session.close()

        logger.info(f"Successfully fetched one-time vs subscription data for {total_days} days")
        return {
            'daily_data': daily_data,
            'date_from': date_from,
            'date_to': date_to,
            'total_days': total_days,
        }

    except Exception as e:
        logger.error(f"Error fetching one-time vs subscription data: {e}", exc_info=True)
        raise


def fetch_single_day_data(
    date_str: str,
    woo_base_url: str,
    woo_consumer_key: str,
    woo_consumer_secret: str,
    per_page: int = 300,
) -> Dict[str, Any]:
    """
    Fetch one-time vs subscription data for a single day.
    Returns dict: {subscription_count, subscription_revenue, onetime_count, onetime_revenue}
    """
    try:
        metorik_tz = ZoneInfo('America/New_York')
        date_dt = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=metorik_tz)
        day_start = date_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        after_str = day_start.strftime('%Y-%m-%d %H:%M:%S')
        before_str = day_end.strftime('%Y-%m-%d %H:%M:%S')

        auth_string = f"{woo_consumer_key}:{woo_consumer_secret}"
        auth_b64 = base64.b64encode(auth_string.encode('ascii')).decode('ascii')

        session = requests.Session()
        session.headers.update({
            'Accept': '*/*',
            'User-Agent': 'curl/7.68.0',
            'Accept-Encoding': 'gzip, deflate',
            'X-PFM-Authorization': f'Basic {auth_b64}'
        })

        api_base = f"{woo_base_url.rstrip('/')}/wp-json/pfm-tools/v1"
        data_url = f"{api_base}/one-time-vs-subscription"

        subscription_count = 0
        subscription_revenue = 0.0
        onetime_count = 0
        onetime_revenue = 0.0

        page_num = 1
        while True:
            params = {
                'date_after': after_str,
                'date_before': before_str,
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
                        time.sleep(retry_delay * (attempt + 1))
                    else:
                        raise
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))
                    else:
                        raise

            if last_exception:
                raise last_exception

            data = response.json()
            subscription_count += int(data.get('subscription_count', 0) or 0)
            subscription_revenue += float(data.get('subscription_revenue', 0) or 0)
            onetime_count += int(data.get('onetime_count', 0) or 0)
            onetime_revenue += float(data.get('onetime_revenue', 0) or 0)

            total_pages = int(response.headers.get('X-WP-TotalPages', 1))
            if page_num >= total_pages:
                break
            page_num += 1

        session.close()

        return {
            'subscription_count': subscription_count,
            'subscription_revenue': round(subscription_revenue, 2),
            'onetime_count': onetime_count,
            'onetime_revenue': round(onetime_revenue, 2),
        }

    except Exception as e:
        logger.error(f"Error fetching single day data for {date_str}: {e}", exc_info=True)
        raise


def save_to_csv(
    data: Dict[str, Any],
    output_path: str,
    update_progress: Optional[Callable[[int, str], None]] = None
) -> str:
    """
    Save one-time vs subscription data to CSV file.
    Columns: Date, Subscription Orders Count, Subscription Orders Revenue,
             One Time Orders Count, One Time Orders Revenue
    """
    logger.info(f"Saving one-time vs subscription data to CSV: {output_path}")

    daily_data = data.get('daily_data', {})

    if update_progress:
        update_progress(95, 'Writing CSV file...')

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Date',
            'Subscription Orders Count',
            'Subscription Orders Revenue',
            'One Time Orders Count',
            'One Time Orders Revenue',
        ])

        for date_key in sorted(daily_data.keys()):
            date_formatted = datetime.strptime(date_key, '%Y-%m-%d').strftime('%m/%d/%Y')
            row_data = daily_data[date_key]
            writer.writerow([
                date_formatted,
                row_data.get('subscription_count', 0),
                row_data.get('subscription_revenue', 0.0),
                row_data.get('onetime_count', 0),
                row_data.get('onetime_revenue', 0.0),
            ])

    logger.info(f"CSV file saved: {output_path}")
    return output_path


def export_single_day_to_google_sheets(
    date_str: str,
    day_data: Dict[str, Any],
    spreadsheet_id: str,
    client=None,
    worksheet=None,
    oauth_credentials_path: str = None,
    oauth_token_path: str = None,
    service_account_path: str = None,
    update_progress: Optional[Callable[[int, str], None]] = None,
) -> Tuple[object, object]:
    """
    Export a single day's data to Google Sheets incrementally.
    Sheet columns: Date | Subscription Orders Count | Subscription Orders Revenue |
                   One Time Orders Count | One Time Orders Revenue
    Returns (client, worksheet) for reuse.
    """
    import gspread
    import pickle
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import Request

    HEADERS = [
        'Date',
        'Subscription Orders Count',
        'Subscription Orders Revenue',
        'One Time Orders Count',
        'One Time Orders Revenue',
    ]

    try:
        if client is None:
            scope = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive',
            ]
            creds = None

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
            except Exception:
                worksheet = spreadsheet.add_worksheet(
                    title="One-Time vs Subscription", rows=1000, cols=10
                )

        existing_data = worksheet.get_all_values()

        # Ensure header row exists
        if not existing_data or existing_data[0] != HEADERS:
            if not existing_data:
                worksheet.append_row(HEADERS)
            else:
                worksheet.update('A1', [HEADERS])
            existing_data = worksheet.get_all_values()

        # Build date → row index map (rows are 1-indexed in Sheets)
        date_row_map = {}
        for row_idx in range(1, len(existing_data)):
            row = existing_data[row_idx]
            if row and row[0]:
                date_row_map[row[0]] = row_idx + 1

        date_formatted = datetime.strptime(date_str, '%Y-%m-%d').strftime('%m/%d/%Y')

        row_values = [
            date_formatted,
            day_data.get('subscription_count', 0),
            day_data.get('subscription_revenue', 0.0),
            day_data.get('onetime_count', 0),
            day_data.get('onetime_revenue', 0.0),
        ]

        if date_formatted in date_row_map:
            worksheet.update(f'A{date_row_map[date_formatted]}', [row_values])
            logger.info(f"Updated row for {date_formatted}")
        else:
            worksheet.append_row(row_values)
            logger.info(f"Appended new row for {date_formatted}")

        return client, worksheet

    except Exception as e:
        logger.error(f"Error exporting {date_str} to Google Sheets: {e}", exc_info=True)
        return client, worksheet


def export_to_google_sheets(
    data: Dict[str, Any],
    spreadsheet_id: str,
    oauth_credentials_path: str = None,
    oauth_token_path: str = None,
    service_account_path: str = None,
    update_progress: Optional[Callable[[int, str], None]] = None,
) -> bool:
    """
    Export full date-range data to Google Sheets.
    """
    import gspread
    import pickle
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import Request

    HEADERS = [
        'Date',
        'Subscription Orders Count',
        'Subscription Orders Revenue',
        'One Time Orders Count',
        'One Time Orders Revenue',
    ]

    logger.info(f"Exporting one-time vs subscription data to Google Sheets: {spreadsheet_id}")

    try:
        scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive',
        ]
        creds = None
        auth_method = None

        if oauth_credentials_path and oauth_token_path and os.path.exists(oauth_token_path):
            try:
                with open(oauth_token_path, 'rb') as token:
                    creds = pickle.load(token)
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(oauth_token_path, 'wb') as token:
                        pickle.dump(creds, token)
                if creds.valid:
                    auth_method = "OAuth"
            except Exception as e:
                logger.warning(f"Could not load OAuth token: {e}")
                creds = None

        if not creds and service_account_path and os.path.exists(service_account_path):
            try:
                creds = Credentials.from_service_account_file(service_account_path, scopes=scope)
                auth_method = "Service Account"
            except Exception as e:
                logger.warning(f"Could not load service account credentials: {e}")
                creds = None

        if not creds:
            logger.error("No valid Google credentials found.")
            return False

        logger.info(f"Using {auth_method} authentication")
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(spreadsheet_id)

        try:
            worksheet = spreadsheet.sheet1
        except Exception:
            worksheet = spreadsheet.add_worksheet(
                title="One-Time vs Subscription", rows=1000, cols=10
            )

        existing_data = worksheet.get_all_values()

        if not existing_data or existing_data[0] != HEADERS:
            if not existing_data:
                worksheet.append_row(HEADERS)
            else:
                worksheet.update('A1', [HEADERS])
            existing_data = worksheet.get_all_values()

        date_row_map = {}
        for row_idx in range(1, len(existing_data)):
            row = existing_data[row_idx]
            if row and row[0]:
                date_row_map[row[0]] = row_idx + 1

        daily_data = data.get('daily_data', {})
        sorted_dates = sorted(daily_data.keys())

        new_rows = []
        updated_rows = []

        for date_key in sorted_dates:
            date_formatted = datetime.strptime(date_key, '%Y-%m-%d').strftime('%m/%d/%Y')
            row_data = daily_data[date_key]
            row_values = [
                date_formatted,
                row_data.get('subscription_count', 0),
                row_data.get('subscription_revenue', 0.0),
                row_data.get('onetime_count', 0),
                row_data.get('onetime_revenue', 0.0),
            ]
            if date_formatted in date_row_map:
                updated_rows.append((date_row_map[date_formatted], row_values))
            else:
                new_rows.append(row_values)

        if update_progress:
            update_progress(80, f'Updating {len(updated_rows)} existing rows...')

        for row_idx, row_values in updated_rows:
            worksheet.update(f'A{row_idx}', [row_values])

        if new_rows:
            if update_progress:
                update_progress(90, f'Adding {len(new_rows)} new rows...')
            worksheet.append_rows(new_rows)

        logger.info("Successfully exported data to Google Sheets")
        return True

    except Exception as e:
        logger.error(f"Error exporting to Google Sheets: {e}", exc_info=True)
        return False
