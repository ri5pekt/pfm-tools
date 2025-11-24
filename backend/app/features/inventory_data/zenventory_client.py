import requests
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class ZenventoryClient:
    """
    Client for Zenventory KLB API.
    """

    def __init__(self, username: str, password: str, base_url: str = "https://app.zenventory.com/rest/inventory"):
        self.username = username
        self.password = password
        self.base_url = base_url

    def get_all_inventory(self) -> Dict[str, Any]:
        """
        Fetch all inventory items from Zenventory API with pagination.

        Returns:
            Dictionary with 'inventory' list and metadata
        """
        all_items = []
        page = 1

        logger.info(f"Fetching inventory from Zenventory API (starting at page {page})")

        while True:
            try:
                response = requests.get(
                    self.base_url,
                    auth=(self.username, self.password),
                    params={"page": page, "perPage": 200},
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()

                items = data.get("inventory", []) or []
                all_items.extend(items)

                meta = data.get("meta", {}) or {}
                total_pages = meta.get("totalPages", 1)

                logger.info(f"Fetched page {page}/{total_pages}: {len(items)} items (total so far: {len(all_items)})")

                if page >= total_pages:
                    break

                page += 1

            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching page {page} from Zenventory API: {str(e)}")
                raise Exception(f"Failed to fetch inventory from Zenventory API: {str(e)}")

        logger.info(f"Successfully fetched {len(all_items)} total items from Zenventory API")

        return {
            "inventory": all_items,
            "total_items": len(all_items)
        }

    def get_inventory_by_skus(self, skus: List[str]) -> Dict[str, int]:
        """
        Get inventory quantities for specific SKUs.

        Args:
            skus: List of SKU strings to look up

        Returns:
            Dictionary mapping SKU to quantity (only includes SKUs with non-zero quantity)
        """
        all_inventory = self.get_all_inventory()
        inventory_items = all_inventory.get("inventory", [])

        # Create a set for faster lookup
        sku_set = set(str(sku).strip() for sku in skus if sku)

        # Build result dictionary
        result = {}

        for inv in inventory_items:
            item = inv.get("item", {}) or {}
            sku = item.get("sku")

            if not sku:
                continue

            sku_str = str(sku).strip()

            # Only process SKUs we're looking for
            if sku_str not in sku_set:
                continue

            # Use 'sellable' as the quantity
            qty = inv.get("sellable", 0) or 0

            # Skip if quantity is zero, None, "", etc.
            if not qty or qty == 0:
                continue

            result[sku_str] = qty

        logger.info(f"Found inventory for {len(result)}/{len(skus)} requested SKUs")
        return result

