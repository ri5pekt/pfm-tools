import requests
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class ShipbobClient:
    """
    Client for Shipbob API.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.shipbob.com/2025-07"):
        self.api_key = api_key
        self.base_url = base_url

    def get_all_inventory(self) -> Dict[str, Any]:
        """
        Fetch all inventory items from Shipbob API with pagination.

        Returns:
            Dictionary with 'items' list and metadata
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        all_items = []
        path = "/inventory-level"
        next_path = path

        logger.info(f"Fetching inventory from Shipbob API (starting at {path})")

        while next_path:
            try:
                url = self.base_url + next_path
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()

                if "items" in data:
                    items = data.get("items", [])
                    all_items.extend(items)
                    logger.info(f"Fetched {len(items)} items (total so far: {len(all_items)})")

                # Get next page path
                next_path = data.get("next")

            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching from Shipbob API: {str(e)}")
                raise Exception(f"Failed to fetch inventory from Shipbob API: {str(e)}")

        logger.info(f"Successfully fetched {len(all_items)} total items from Shipbob API")

        return {
            "items": all_items,
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
        inventory_items = all_inventory.get("items", [])

        # Create a set for faster lookup
        sku_set = set(str(sku).strip() for sku in skus if sku)

        # Build result dictionary
        result = {}

        for item in inventory_items:
            sku = item.get("sku")

            if not sku:
                continue

            sku_str = str(sku).strip()

            # Only process SKUs we're looking for
            if sku_str not in sku_set:
                continue

            # Use 'total_on_hand_quantity' as the quantity
            qty = item.get("total_on_hand_quantity", 0) or 0

            # Skip if quantity is zero, None, "", etc.
            if not qty or qty == 0:
                continue

            result[sku_str] = qty

        logger.info(f"Found inventory for {len(result)}/{len(skus)} requested SKUs")
        return result

    def get_inventory_by_locations(self, locations: Dict[str, str] = None) -> Dict[str, Dict[str, int]]:
        """
        Get inventory quantities per SKU and location.

        Args:
            locations: Dictionary mapping location names to internal keys
                      Example: {"US (PA) Northeast Hub 1": "us_pa_ne_hub_1"}

        Returns:
            Dictionary mapping SKU to location quantities
            Example: {"SKU123": {"us_pa_ne_hub_1": 10, "dayton_nj": 5}}
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        # Default locations if not provided
        if locations is None:
            locations = {
                "US (PA) Northeast Hub 1": "us_pa_ne_hub_1",
                "Dayton (NJ)": "dayton_nj",
                "US (GA) Southeast Hub 1": "us_ga_se_hub_1",
                "Fresno (CA)": "fresno_ca",
                "Grapevine (TX)": "grapevine_tx",
                "Dropp Logistics (Fairburn) Fulfillment Center": "dropp_fairburn",
                "Fairburn (GA)": "fairburn_ga",
            }

        all_items = []
        path = "/inventory-level/locations"
        next_path = path

        logger.info(f"Fetching location-based inventory from Shipbob API (starting at {path})")

        # Load all pages
        while next_path:
            try:
                url = self.base_url + next_path
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()

                items = data.get("items", []) or []
                all_items.extend(items)

                # ShipBob returns a relative path here (e.g. "/inventory-levels/locations?cursor=...")
                next_path = data.get("next")

            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching from Shipbob API: {str(e)}")
                raise Exception(f"Failed to fetch inventory from Shipbob API: {str(e)}")

        logger.info(f"Successfully fetched {len(all_items)} total items from Shipbob API")

        # Aggregate per SKU + location (fulfillable quantity)
        result_map = {}

        def ensure_sku_entry(sku: str):
            if sku not in result_map:
                result_map[sku] = {key: 0 for key in locations.values()}

        for item in all_items:
            sku = item.get("sku")
            if not sku:
                continue

            # Convert SKU to string for consistency
            sku_str = str(sku).strip()

            item_locations = item.get("locations", []) or []
            if not item_locations:
                continue

            ensure_sku_entry(sku_str)

            for loc in item_locations:
                loc_name = loc.get("name")
                key = locations.get(loc_name)
                if not key:
                    # Location we don't track
                    continue

                qty = loc.get("fulfillable_quantity", 0) or 0
                try:
                    qty_int = int(qty)
                except Exception:
                    qty_int = 0

                # Sum quantities per SKU+location (in case ShipBob ever returns duplicates)
                result_map[sku][key] += qty_int

        logger.info(f"Aggregated inventory for {len(result_map)} SKUs across {len(locations)} locations")
        return result_map

