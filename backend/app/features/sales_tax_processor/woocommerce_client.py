"""
WooCommerce REST API client for fetching order data.
"""
import logging
import requests
from typing import Optional, Dict, Any
from urllib.parse import urljoin

from ...core.config import get_settings

settings = get_settings()

# Set up logger
logger = logging.getLogger(__name__)


class WooCommerceClient:
    """Client for interacting with WooCommerce REST API."""

    def __init__(self, base_url: Optional[str] = None, consumer_key: Optional[str] = None, consumer_secret: Optional[str] = None):
        """
        Initialize WooCommerce client.

        Args:
            base_url: WooCommerce store base URL (e.g., https://example.com)
            consumer_key: WooCommerce API consumer key
            consumer_secret: WooCommerce API consumer secret
        """
        self.base_url = base_url or settings.woo_base_url
        self.consumer_key = consumer_key or settings.woo_consumer_key
        self.consumer_secret = consumer_secret or settings.woo_consumer_secret

        if not self.base_url:
            raise ValueError("WooCommerce base_url is required")
        if not self.consumer_key or not self.consumer_secret:
            raise ValueError("WooCommerce consumer_key and consumer_secret are required")

        # Ensure base_url doesn't end with slash
        self.base_url = self.base_url.rstrip('/')
        self.api_base = f"{self.base_url}/wp-json/wc/v3"

        # Log initialization
        logger.info(f"WooCommerce client initialized:")
        logger.info(f"  Base URL: {self.base_url}")
        logger.info(f"  API Base: {self.api_base}")
        logger.info(f"  Consumer Key: {self.consumer_key[:10]}...{self.consumer_key[-4:] if len(self.consumer_key) > 14 else '***'}")
        logger.info(f"  Consumer Secret: {'*' * len(self.consumer_secret) if self.consumer_secret else 'None'}")

        # Session for connection pooling
        # WooCommerce REST API uses Basic Auth (consumer_key:consumer_secret)
        self.session = requests.Session()
        self.session.auth = (self.consumer_key, self.consumer_secret)
        # Use curl-like headers to match what works from command line
        self.session.headers.update({
            'Accept': '*/*',
            'User-Agent': 'curl/7.68.0',  # Match curl user agent
            'Accept-Encoding': 'gzip, deflate',
        })
        # Don't verify SSL if there are certificate issues (though this shouldn't be needed)
        # self.session.verify = False

        # Log the actual auth being used (for debugging)
        import base64
        auth_string = f"{self.consumer_key}:{self.consumer_secret}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        logger.debug(f"  Basic Auth Header: Basic {auth_b64[:20]}...")

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch order data from WooCommerce by order ID.

        Args:
            order_id: The WooCommerce order ID

        Returns:
            Order data dictionary or None if not found/error
        """
        try:
            # Clean order_id (remove any whitespace)
            original_order_id = order_id
            order_id = str(order_id).strip()
            if not order_id:
                logger.warning(f"Empty order ID provided (original: {repr(original_order_id)})")
                return None

            # WooCommerce REST API uses Basic Auth (consumer_key:consumer_secret)
            url = f"{self.api_base}/orders/{order_id}"

            response = self.session.get(url, timeout=10)

            if response.status_code == 404:
                logger.warning(f"Order {order_id} not found (404)")
                return None

            response.raise_for_status()

            order_data = response.json()

            return order_data
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching WooCommerce order {order_id}:")
            logger.error(f"  Status Code: {e.response.status_code if hasattr(e, 'response') else 'N/A'}")
            logger.error(f"  Response Text: {e.response.text if hasattr(e, 'response') and e.response else 'N/A'}")
            logger.error(f"  Error: {str(e)}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching WooCommerce order {order_id}:")
            logger.error(f"  Error Type: {type(e).__name__}")
            logger.error(f"  Error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching WooCommerce order {order_id}:")
            logger.error(f"  Error Type: {type(e).__name__}")
            logger.error(f"  Error: {str(e)}", exc_info=True)
            return None

    def get_order_totals(self, order_id: str) -> Dict[str, Optional[float]]:
        """
        Extract total+tax and tax from WooCommerce order.

        Args:
            order_id: The WooCommerce order ID

        Returns:
            Dictionary with 'total_with_tax' and 'tax' values (None if order not found)
        """
        logger.info(f"Getting order totals for order ID: {order_id}")
        order = self.get_order(order_id)
        if not order:
            logger.warning(f"No order data returned for order {order_id}, returning None values")
            return {
                'total_with_tax': None,
                'tax': None
            }

        # Extract total and tax from WooCommerce order structure
        # WooCommerce order structure:
        # - total: order total (string, includes tax)
        # - total_tax: tax amount (string)
        total_with_tax = None
        tax = None

        logger.info(f"Extracting totals from order data:")
        logger.info(f"  Available keys: {list(order.keys())}")
        logger.info(f"  'total' value: {order.get('total', 'KEY NOT FOUND')}")
        logger.info(f"  'total_tax' value: {order.get('total_tax', 'KEY NOT FOUND')}")

        try:
            # Convert string values to float
            if 'total' in order:
                total_raw = order['total']
                logger.info(f"  Processing 'total': {repr(total_raw)} (type: {type(total_raw).__name__})")
                if total_raw:
                    total_with_tax = float(total_raw)
                    logger.info(f"  Parsed total_with_tax: {total_with_tax}")
                else:
                    logger.warning(f"  'total' is empty/None")
            else:
                logger.warning(f"  'total' key not found in order data")

            if 'total_tax' in order:
                tax_raw = order['total_tax']
                logger.info(f"  Processing 'total_tax': {repr(tax_raw)} (type: {type(tax_raw).__name__})")
                if tax_raw:
                    tax = float(tax_raw)
                    logger.info(f"  Parsed tax: {tax}")
                else:
                    logger.warning(f"  'total_tax' is empty/None")
            else:
                logger.warning(f"  'total_tax' key not found in order data")
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing order totals for order {order_id}:")
            logger.error(f"  Error Type: {type(e).__name__}")
            logger.error(f"  Error: {str(e)}")
            logger.error(f"  Order data: {order}")

        result = {
            'total_with_tax': total_with_tax,
            'tax': tax
        }
        logger.info(f"Final totals for order {order_id}: {result}")
        return result

    def get_orders_batch(self, order_ids: list[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Fetch multiple orders in a single API call using the include parameter.

        Args:
            order_ids: List of order IDs to fetch

        Returns:
            Dictionary mapping order_id -> order_data (or None if not found)
        """
        if not order_ids:
            return {}

        # Clean and filter order IDs
        clean_order_ids = [str(oid).strip() for oid in order_ids if str(oid).strip()]
        if not clean_order_ids:
            return {}

        try:
            url = f"{self.api_base}/orders"
            # WooCommerce REST API supports batch loading using 'include' parameter
            # Can be passed as comma-separated string or list
            # Using comma-separated string for better compatibility
            params = {'include': ','.join(clean_order_ids)}

            response = self.session.get(url, params=params, timeout=30)  # Longer timeout for batch
            
            if response.status_code != 200:
                error_text = response.text[:500] if hasattr(response, 'text') else 'N/A'
                logger.error(f"Batch API failed with status {response.status_code}: {error_text}")

            if response.status_code == 404:
                logger.warning(f"Orders batch not found (404)")
                return {oid: None for oid in clean_order_ids}

            response.raise_for_status()

            orders_data = response.json()

            # Create a dictionary mapping order ID to order data
            # WooCommerce returns orders as a list, we need to index by ID
            result = {}
            for order in orders_data:
                order_id = str(order.get('id', ''))
                if order_id:
                    result[order_id] = order

            # Mark missing orders as None
            for order_id in clean_order_ids:
                if order_id not in result:
                    result[order_id] = None

            return result

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching WooCommerce orders batch:")
            logger.error(f"  Status Code: {e.response.status_code if hasattr(e, 'response') else 'N/A'}")
            logger.error(f"  Response Text: {e.response.text[:500] if hasattr(e, 'response') and e.response else 'N/A'}")
            logger.error(f"  Error: {str(e)}")
            return {oid: None for oid in clean_order_ids}
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching WooCommerce orders batch:")
            logger.error(f"  Error Type: {type(e).__name__}")
            logger.error(f"  Error: {str(e)}")
            return {oid: None for oid in clean_order_ids}
        except Exception as e:
            logger.error(f"Unexpected error fetching WooCommerce orders batch:")
            logger.error(f"  Error Type: {type(e).__name__}")
            logger.error(f"  Error: {str(e)}", exc_info=True)
            return {oid: None for oid in clean_order_ids}

    def get_order_totals_from_data(self, order_data: Optional[Dict[str, Any]], order_id: str = "") -> Dict[str, Optional[float]]:
        """
        Extract total+tax and tax from WooCommerce order data.
        This is a helper method that doesn't make an API call.

        Args:
            order_data: Order data dictionary (from batch fetch or single fetch)
            order_id: Order ID for logging purposes

        Returns:
            Dictionary with 'total_with_tax' and 'tax' values (None if order not found)
        """
        if not order_data:
            return {
                'total_with_tax': None,
                'tax': None
            }

        # Extract total and tax from WooCommerce order structure
        total_with_tax = None
        tax = None

        try:
            # Convert string values to float
            if 'total' in order_data:
                total_raw = order_data['total']
                if total_raw:
                    total_with_tax = float(total_raw)
            if 'total_tax' in order_data:
                tax_raw = order_data['total_tax']
                if tax_raw:
                    tax = float(tax_raw)
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing order totals for order {order_id}: {str(e)}")

        return {
            'total_with_tax': total_with_tax,
            'tax': tax
        }

    def get_payment_method_from_data(self, order_data: Optional[Dict[str, Any]], order_id: str = "") -> Optional[str]:
        """
        Extract payment method from WooCommerce order data.
        This is a helper method that doesn't make an API call.

        Args:
            order_data: Order data dictionary (from batch fetch or single fetch)
            order_id: Order ID for logging purposes

        Returns:
            Payment method (e.g., "braintree_cc") or None if not found
        """
        if not order_data:
            logger.debug(f"  No order data for payment method extraction (order {order_id})")
            return None

        # Use payment_method field as requested
        payment_method = order_data.get('payment_method')

        logger.debug(f"  Extracting payment method for order {order_id}:")
        logger.debug(f"    payment_method field: {payment_method}")
        logger.debug(f"    payment_method_title field: {order_data.get('payment_method_title')}")

        if payment_method:
            result = str(payment_method)
            logger.debug(f"    Returning payment method: {result}")
            return result

        logger.warning(f"  Payment method not found for order {order_id}")
        return None

    def get_transaction_id_from_data(self, order_data: Optional[Dict[str, Any]], order_id: str = "") -> Optional[str]:
        """
        Extract transaction ID from WooCommerce order data.
        This is used to fetch payment processor data (e.g., Braintree).

        Args:
            order_data: Order data dictionary (from batch fetch or single fetch)
            order_id: Order ID for logging purposes

        Returns:
            Transaction ID (e.g., "5mhyged9") or None if not found
        """
        if not order_data:
            logger.debug(f"  No order data for transaction ID extraction (order {order_id})")
            return None

        # Transaction ID is typically in the transaction_id field
        transaction_id = order_data.get('transaction_id')

        logger.debug(f"  Extracting transaction ID for order {order_id}:")
        logger.debug(f"    transaction_id field: {transaction_id}")

        if transaction_id:
            result = str(transaction_id).strip()
            if result:
                logger.debug(f"    Returning transaction ID: {result}")
                return result

        logger.warning(f"  Transaction ID not found for order {order_id}")
        return None

    def close(self):
        """Close the session."""
        if self.session:
            self.session.close()

