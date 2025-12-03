"""
AfterPay API client for fetching payment data.
"""
import logging
import time
import requests
from typing import Optional, Dict, Any
from requests.auth import HTTPBasicAuth

from ...core.config import get_settings

settings = get_settings()

# Set up logger
logger = logging.getLogger(__name__)


class AfterPayClient:
    """Client for interacting with AfterPay API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Initialize AfterPay client.

        Args:
            base_url: AfterPay API base URL (e.g., https://api.us.afterpay.com)
            username: AfterPay API username
            password: AfterPay API password
        """
        # Use aftership credentials for AfterPay (they're the same service)
        self.base_url = base_url or settings.aftership_base_url
        self.username = username or settings.aftership_username
        self.password = password or settings.aftership_password

        if not self.base_url:
            raise ValueError("AfterPay base_url is required")
        if not self.username or not self.password:
            raise ValueError("AfterPay username and password are required")

        # Ensure base_url doesn't end with slash
        self.base_url = self.base_url.rstrip('/')

        # Log initialization
        logger.info(f"AfterPay client initialized:")
        logger.info(f"  Base URL: {self.base_url}")
        logger.info(f"  Username: {self.username[:10]}...{self.username[-4:] if len(self.username) > 14 else '***'}")

        # Session for connection pooling with Basic Auth
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(self.username, self.password)
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })

    def get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch payment data from AfterPay by payment ID.

        Args:
            payment_id: The AfterPay payment ID

        Returns:
            Payment data dictionary or None if not found/error
        """
        api_start = time.time()
        try:
            # Clean payment_id (remove any whitespace)
            original_payment_id = payment_id
            payment_id = str(payment_id).strip()
            if not payment_id:
                logger.warning(f"Empty payment ID provided (original: {repr(original_payment_id)})")
                return None

            # AfterPay API endpoint: /v2/payments/{payment_id}
            url = f"{self.base_url}/v2/payments/{payment_id}"

            response = self.session.get(url, timeout=10)

            if response.status_code == 404:
                logger.warning(f"AfterPay payment {payment_id} not found (404)")
                return None

            response.raise_for_status()

            payment_data = response.json()

            return payment_data

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching AfterPay payment {payment_id}:")
            logger.error(f"  Status Code: {e.response.status_code if hasattr(e, 'response') else 'N/A'}")
            logger.error(f"  Response Text: {e.response.text if hasattr(e, 'response') and e.response else 'N/A'}")
            logger.error(f"  Error: {str(e)}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching AfterPay payment {payment_id}:")
            logger.error(f"  Error Type: {type(e).__name__}")
            logger.error(f"  Error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching AfterPay payment {payment_id}:")
            logger.error(f"  Error Type: {type(e).__name__}")
            logger.error(f"  Error: {str(e)}", exc_info=True)
            return None

    def get_payment_data_from_dict(self, payment_data: Optional[Dict[str, Any]], payment_id: str = "") -> Dict[str, Any]:
        """
        Extract relevant payment data for CSV output.
        This is a helper method that processes already-fetched payment data.

        Args:
            payment_data: Payment data dictionary (from get_payment)
            payment_id: Payment ID for logging purposes

        Returns:
            Dictionary with relevant fields for CSV output
        """
        if not payment_data:
            return {
                'processor_total': None,
                'processor_tax': None,
            }

        # Extract originalAmount.amount for processor_total
        processor_total = None
        if 'originalAmount' in payment_data and payment_data['originalAmount']:
            amount_str = payment_data['originalAmount'].get('amount')
            if amount_str:
                try:
                    processor_total = str(amount_str)
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse originalAmount.amount: {amount_str}")

        # Extract orderDetails.taxAmount.amount for processor_tax
        processor_tax = None
        if 'orderDetails' in payment_data and payment_data['orderDetails']:
            tax_amount_obj = payment_data['orderDetails'].get('taxAmount')
            if tax_amount_obj:
                tax_amount_str = tax_amount_obj.get('amount')
                if tax_amount_str:
                    try:
                        processor_tax = str(tax_amount_str)
                    except (ValueError, TypeError):
                        logger.warning(f"Could not parse taxAmount.amount: {tax_amount_str}")

        result = {
            'processor_total': processor_total,
            'processor_tax': processor_tax,
        }

        return result

    def close(self):
        """Close the session."""
        if self.session:
            self.session.close()

