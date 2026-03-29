"""
Diagnostic: for orders Mar 1–10 2025 that contain a creator coupon,
print their utm_campaign value and coupon codes.
"""
import base64
import os
import pickle
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import Counter

import requests
import gspread
from google.auth.transport.requests import Request

# ── Config from env ───────────────────────────────────────────────────────────
WOO_BASE     = os.environ["WOO_BASE_URL"]
WOO_KEY      = os.environ["WOO_CONSUMER_KEY"]
WOO_SECRET   = os.environ["WOO_CONSUMER_SECRET"]
SHEET_ID     = os.environ["YT_INFLUENCERS_GOOGLE_SHEETS_SPREADSHEET_ID"]
TOKEN_PATH   = os.environ.get("GOOGLE_SHEETS_OAUTH_TOKEN_PATH", "credentials/google_sheets_token.pickle")
CREDS_PATH   = os.environ.get("GOOGLE_SHEETS_OAUTH_CREDENTIALS_PATH", "credentials/client_secret_google_sheets.json")
SA_PATH      = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH")

NY = ZoneInfo("America/New_York")

# ── Auth ──────────────────────────────────────────────────────────────────────
def get_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]
    creds = None
    if TOKEN_PATH and os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
    if not creds and SA_PATH and os.path.exists(SA_PATH):
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_file(SA_PATH, scopes=scope)
    return gspread.authorize(creds)

# ── Load creator coupons from sheet ──────────────────────────────────────────
client = get_client()
sheet  = client.open_by_key(SHEET_ID)
ws     = sheet.worksheet("Creators")
rows   = ws.get_all_values()
header = [h.strip() for h in rows[0]]
c_col  = header.index("Creator")
u_col  = header.index("UTM_Campaign")
cp_col = header.index("Coupon")

creators = []
for r in rows[1:]:
    if len(r) <= max(c_col, u_col, cp_col):
        continue
    creators.append({
        "name":   r[c_col].strip(),
        "utm":    r[u_col].strip().lower(),
        "coupon": r[cp_col].strip().lower(),
    })

coupon_set = {c["coupon"] for c in creators if c["coupon"]}
utm_set    = {c["utm"]    for c in creators if c["utm"]}

print(f"\n=== Creators tab: {len(creators)} rows ===")
print(f"Known coupons : {sorted(coupon_set)}")
print(f"Known UTMs    : {sorted(utm_set)}")

# ── Fetch orders Mar 1–10 2025 ───────────────────────────────────────────────
auth_b64 = base64.b64encode(f"{WOO_KEY}:{WOO_SECRET}".encode()).decode()
session  = requests.Session()
session.headers.update({
    "X-PFM-Authorization": f"Basic {auth_b64}",
    "User-Agent": "curl/7.68.0",
})

api_url   = f"{WOO_BASE.rstrip('/')}/wp-json/pfm-tools/v1/yt-influencers-orders"
start_ny  = datetime(2026, 3, 1,  0, 0, 0, tzinfo=NY)
end_ny    = datetime(2026, 3, 10, 0, 0, 0, tzinfo=NY) + timedelta(days=1)

print(f"\nFetching orders {start_ny} → {end_ny} …")

all_orders = []
page = 1
while True:
    resp = session.get(api_url, params={
        "date_after":  start_ny.strftime("%Y-%m-%d %H:%M:%S"),
        "date_before": end_ny.strftime("%Y-%m-%d %H:%M:%S"),
        "per_page": 300,
        "page": page,
    }, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    orders = data.get("orders", [])
    all_orders.extend(orders)
    total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
    print(f"  Page {page}/{total_pages}: {len(orders)} orders (total so far: {len(all_orders)})")
    if page >= total_pages or not orders:
        break
    page += 1

print(f"\nTotal orders: {len(all_orders)}")

# ── Find orders with creator coupons ─────────────────────────────────────────
matched = [
    o for o in all_orders
    if any(str(c).strip().lower() in coupon_set for c in (o.get("coupon_codes") or []))
]

print(f"Orders with creator coupons: {len(matched)}")

# ── Analyse their UTMs ───────────────────────────────────────────────────────
utm_counter = Counter()
for o in matched:
    utm = (o.get("utm_campaign") or "").strip()
    utm_counter[utm or "(empty)"] += 1

print("\n=== UTM values on orders with creator coupons ===")
for utm, count in utm_counter.most_common():
    match = "✓ matches creator" if utm.lower() in utm_set else ""
    print(f"  {count:4d}x  {utm!r}  {match}")

# ── Sample 5 matched orders ──────────────────────────────────────────────────
print("\n=== Sample matched orders (first 5) ===")
for o in matched[:5]:
    print(f"  id={o['id']}  date={o.get('date_created','')}  "
          f"utm={o.get('utm_campaign')!r}  coupons={o.get('coupon_codes')}")
