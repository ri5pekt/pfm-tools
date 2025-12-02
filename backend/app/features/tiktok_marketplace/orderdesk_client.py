import requests
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class OrderDeskAPIClient:
    """Client for interacting with Order Desk API (used for TikTok Marketplace orders)"""

    def __init__(self, store_id: str, api_key: str, base_url: str = "https://app.orderdesk.me/api/v2"):
        """
        Initialize Order Desk API client.

        Args:
            store_id: Order Desk Store ID
            api_key: Order Desk API Key
            base_url: Base URL for Order Desk API (default: https://app.orderdesk.me/api/v2)
        """
        self.store_id = store_id
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'ORDERDESK-STORE-ID': store_id,
            'ORDERDESK-API-KEY': api_key,
            'Content-Type': 'application/json'
        })

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection to Order Desk API.

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}/test"

        logger.info(f"Testing Order Desk API connection")
        logger.info(f"Request URL: {url}")

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()
            logger.info(f"Order Desk API test response received. Status: {response.status_code}")
            logger.info(f"Response data: {data}")

            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error testing Order Desk API connection: {str(e)}")
            raise

    def get_orders(
        self,
        search_start_date: Optional[str] = None,
        search_end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        folder_id: Optional[int] = None,
        folder_name: Optional[str] = None,
        source_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch orders from Order Desk API.

        Args:
            search_start_date: Start date filter in UTC (format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            search_end_date: End date filter in UTC (format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            limit: Maximum number of records to return (default: 100, max: 500)
            offset: Offset for pagination (default: 0)
            folder_id: Filter by folder ID (comma-separated for multiple)
            folder_name: Filter by folder name (exact match)
            source_name: Filter by source name (e.g., "TikTok")

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}/orders"

        params = {
            'limit': min(limit, 500),  # API max is 500
            'offset': offset
        }

        # Add optional filters - using correct parameter names from Order Desk API
        if search_start_date:
            params['search_start_date'] = search_start_date
        if search_end_date:
            params['search_end_date'] = search_end_date
        if folder_id:
            params['folder_id'] = folder_id
        if folder_name:
            params['folder_name'] = folder_name
        if source_name:
            params['source_name'] = source_name

        logger.info(f"Fetching Order Desk orders")
        logger.info(f"Request URL: {url}")
        logger.info(f"Request params: {params}")

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            logger.info(f"Order Desk API response received. Status: {response.status_code}")

            # Log rate limit headers if present
            if 'X-Tokens-Remaining' in response.headers:
                logger.info(f"Rate limit - Tokens remaining: {response.headers['X-Tokens-Remaining']}")

            # Log response structure (first 2000 chars)
            logger.info(f"Response data (first 2000 chars): {str(data)[:2000]}")

            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Order Desk orders: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            raise

    def get_order(self, order_id: str) -> Dict[str, Any]:
        """
        Get a single order by ID.

        Args:
            order_id: Order Desk order ID

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}/orders/{order_id}"

        logger.info(f"Fetching Order Desk order: {order_id}")
        logger.info(f"Request URL: {url}")

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()
            logger.info(f"Order Desk API response received. Status: {response.status_code}")

            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Order Desk order {order_id}: {str(e)}")
            raise

    def close(self):
        """Close the session"""
        self.session.close()

