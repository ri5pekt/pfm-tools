import base64
import csv
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Any
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

METORIK_TZ = ZoneInfo("America/New_York")

# Google Sheets tab names
CREATORS_TAB = "Creators"
SEGMENT_TABS = ["Segment 1", "Segment 2", "Segment 3"]
SEGMENT_HEADERS = ["Date", "Influencer Name", "Orders", "Revenue", "Items Sold", "Product Name"]


# ---------------------------------------------------------------------------
# WooCommerce fetch
# ---------------------------------------------------------------------------

def fetch_yt_influencers_orders(
    date: str,
    woo_base_url: str,
    woo_consumer_key: str,
    woo_consumer_secret: str,
    per_page: int = 300,
    update_progress: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Fetch orders for a given date from the /pfm-tools/v1/yt-influencers-orders endpoint.

    Each order contains: id, date_created, total (USD), utm_campaign, coupon_codes, line_items.

    `date` is an ISO timestamp like "2025-11-01T00:00:00.000Z".
    The plugin filters by America/New_York day boundaries matching Metorik.
    """
    metorik_tz = ZoneInfo("America/New_York")

    date_dt_utc = datetime.fromisoformat(date.replace("Z", "+00:00"))
    date_dt_ny = datetime(
        date_dt_utc.year, date_dt_utc.month, date_dt_utc.day,
        0, 0, 0,
        tzinfo=metorik_tz,
    )
    end_dt_ny = date_dt_ny + timedelta(days=1)

    after_str = date_dt_ny.strftime("%Y-%m-%d %H:%M:%S")
    before_str = end_dt_ny.strftime("%Y-%m-%d %H:%M:%S")

    api_url = f"{woo_base_url.rstrip('/')}/wp-json/pfm-tools/v1/yt-influencers-orders"

    auth_b64 = base64.b64encode(f"{woo_consumer_key}:{woo_consumer_secret}".encode()).decode()
    session = requests.Session()
    session.headers.update({
        "Accept": "*/*",
        "User-Agent": "curl/7.68.0",
        "Accept-Encoding": "gzip, deflate",
        "X-PFM-Authorization": f"Basic {auth_b64}",
    })

    all_orders: List[dict] = []
    page = 1
    total_pages = None
    fetch_start = time.time()

    logger.info(f"[yt_influencers] Fetching orders for {after_str} → {before_str} (NY tz)")

    while True:
        params = {
            "date_after": after_str,
            "date_before": before_str,
            "per_page": per_page,
            "page": page,
        }

        for attempt in range(3):
            try:
                resp = session.get(api_url, params=params, timeout=300)
                resp.raise_for_status()
                break
            except requests.exceptions.RequestException as exc:
                if attempt < 2:
                    wait = 2 * (attempt + 1)
                    logger.warning(f"Attempt {attempt + 1}/3 failed (page {page}): {exc}, retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise

        data = resp.json()

        if total_pages is None:
            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            total_count = int(resp.headers.get("X-WP-Total", 0))
            logger.info(f"[yt_influencers] Total orders: {total_count} across {total_pages} page(s)")

        page_orders = data.get("orders", [])
        all_orders.extend(page_orders)

        if update_progress:
            pct = min(50, int((page / total_pages) * 50)) if total_pages else 20
            update_progress(pct, f"Fetching orders… page {page}/{total_pages} ({len(all_orders)} so far)")

        logger.info(f"[yt_influencers] Page {page}/{total_pages}: {len(page_orders)} orders")

        if page >= total_pages or not page_orders:
            break
        page += 1

    session.close()
    logger.info(f"[yt_influencers] Fetched {len(all_orders)} orders in {time.time() - fetch_start:.1f}s")

    return {"orders": all_orders, "total_count": len(all_orders)}


# ---------------------------------------------------------------------------
# Segment logic
# ---------------------------------------------------------------------------

def _norm_utm(value: str) -> str:
    """Normalise a UTM campaign string: lowercase and strip separators so that
    'FrankSloup', 'frank_sloup', and 'frank-sloup' all become 'franksloup'."""
    return value.strip().lower().replace("_", "").replace("-", "").replace(" ", "")


def _build_lookup_maps(creators: List[dict]):
    """
    Build two lookup dicts from the Creators list.
    UTM keys are normalised (lowercase, no underscores/hyphens/spaces).
    Coupon keys are lowercase only (coupons are exact codes).
    """
    utms: Dict[str, dict] = {}
    coupons: Dict[str, dict] = {}
    for c in creators:
        utm = _norm_utm(c.get("utm_campaign") or "")
        coupon = (c.get("coupon") or "").strip().lower()
        if utm:
            utms[utm] = c
        if coupon:
            coupons[coupon] = c
    return utms, coupons


def classify_orders(orders: List[dict], creators: List[dict]) -> Dict[str, List[tuple]]:
    """
    Classify each order into Segment 1, 2, or 3.

    Segment 1 : UTM matches an influencer  AND  order has the same influencer's coupon
    Segment 2 : UTM matches an influencer  AND  no matching influencer coupon on the order
    Segment 3 : order has a matching influencer coupon  AND  UTM does NOT match any influencer

    Returns {"segment1": [(order, creator), ...], "segment2": [...], "segment3": [...]}
    """
    utms_map, coupons_map = _build_lookup_maps(creators)

    # Diagnostic: log creator UTMs and coupon keys we're matching against
    logger.info(f"[yt_influencers] Creator UTM keys   : {sorted(utms_map.keys())}")
    logger.info(f"[yt_influencers] Creator coupon keys: {sorted(coupons_map.keys())}")

    # Diagnostic: log unique non-empty UTM values seen in the orders (normalised)
    order_utms_raw = {(o.get("utm_campaign") or "").strip() for o in orders}
    order_utms_raw.discard("")
    logger.info(f"[yt_influencers] Unique order UTMs (raw)  : {sorted(order_utms_raw)[:30]}")
    order_utms_norm = {_norm_utm(u) for u in order_utms_raw}
    logger.info(f"[yt_influencers] Unique order UTMs (norm) : {sorted(order_utms_norm)[:30]}")

    # Diagnostic: count orders with/without UTM
    with_utm = sum(1 for o in orders if (o.get("utm_campaign") or "").strip())
    logger.info(f"[yt_influencers] Orders with non-empty UTM: {with_utm}/{len(orders)}")

    result: Dict[str, List[tuple]] = {"segment1": [], "segment2": [], "segment3": []}

    for order in orders:
        order_utm = _norm_utm(order.get("utm_campaign") or "")
        order_coupons = [str(c).strip().lower() for c in (order.get("coupon_codes") or []) if c]

        utm_creator = utms_map.get(order_utm) if order_utm else None

        coupon_creator = None
        for c in order_coupons:
            if c in coupons_map:
                coupon_creator = coupons_map[c]
                break

        if utm_creator and coupon_creator:
            result["segment1"].append((order, utm_creator))
        elif utm_creator and not coupon_creator:
            result["segment2"].append((order, utm_creator))
        elif coupon_creator and not utm_creator:
            result["segment3"].append((order, coupon_creator))
        # orders that match neither are not influencer orders — skip

    return result


def aggregate_segment(segment_orders: List[tuple], base_date: str) -> List[dict]:
    """
    Group orders by influencer, compute Orders / Revenue / Items Sold / Product Name.
    Returns a list of row dicts matching SEGMENT_HEADERS.
    """
    groups: Dict[str, dict] = {}

    for order, creator in segment_orders:
        name = creator.get("creator", "Unknown")
        if name not in groups:
            groups[name] = {"orders": 0, "revenue": 0.0, "items_sold": 0, "products": set()}
        groups[name]["orders"] += 1
        groups[name]["revenue"] += float(order.get("total") or 0)
        for item in order.get("line_items") or []:
            groups[name]["items_sold"] += int(item.get("quantity") or 0)
            product_name = (item.get("name") or "").strip()
            if product_name:
                groups[name]["products"].add(product_name)

    rows = []
    for influencer_name, stats in sorted(groups.items()):
        rows.append({
            "Date": base_date,
            "Influencer Name": influencer_name,
            "Orders": stats["orders"],
            "Revenue": round(stats["revenue"], 2),
            "Items Sold": stats["items_sold"],
            "Product Name": ", ".join(sorted(stats["products"])),
        })
    return rows


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def save_yt_influencers_to_csv(
    data: dict,
    output_path: str,
    selected_date: str,
    update_progress: Optional[Callable] = None,
) -> None:
    """
    Save raw YT Influencer orders to a CSV file for debugging / archiving.
    """
    if update_progress:
        update_progress(60, "Saving orders to CSV…")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    orders = data.get("orders", [])

    fieldnames = ["id", "date_created", "total", "utm_campaign", "coupon_codes", "products"]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for order in orders:
            writer.writerow({
                "id": order.get("id"),
                "date_created": order.get("date_created"),
                "total": order.get("total"),
                "utm_campaign": order.get("utm_campaign"),
                "coupon_codes": "|".join(order.get("coupon_codes") or []),
                "products": "|".join(
                    f"{i.get('name')} x{i.get('quantity')}"
                    for i in (order.get("line_items") or [])
                ),
            })

    logger.info(f"[yt_influencers] CSV saved to {output_path} ({len(orders)} orders)")
    if update_progress:
        update_progress(70, f"CSV saved ({len(orders)} orders)")


# ---------------------------------------------------------------------------
# Google Sheets helpers
# ---------------------------------------------------------------------------

def _get_gspread_client(
    oauth_credentials_path: Optional[str],
    oauth_token_path: Optional[str],
    service_account_path: Optional[str],
):
    import gspread
    import pickle
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import Request

    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = None

    if oauth_credentials_path and oauth_token_path and os.path.exists(oauth_token_path):
        try:
            with open(oauth_token_path, "rb") as fh:
                creds = pickle.load(fh)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(oauth_token_path, "wb") as fh:
                    pickle.dump(creds, fh)
            if not creds.valid:
                creds = None
        except Exception as exc:
            logger.warning(f"Could not load OAuth token: {exc}")
            creds = None

    if not creds and service_account_path and os.path.exists(service_account_path):
        try:
            creds = Credentials.from_service_account_file(service_account_path, scopes=scope)
        except Exception as exc:
            logger.warning(f"Could not load service account: {exc}")
            creds = None

    if not creds:
        raise RuntimeError("No valid Google credentials found (OAuth token or service account)")

    return gspread.authorize(creds)


def _get_or_create_worksheet(spreadsheet, tab_name: str):
    """Return the worksheet named tab_name, creating it with the standard header if absent.
    Also removes any duplicate header rows that may have been inserted by a previous bug.
    """
    import gspread

    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(SEGMENT_HEADERS))
        ws.append_row(SEGMENT_HEADERS, value_input_option="RAW")
        logger.info(f"[yt_influencers] Created tab '{tab_name}'")
        return ws

    # Tab already exists — ensure row 1 is the correct header
    existing = ws.row_values(1)
    if existing != SEGMENT_HEADERS:
        ws.insert_row(SEGMENT_HEADERS, index=1, value_input_option="RAW")
        logger.info(f"[yt_influencers] Wrote header to '{tab_name}'")

    # Remove any duplicate header rows (row 2 onwards that equal SEGMENT_HEADERS)
    all_values = ws.get_all_values()
    dup_rows = [
        i + 1  # 1-based sheet row
        for i, row in enumerate(all_values[1:], start=1)
        if row == SEGMENT_HEADERS
    ]
    for row_idx in reversed(dup_rows):
        ws.delete_rows(row_idx + 1)
    if dup_rows:
        logger.info(f"[yt_influencers] Removed {len(dup_rows)} duplicate header row(s) from '{tab_name}'")

    return ws


def _remove_rows_for_date(ws, base_date: str) -> int:
    """
    Delete all data rows (not header) where column A (Date) == base_date.
    Returns the number of rows deleted.
    """
    all_values = ws.get_all_values()
    if len(all_values) <= 1:
        return 0

    # Build a list of 1-based sheet row numbers to delete.
    # all_values[0] is the header (sheet row 1), all_values[1] is sheet row 2, etc.
    to_delete = [
        i + 1  # convert 0-based all_values index → 1-based sheet row
        for i, row in enumerate(all_values)
        if i > 0 and row and row[0] == base_date
    ]

    if not to_delete:
        return 0

    # Delete from bottom up to keep row numbers stable
    for row_idx in reversed(to_delete):
        ws.delete_rows(row_idx)

    logger.info(f"[yt_influencers] Removed {len(to_delete)} existing row(s) for {base_date} from '{ws.title}'")
    return len(to_delete)


def _write_rows_to_sheet(ws, rows: List[dict], base_date: str) -> None:
    """Remove existing rows for the date, then append fresh rows."""
    _remove_rows_for_date(ws, base_date)

    if not rows:
        logger.info(f"[yt_influencers] No data to write to '{ws.title}' for {base_date}")
        return

    values = [
        [
            row["Date"],
            row["Influencer Name"],
            row["Orders"],
            row["Revenue"],
            row["Items Sold"],
            row["Product Name"],
        ]
        for row in rows
    ]
    ws.append_rows(values, value_input_option="USER_ENTERED")
    logger.info(f"[yt_influencers] Wrote {len(values)} row(s) to '{ws.title}' for {base_date}")


# ---------------------------------------------------------------------------
# Main Google Sheets export
# ---------------------------------------------------------------------------

def export_to_google_sheets(
    data: dict,
    base_date: str,
    spreadsheet_id: str,
    oauth_credentials_path: Optional[str] = None,
    oauth_token_path: Optional[str] = None,
    service_account_path: Optional[str] = None,
    update_progress: Optional[Callable] = None,
) -> bool:
    """
    Full pipeline:
      1. Authenticate with Google Sheets
      2. Read the 'Creators' tab to get UTM→creator and coupon→creator mappings
      3. Classify orders into Segment 1 / 2 / 3
      4. Aggregate each segment by influencer
      5. Write results to each segment tab (removing old rows for base_date first)

    Returns True on success, False on failure.
    """
    try:
        if update_progress:
            update_progress(75, "Connecting to Google Sheets…")

        client = _get_gspread_client(oauth_credentials_path, oauth_token_path, service_account_path)
        spreadsheet = client.open_by_key(spreadsheet_id)

        # --- Read Creators mapping ---
        if update_progress:
            update_progress(78, "Reading Creators tab…")

        try:
            creators_ws = spreadsheet.worksheet(CREATORS_TAB)
        except Exception:
            logger.error(f"[yt_influencers] 'Creators' tab not found in spreadsheet {spreadsheet_id}")
            return False

        creators_raw = creators_ws.get_all_values()
        if not creators_raw:
            logger.error("[yt_influencers] Creators tab is empty")
            return False

        header = [h.strip() for h in creators_raw[0]]
        try:
            creator_col = header.index("Creator")
            utm_col     = header.index("UTM_Campaign")
            coupon_col  = header.index("Coupon")
        except ValueError as exc:
            logger.error(f"[yt_influencers] Missing column in Creators tab: {exc}")
            return False

        creators: List[dict] = []
        for row in creators_raw[1:]:
            if len(row) <= max(creator_col, utm_col, coupon_col):
                continue
            creator_name = row[creator_col].strip()
            utm_val      = row[utm_col].strip()
            coupon_val   = row[coupon_col].strip()
            if creator_name or utm_val or coupon_val:
                creators.append({"creator": creator_name, "utm_campaign": utm_val, "coupon": coupon_val})

        logger.info(f"[yt_influencers] Loaded {len(creators)} creator mapping(s) from Creators tab")

        # --- Classify orders ---
        if update_progress:
            update_progress(82, "Classifying orders into segments…")

        orders = data.get("orders", [])
        segments = classify_orders(orders, creators)

        for seg_key, seg_orders in segments.items():
            logger.info(f"[yt_influencers] {seg_key}: {len(seg_orders)} order(s)")

        # --- Aggregate & write each segment tab ---
        segment_keys = ["segment1", "segment2", "segment3"]
        for i, (seg_key, tab_name) in enumerate(zip(segment_keys, SEGMENT_TABS)):
            if update_progress:
                pct = 85 + i * 4
                update_progress(pct, f"Writing {tab_name}…")

            rows = aggregate_segment(segments[seg_key], base_date)
            ws = _get_or_create_worksheet(spreadsheet, tab_name)
            _write_rows_to_sheet(ws, rows, base_date)

        if update_progress:
            update_progress(98, "Google Sheets export complete")

        logger.info(f"[yt_influencers] Successfully exported to Google Sheets for {base_date}")
        return True

    except Exception as exc:
        logger.error(f"[yt_influencers] Google Sheets export failed: {exc}", exc_info=True)
        return False
