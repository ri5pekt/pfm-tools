# TikTok Marketplace uses Order Desk API to fetch orders
# This file is kept for backward compatibility but the actual client is in orderdesk_client.py
from .orderdesk_client import OrderDeskAPIClient

# Alias for backward compatibility
TikTokAPIClient = OrderDeskAPIClient

