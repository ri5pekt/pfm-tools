"""
Braintree SDK client for fetching transaction data.
"""
import logging
import braintree
from typing import Optional, Dict, Any

from ...core.config import get_settings

settings = get_settings()

# Set up logger
logger = logging.getLogger(__name__)


class BraintreeClient:
    """Client for interacting with Braintree API using the official SDK."""

    def __init__(
        self,
        merchant_id: Optional[str] = None,
        public_key: Optional[str] = None,
        private_key: Optional[str] = None,
        environment: Optional[str] = None
    ):
        """
        Initialize Braintree client.

        Args:
            merchant_id: Braintree merchant ID
            public_key: Braintree public key
            private_key: Braintree private key
            environment: "production" or "sandbox"
        """
        self.merchant_id = merchant_id or settings.braintree_merchant_id
        self.public_key = public_key or settings.braintree_public_key
        self.private_key = private_key or settings.braintree_private_key
        self.environment = (environment or settings.braintree_environment).lower()

        if not self.merchant_id:
            raise ValueError("Braintree merchant_id is required")
        if not self.public_key:
            raise ValueError("Braintree public_key is required")
        if not self.private_key:
            raise ValueError("Braintree private_key is required")

        # Map environment string to Braintree Environment enum
        if self.environment == "production":
            braintree_env = braintree.Environment.Production
        elif self.environment == "sandbox":
            braintree_env = braintree.Environment.Sandbox
        else:
            raise ValueError(f"Invalid Braintree environment: {self.environment}. Must be 'production' or 'sandbox'")

        # Configure Braintree gateway
        self.gateway = braintree.BraintreeGateway(
            braintree.Configuration(
                braintree_env,
                merchant_id=self.merchant_id,
                public_key=self.public_key,
                private_key=self.private_key
            )
        )

        # Log initialization
        logger.info(f"Braintree client initialized:")
        logger.info(f"  Environment: {self.environment}")
        logger.info(f"  Merchant ID: {self.merchant_id[:10]}...{self.merchant_id[-4:] if len(self.merchant_id) > 14 else '***'}")
        logger.info(f"  Public Key: {self.public_key[:10]}...{self.public_key[-4:] if len(self.public_key) > 14 else '***'}")

    def get_transaction(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch transaction data from Braintree by transaction ID.

        Args:
            transaction_id: The Braintree transaction ID

        Returns:
            Transaction data dictionary or None if not found/error
        """
        try:
            # Clean transaction_id (remove any whitespace)
            original_transaction_id = transaction_id
            transaction_id = str(transaction_id).strip()
            if not transaction_id:
                logger.warning(f"Empty transaction ID provided (original: {repr(original_transaction_id)})")
                return None

            logger.info(f"Fetching Braintree transaction:")
            logger.info(f"  Transaction ID: {transaction_id} (original: {repr(original_transaction_id)})")

            # Use SDK to find transaction
            transaction = self.gateway.transaction.find(transaction_id)

            if transaction is None:
                logger.warning(f"Transaction {transaction_id} not found")
                return None

            # Convert transaction object to dictionary
            transaction_dict = self._transaction_to_dict(transaction)

            logger.info(f"Transaction data retrieved successfully:")
            logger.info(f"  Transaction ID: {transaction_dict.get('id', 'N/A')}")
            logger.info(f"  Status: {transaction_dict.get('status', 'N/A')}")
            logger.info(f"  Amount: {transaction_dict.get('amount', 'N/A')}")
            logger.info(f"  Tax Amount: {transaction_dict.get('tax_amount', 'N/A')}")
            logger.debug(f"  Full transaction: {transaction_dict}")

            return transaction_dict

        except braintree.exceptions.NotFoundError:
            logger.warning(f"Transaction {transaction_id} not found (NotFoundError)")
            return None
        except braintree.exceptions.AuthenticationError as e:
            logger.error(f"Braintree authentication error for transaction {transaction_id}: {str(e)}")
            return None
        except braintree.exceptions.AuthorizationError as e:
            logger.error(f"Braintree authorization error for transaction {transaction_id}: {str(e)}")
            return None
        except braintree.exceptions.ServerError as e:
            logger.error(f"Braintree server error for transaction {transaction_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching Braintree transaction {transaction_id}:")
            logger.error(f"  Error Type: {type(e).__name__}")
            logger.error(f"  Error: {str(e)}", exc_info=True)
            return None

    def _transaction_to_dict(self, transaction) -> Dict[str, Any]:
        """
        Convert Braintree transaction object to dictionary.

        Args:
            transaction: Braintree transaction object

        Returns:
            Dictionary representation of transaction
        """
        result = {}

        # Basic transaction fields
        if hasattr(transaction, 'id'):
            result['id'] = transaction.id
        if hasattr(transaction, 'status'):
            result['status'] = transaction.status
        if hasattr(transaction, 'type'):
            result['type'] = transaction.type
        if hasattr(transaction, 'amount'):
            result['amount'] = str(transaction.amount) if transaction.amount is not None else None
        if hasattr(transaction, 'tax_amount'):
            result['tax_amount'] = str(transaction.tax_amount) if transaction.tax_amount is not None else None
        if hasattr(transaction, 'tax_exempt'):
            result['tax_exempt'] = transaction.tax_exempt
        if hasattr(transaction, 'currency_iso_code'):
            result['currency_iso_code'] = transaction.currency_iso_code
        if hasattr(transaction, 'created_at'):
            result['created_at'] = transaction.created_at.isoformat() if transaction.created_at else None
        if hasattr(transaction, 'updated_at'):
            result['updated_at'] = transaction.updated_at.isoformat() if transaction.updated_at else None

        # Payment method details
        if hasattr(transaction, 'payment_instrument_type'):
            result['payment_instrument_type'] = transaction.payment_instrument_type

        # Credit card details
        if hasattr(transaction, 'credit_card_details'):
            cc = transaction.credit_card_details
            if cc:
                result['credit_card'] = {
                    'bin': cc.bin if hasattr(cc, 'bin') else None,
                    'last_4': cc.last_4 if hasattr(cc, 'last_4') else None,
                    'card_type': cc.card_type if hasattr(cc, 'card_type') else None,
                    'expiration_month': cc.expiration_month if hasattr(cc, 'expiration_month') else None,
                    'expiration_year': cc.expiration_year if hasattr(cc, 'expiration_year') else None,
                    'cardholder_name': cc.cardholder_name if hasattr(cc, 'cardholder_name') else None,
                }

        # Customer details
        if hasattr(transaction, 'customer_details'):
            customer = transaction.customer_details
            if customer:
                result['customer'] = {
                    'id': customer.id if hasattr(customer, 'id') else None,
                    'email': customer.email if hasattr(customer, 'email') else None,
                    'first_name': customer.first_name if hasattr(customer, 'first_name') else None,
                    'last_name': customer.last_name if hasattr(customer, 'last_name') else None,
                }

        # Billing address
        if hasattr(transaction, 'billing_details'):
            billing = transaction.billing_details
            if billing:
                result['billing'] = {
                    'street_address': billing.street_address if hasattr(billing, 'street_address') else None,
                    'extended_address': billing.extended_address if hasattr(billing, 'extended_address') else None,
                    'locality': billing.locality if hasattr(billing, 'locality') else None,
                    'region': billing.region if hasattr(billing, 'region') else None,
                    'postal_code': billing.postal_code if hasattr(billing, 'postal_code') else None,
                    'country_code_alpha2': billing.country_code_alpha2 if hasattr(billing, 'country_code_alpha2') else None,
                }

        # Shipping address
        if hasattr(transaction, 'shipping_details'):
            shipping = transaction.shipping_details
            if shipping:
                result['shipping'] = {
                    'street_address': shipping.street_address if hasattr(shipping, 'street_address') else None,
                    'extended_address': shipping.extended_address if hasattr(shipping, 'extended_address') else None,
                    'locality': shipping.locality if hasattr(shipping, 'locality') else None,
                    'region': shipping.region if hasattr(shipping, 'region') else None,
                    'postal_code': shipping.postal_code if hasattr(shipping, 'postal_code') else None,
                    'country_code_alpha2': shipping.country_code_alpha2 if hasattr(shipping, 'country_code_alpha2') else None,
                }

        # Additional useful fields
        if hasattr(transaction, 'processor_response_code'):
            result['processor_response_code'] = transaction.processor_response_code
        if hasattr(transaction, 'processor_response_text'):
            result['processor_response_text'] = transaction.processor_response_text
        if hasattr(transaction, 'merchant_account_id'):
            result['merchant_account_id'] = transaction.merchant_account_id

        return result

    def get_transaction_data_from_dict(self, transaction_data: Optional[Dict[str, Any]], transaction_id: str = "") -> Dict[str, Any]:
        """
        Extract relevant transaction data for CSV output.
        This is a helper method that processes already-fetched transaction data.

        Args:
            transaction_data: Transaction data dictionary (from get_transaction)
            transaction_id: Transaction ID for logging purposes

        Returns:
            Dictionary with relevant fields for CSV output
        """
        if not transaction_data:
            return {
                'braintree_amount': None,
                'braintree_tax_amount': None,
                'braintree_status': None,
                'braintree_currency': None,
            }

        result = {
            'braintree_amount': transaction_data.get('amount'),
            'braintree_tax_amount': transaction_data.get('tax_amount'),
            'braintree_status': transaction_data.get('status'),
            'braintree_currency': transaction_data.get('currency_iso_code'),
        }

        return result

