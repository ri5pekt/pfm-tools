import requests
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class UltaAPIClient:
    """Client for interacting with Ulta Marketplace API"""

    def __init__(self, api_key: str, base_url: str = "https://marketplace.ulta.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': api_key,
            'Content-Type': 'application/json'
        })

    def get_orders(
        self,
        start_date: str,
        end_date: str,
        max: int = 999,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Fetch orders from Ulta API.

        Args:
            start_date: Start date in ISO format (e.g., 2025-11-01T00:00:00Z)
            end_date: End date in ISO format (e.g., 2025-11-01T23:59:00Z)
            max: Maximum number of records to return (default: 999)
            offset: Offset for pagination (default: 0)

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}/api/orders"
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'max': max,
            'offset': offset
        }

        logger.info(f"Fetching Ulta orders from {start_date} to {end_date}")
        logger.info(f"Request URL: {url}")
        logger.info(f"Request params: {params}")

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            logger.info(f"Ulta API response received. Status: {response.status_code}")
            logger.info(f"Response data (first 1000 chars): {str(data)[:1000]}")

            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Ulta orders: {str(e)}")
            raise

    def close(self):
        """Close the session"""
        self.session.close()

