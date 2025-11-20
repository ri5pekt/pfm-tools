#!/usr/bin/env python3
"""Test PFM Tools custom API date filtering"""
import requests
import base64
import sys
from app.core.config import get_settings

settings = get_settings()

# Setup auth
auth = base64.b64encode(f'{settings.woo_consumer_key}:{settings.woo_consumer_secret}'.encode()).decode()
headers = {'Authorization': f'Basic {auth}'}

# Test date: 2025-10-01
url = 'https://www.particleformen.com/wp-json/pfm-tools/v1/orders'
params = {
    'date_after': '2025-10-01 00:00:00',
    'date_before': '2025-10-01 23:59:59',
    'per_page': 10,
    'page': 1
}

print(f"Testing PFM Tools custom API date filtering")
print(f"URL: {url}")
print(f"Params: {params}")
print()

r = requests.get(url, params=params, headers=headers, timeout=30)
print(f"Status: {r.status_code}")
print(f"Total orders in response header: {r.headers.get('X-WP-Total', 'N/A')}")
print(f"Total pages: {r.headers.get('X-WP-TotalPages', 'N/A')}")
print()

if r.status_code == 200:
    orders = r.json()
    print(f"Returned {len(orders)} orders in this page")
    print()
    print("First 10 orders:")
    for order in orders:
        order_id = order.get('id', 'N/A')
        date_created = order.get('date_created', 'N/A')
        status = order.get('status', 'N/A')
        has_refunds = order.get('has_refunds', False)
        total = order.get('total', 'N/A')
        print(f"  Order {order_id}: date={date_created}, status={status}, total={total}, has_refunds={has_refunds}")
else:
    print(f"Error: {r.status_code}")
    print(r.text[:500])

