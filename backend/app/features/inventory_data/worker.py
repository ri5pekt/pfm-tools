import os
import logging
from sqlalchemy.orm import Session
from datetime import datetime

from ...core.config import get_settings
from ...core.db import SessionLocal
from ...jobs.models import Job
from .service import (
    fetch_zenventory_klb_inventory,
    fetch_shipbob_inventory_by_locations,
    create_inventory_csv,
    create_location_inventory_csv,
    create_inventory_zip,
    export_inventory_to_google_sheets,
)

settings = get_settings()
logger = logging.getLogger(__name__)


def ensure_dirs():
    os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(settings.processed_dir, exist_ok=True)


def run_inventory_data_export_job(job_id: int):
    """
    Worker function to process Inventory Data export job.
    Fetches data from multiple warehouse APIs and creates a ZIP archive with CSV files.
    """
    ensure_dirs()
    db = SessionLocal()
    try:
        job: Job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.warning(f"Job {job_id} not found, skipping")
            return

        job.status = "running"
        db.commit()
        db.refresh(job)

        # Double-check job still exists
        if not db.query(Job).filter(Job.id == job_id).first():
            logger.warning(f"Job {job_id} was deleted, stopping")
            return

        # Get options from job
        options = job.options or {}
        is_manual = options.get("is_manual", True)
        export_date = options.get("export_date") or datetime.now().strftime("%Y-%m-%d")
        export_date_display = options.get("export_date_display") or export_date
        zenventory_username = options.get("zenventory_username")
        zenventory_password = options.get("zenventory_password")
        zenventory_base_url = options.get("zenventory_base_url")
        shipbob_api_key = options.get("shipbob_api_key")
        shipbob_base_url = options.get("shipbob_base_url")

        if not zenventory_username or not zenventory_password:
            job.status = "error"
            job.error_message = "Zenventory KLB credentials not provided"
            db.commit()
            return

        if not shipbob_api_key:
            job.status = "error"
            job.error_message = "Shipbob API key not provided"
            db.commit()
            return

        logger.info(f"Starting Inventory Data export job {job_id}")
        logger.info(f"Export date: {export_date}")
        logger.info(f"Manual run: {is_manual}")

        csv_files = []
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

        # ====== API 1: Zenventory KLB ======
        try:
            # Update progress
            new_options = dict(options)
            new_options['progress'] = 10
            new_options['status_message'] = 'Fetching inventory from Zenventory KLB...'
            job.options = new_options
            db.commit()
            db.refresh(job)

            logger.info("Fetching inventory from Zenventory KLB...")
            zenventory_inventory = fetch_zenventory_klb_inventory(
                username=zenventory_username,
                password=zenventory_password,
                base_url=zenventory_base_url
            )

            # Create CSV for Zenventory KLB
            csv_path = os.path.join(
                settings.processed_dir,
                f"inventory_zenventory_klb_{job.id}_{timestamp}.csv"
            )
            create_inventory_csv(
                inventory_data=zenventory_inventory,
                warehouse_name="Zenventory KLB",
                output_path=csv_path,
                export_date=export_date
            )
            csv_files.append({
                "path": csv_path,
                "name": "zenventory_klb.csv"
            })
            logger.info(f"Created CSV for Zenventory KLB: {len([q for q in zenventory_inventory.values() if q > 0])} products with inventory")

        except Exception as e:
            logger.error(f"Error processing Zenventory KLB: {str(e)}", exc_info=True)
            job.status = "error"
            job.error_message = f"Failed to fetch Zenventory KLB inventory: {str(e)}"
            db.commit()
            return

        # ====== API 2: Shipbob (Location-based) ======
        try:
            # Update progress
            new_options = dict(options)
            new_options['progress'] = 50
            new_options['status_message'] = 'Fetching inventory from Shipbob locations...'
            job.options = new_options
            db.commit()
            db.refresh(job)

            logger.info("Fetching inventory from Shipbob locations...")
            shipbob_inventory, locations = fetch_shipbob_inventory_by_locations(
                api_key=shipbob_api_key,
                base_url=shipbob_base_url
            )

            # Create CSV for each Shipbob location
            location_name_map = {
                "us_pa_ne_hub_1": "US (PA) Northeast Hub 1",
                "dayton_nj": "Dayton (NJ)",
                "us_ga_se_hub_1": "US (GA) Southeast Hub 1",
                "fresno_ca": "Fresno (CA)",
                "grapevine_tx": "Grapevine (TX)",
                "dropp_fairburn": "Dropp Logistics (Fairburn)",
                "fairburn_ga": "Fairburn (GA)",
            }

            for location_key, location_name in location_name_map.items():
                # Create CSV for this location
                csv_path = os.path.join(
                    settings.processed_dir,
                    f"inventory_shipbob_{location_key}_{job.id}_{timestamp}.csv"
                )
                create_location_inventory_csv(
                    location_inventory_data=shipbob_inventory,
                    location_key=location_key,
                    location_name=location_name,
                    output_path=csv_path,
                    export_date=export_date
                )

                # Add to CSV files list with a clean filename
                csv_filename = f"shipbob_{location_key}.csv"
                csv_files.append({
                    "path": csv_path,
                    "name": csv_filename
                })

                # Count products with inventory for this location
                products_with_inventory = len([
                    sku for sku, locs in shipbob_inventory.items()
                    if locs.get(location_key, 0) > 0
                ])
                logger.info(f"Created CSV for Shipbob {location_name}: {products_with_inventory} products with inventory")

            # Create aggregated Shipbob CSV (total across all locations)
            # Sum up quantities across all locations for each SKU
            aggregated_shipbob_inventory = {}
            for sku, locs in shipbob_inventory.items():
                total_qty = sum(locs.values())
                if total_qty > 0:
                    aggregated_shipbob_inventory[sku] = total_qty

            # Create CSV for total Shipbob inventory
            csv_path = os.path.join(
                settings.processed_dir,
                f"inventory_shipbob_total_{job.id}_{timestamp}.csv"
            )
            create_inventory_csv(
                inventory_data=aggregated_shipbob_inventory,
                warehouse_name="Shipbob (Total)",
                output_path=csv_path,
                export_date=export_date
            )
            csv_files.append({
                "path": csv_path,
                "name": "shipbob.csv"
            })
            logger.info(f"Created CSV for Shipbob (Total): {len([q for q in aggregated_shipbob_inventory.values() if q > 0])} products with inventory")

        except Exception as e:
            logger.error(f"Error processing Shipbob: {str(e)}", exc_info=True)
            job.status = "error"
            job.error_message = f"Failed to fetch Shipbob inventory: {str(e)}"
            db.commit()
            return

        # ====== API 3: (To be implemented) ======
        # Placeholder for third API
        # new_options['progress'] = 70
        # new_options['status_message'] = 'Fetching inventory from API 3...'
        # job.options = new_options
        # db.commit()
        # db.refresh(job)

        # ====== API 3: (To be implemented) ======
        # Placeholder for third API
        # new_options['progress'] = 70
        # new_options['status_message'] = 'Fetching inventory from API 3...'
        # job.options = new_options
        # db.commit()
        # db.refresh(job)

        # Update progress
        new_options = dict(options)
        new_options['progress'] = 80
        new_options['status_message'] = 'Creating ZIP archive...'
        job.options = new_options
        db.commit()
        db.refresh(job)

        # Create ZIP archive with all CSV files
        zip_path = os.path.join(
            settings.processed_dir,
            f"inventory_data_export_{job.id}_{timestamp}.zip"
        )

        try:
            create_inventory_zip(csv_files, zip_path)
            logger.info(f"Created ZIP archive: {zip_path}")

            # Clean up individual CSV files after creating ZIP
            for csv_file in csv_files:
                csv_path = csv_file.get("path")
                if csv_path and os.path.exists(csv_path):
                    try:
                        os.remove(csv_path)
                        logger.info(f"Cleaned up CSV file: {csv_path}")
                    except Exception as e:
                        logger.warning(f"Could not delete CSV file {csv_path}: {str(e)}")

        except Exception as e:
            logger.error(f"Error creating ZIP archive: {str(e)}", exc_info=True)
            job.status = "error"
            job.error_message = f"Failed to create ZIP archive: {str(e)}"
            db.commit()
            return

        # Export to Google Sheets if configured
        # Use inventory-specific spreadsheet ID if available, otherwise fall back to general one
        spreadsheet_id = settings.inventory_google_sheets_spreadsheet_id or settings.google_sheets_spreadsheet_id
        google_sheets_enabled = (
            spreadsheet_id and
            (
                (settings.google_sheets_oauth_credentials_path and settings.google_sheets_oauth_token_path) or
                settings.google_sheets_service_account_path
            )
        )

        if google_sheets_enabled:
            logger.info("Google Sheets export is ENABLED, proceeding with export...")
            # Update progress
            new_options = dict(options)
            new_options['progress'] = 90
            new_options['status_message'] = 'Exporting to Google Sheets...'
            job.options = new_options
            db.commit()
            db.refresh(job)

            try:
                import time

                # Export Zenventory KLB
                logger.info("Exporting Zenventory KLB to Google Sheets...")
                success = export_inventory_to_google_sheets(
                    inventory_data=zenventory_inventory,
                    spreadsheet_id=spreadsheet_id,
                    sheet_name="KLB",
                    export_date=export_date,
                    oauth_credentials_path=settings.google_sheets_oauth_credentials_path,
                    oauth_token_path=settings.google_sheets_oauth_token_path,
                    service_account_path=settings.google_sheets_service_account_path,
                )
                if not success:
                    logger.warning("Failed to export KLB to Google Sheets")
                time.sleep(2)  # Delay to avoid rate limiting

                # Export Shipbob Total
                logger.info("Exporting Shipbob Total to Google Sheets...")
                success = export_inventory_to_google_sheets(
                    inventory_data=aggregated_shipbob_inventory,
                    spreadsheet_id=spreadsheet_id,
                    sheet_name="ShipBob",
                    export_date=export_date,
                    oauth_credentials_path=settings.google_sheets_oauth_credentials_path,
                    oauth_token_path=settings.google_sheets_oauth_token_path,
                    service_account_path=settings.google_sheets_service_account_path,
                )
                if not success:
                    logger.warning("Failed to export ShipBob to Google Sheets")
                time.sleep(2)  # Delay to avoid rate limiting

                # Export each Shipbob location
                location_sheet_map = {
                    "us_pa_ne_hub_1": "US (PA) Northeast Hub 1",
                    "dayton_nj": "Dayton (NJ)",
                    "us_ga_se_hub_1": "US (GA) Southeast Hub 1",
                    "fresno_ca": "Fresno (CA)",
                    "grapevine_tx": "Grapevine (TX)",
                    "dropp_fairburn": "Dropp Logistics (Fairburn) Fulfillment Center",
                    "fairburn_ga": "Fairburn (GA)",
                }

                for location_key, sheet_name in location_sheet_map.items():
                    try:
                        # Create location-specific inventory data for ALL products
                        # Include all hardcoded products, even if they have 0 quantity
                        location_inventory = {}
                        # First, initialize all products with 0
                        from .service import HARDCODED_PRODUCTS
                        for product in HARDCODED_PRODUCTS:
                            sku = str(product["sku"]).strip()
                            location_inventory[sku] = 0

                        # Then update with actual inventory from shipbob_inventory
                        for sku, locs in shipbob_inventory.items():
                            sku_str = str(sku).strip()
                            location_inventory[sku_str] = locs.get(location_key, 0)

                        logger.info(f"Exporting Shipbob {sheet_name} to Google Sheets...")
                        success = export_inventory_to_google_sheets(
                            inventory_data=location_inventory,
                            spreadsheet_id=spreadsheet_id,
                            sheet_name=sheet_name,
                            export_date=export_date,
                            oauth_credentials_path=settings.google_sheets_oauth_credentials_path,
                            oauth_token_path=settings.google_sheets_oauth_token_path,
                            service_account_path=settings.google_sheets_service_account_path,
                        )
                        if success:
                            logger.info(f"Successfully exported {sheet_name} to Google Sheets")
                        else:
                            logger.warning(f"Failed to export {sheet_name} to Google Sheets (check logs for details)")
                        # Add delay between exports to avoid rate limiting
                        time.sleep(2)
                    except Exception as e:
                        logger.error(f"Error exporting {sheet_name} to Google Sheets: {str(e)}", exc_info=True)
                        # Continue with other locations even if one fails
                        # Add a delay to avoid rate limiting
                        time.sleep(2)

                logger.info("Successfully exported all inventory data to Google Sheets")
            except Exception as e:
                logger.error(f"Error exporting to Google Sheets: {str(e)}", exc_info=True)
                # Don't fail the job if Google Sheets export fails, just log it
        else:
            logger.info("Google Sheets export is DISABLED (missing configuration)")

        # Update progress to 100%
        new_options = dict(options)
        new_options['progress'] = 100
        new_options['status_message'] = 'Export completed'
        job.options = new_options

        job.status = "done"
        job.output_filename = zip_path
        db.commit()
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error processing Inventory Data export job {job_id}: {str(e)}")
        logger.error(error_trace)
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "error"
            job.error_message = f"{str(e)}\n\nTraceback:\n{error_trace}"
            db.commit()
    finally:
        db.close()

