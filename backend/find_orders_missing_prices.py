#!/usr/bin/env python3
"""Find orders that are missing price metadata"""
import requests
from app.core.config import get_settings

s = get_settings()
headers = {
    'ORDERDESK-STORE-ID': s.orderdesk_store_id,
    'ORDERDESK-API-KEY': s.orderdesk_api_key
}

# Get orders from the date range that was exported
params = {
    'search_start_date': '2025-10-30 04:00:00',
    'search_end_date': '2025-11-07 04:59:59',
    'source_name': 'TikTok Shop US',
    'folder_name': 'Closed',
    'limit': 100,
    'order_by': 'date_added',
    'order': 'DESC'
}

print("=" * 60)
print("Finding orders missing price metadata")
print("=" * 60)
print()

orders_missing_prices = []

try:
    r = requests.get('https://app.orderdesk.me/api/v2/orders', headers=headers, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    orders = data.get('orders', [])

    print(f"Checking {len(orders)} orders...")
    print()

    for order in orders:
        order_id = order.get('id')
        tiktok_id = order.get('source_id')
        order_items = order.get('order_items', [])

        has_missing_price = False
        missing_items = []

        for item in order_items:
            item_id = item.get('id')
            metadata = item.get('metadata', {})
            if not isinstance(metadata, dict):
                metadata = {}

            sale_price = metadata.get('tiktokshopus_sale_price')
            original_price = metadata.get('tiktokshopus_original_price')
            item_price = item.get('price')

            # Check if metadata prices are missing
            if (sale_price is None or sale_price == '') and (original_price is None or original_price == ''):
                has_missing_price = True
                missing_items.append({
                    'item_id': item_id,
                    'item_price': item_price,
                    'has_item_price': item_price is not None and item_price != ''
                })

        if has_missing_price:
            orders_missing_prices.append({
                'order_desk_id': order_id,
                'tiktok_id': tiktok_id,
                'date_added': order.get('date_added'),
                'order_total': order.get('order_total'),
                'product_total': order.get('product_total'),
                'tax_total': order.get('tax_total'),
                'missing_items': missing_items
            })

    print(f"Found {len(orders_missing_prices)} orders with missing price metadata")
    print()
    print("=" * 60)
    print("Examples (first 10):")
    print("=" * 60)
    print()

    for idx, order_info in enumerate(orders_missing_prices[:10], 1):
        print(f"{idx}. Order Desk ID: {order_info['order_desk_id']}")
        print(f"   TikTok ID: {order_info['tiktok_id']}")
        print(f"   Date: {order_info['date_added']}")
        print(f"   Order total: ${order_info['order_total']}")
        print(f"   Product total: ${order_info['product_total']}")
        print(f"   Tax total: ${order_info['tax_total']}")
        print(f"   Items missing metadata prices: {len(order_info['missing_items'])}")
        for item in order_info['missing_items']:
            print(f"     - Item {item['item_id']}: item.price = {item['item_price']} (available: {item['has_item_price']})")
        print()
        print("-" * 60)
        print()

    if len(orders_missing_prices) > 10:
        print(f"... and {len(orders_missing_prices) - 10} more orders")
        print()

    # Show summary
    print("=" * 60)
    print("Summary:")
    print("=" * 60)
    print(f"Total orders checked: {len(orders)}")
    print(f"Orders missing metadata prices: {len(orders_missing_prices)}")

    # Count how many have item.price available
    orders_with_fallback = sum(1 for o in orders_missing_prices
                              if any(item['has_item_price'] for item in o['missing_items']))
    print(f"Orders with item.price fallback available: {orders_with_fallback}")
    print(f"Orders with no price data at all: {len(orders_missing_prices) - orders_with_fallback}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

