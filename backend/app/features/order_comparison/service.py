import csv
import logging
import time
from datetime import datetime
from typing import Dict, List, Set, Optional, Any
from collections import defaultdict
from sqlalchemy.orm import Session
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from ...core.config import get_settings
from ...features.sales_tax_processor.woocommerce_client import WooCommerceClient
from ...jobs.models import Job

settings = get_settings()
logger = logging.getLogger(__name__)


def parse_complyt_csv(file_path: str, order_id_header: str, date_from: str = None, date_to: str = None) -> Dict[str, Any]:
    """
    Parse Complyt CSV file and extract orders and refunds by transactionType.

    NOTE: Date filtering is disabled - all rows in the CSV are included regardless of date.

    Args:
        file_path: Path to the Complyt CSV file
        order_id_header: Column name for order ID (e.g., 'externalId')
        date_from: Ignored - kept for API compatibility
        date_to: Ignored - kept for API compatibility

    Returns:
        Dictionary with:
        - 'invoices': list of order IDs (transactionType == 'INVOICE')
        - 'taxable_refunds': list of refund IDs (transactionType == 'TAXABLE_REFUND')
        - 'refunds': list of refund IDs (transactionType == 'REFUND')
        - 'invoice_amounts': dict mapping order_id -> amount
        - 'taxable_refund_amounts': dict mapping refund_id -> amount
        - 'refund_amounts': dict mapping refund_id -> amount
    """
    result = {
        'invoices': [],
        'taxable_refunds': [],
        'refunds': [],
        'invoice_amounts': {},
        'taxable_refund_amounts': {},
        'refund_amounts': {},
    }

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            total_rows = 0

            logger.info(f"Parsing Complyt CSV file (date filtering disabled - all rows included)")

            for row in reader:
                total_rows += 1
                order_id = str(row.get(order_id_header, '')).strip()
                if not order_id:
                    continue

                transaction_type = row.get('transactionType', '').strip()
                total_items_amount = row.get('totalItemsAmount', '0')

                try:
                    amount = float(total_items_amount) if total_items_amount else 0.0
                except (ValueError, TypeError):
                    amount = 0.0

                if transaction_type == 'INVOICE':
                    result['invoices'].append(order_id)
                    result['invoice_amounts'][order_id] = amount
                elif transaction_type == 'TAXABLE_REFUND':
                    result['taxable_refunds'].append(order_id)
                    result['taxable_refund_amounts'][order_id] = abs(amount)  # Make positive for reporting
                elif transaction_type == 'REFUND':
                    result['refunds'].append(order_id)
                    result['refund_amounts'][order_id] = abs(amount)  # Make positive for reporting

            logger.info(f"Parsed Complyt CSV: {total_rows} total rows processed (all rows included)")
            logger.info(f"  - Invoices: {len(result['invoices'])}")
            logger.info(f"  - Taxable refunds: {len(result['taxable_refunds'])}")
            logger.info(f"  - Refunds: {len(result['refunds'])}")

    except Exception as e:
        logger.error(f"Error parsing Complyt CSV: {str(e)}", exc_info=True)
        raise

    return result


def fetch_woocommerce_orders(date_from: str, date_to: str, woo_client: WooCommerceClient, job_id: int = None, db: Session = None) -> Dict[str, Any]:
    """
    Fetch WooCommerce orders and refunds for the given date range.

    Returns:
        Dictionary with:
        - 'orders': dict mapping order_id -> order_data
        - 'refunds': dict mapping refund_id -> refund_data
        - 'order_amounts': dict mapping order_id -> amount
        - 'refund_amounts': dict mapping refund_id -> amount
    """
    result = {
        'orders': {},
        'refunds': {},
        'order_amounts': {},
        'refund_amounts': {},
    }

    try:
        # Fetch orders from custom PFM Tools endpoint
        # Custom endpoint uses date_after/date_before parameters with SPACE format
        # Format: YYYY-MM-DD HH:MM:SS (e.g., 2025-10-01 00:00:00)
        # Dates are interpreted in WordPress site timezone (e.g., Asia/Jerusalem)
        api_base = f"{woo_client.base_url}/wp-json/pfm-tools/v1"

        # Format dates with SPACE (not T) - this is critical for date filtering to work
        # IMPORTANT: The PHP plugin interprets these dates in WordPress site timezone (Asia/Jerusalem)
        # We send dates EXACTLY as provided by the user (no timezone conversion)
        after_date = f"{date_from} 00:00:00"
        before_date = f"{date_to} 23:59:59"

        logger.info(f"Fetching WooCommerce orders from {after_date} to {before_date}")

        # Verify API keys are set
        if not woo_client.consumer_key or not woo_client.consumer_secret:
            raise ValueError("WooCommerce consumer_key and consumer_secret must be set in environment variables")

        # Fetch orders from custom endpoint
        orders_url = f"{api_base}/orders"
        params = {
            'date_after': after_date,
            'date_before': before_date,
            'per_page': 100,  # Maximum per page
            'page': 1,
        }

        # Create a separate session for custom endpoint with explicit Authorization header
        # The custom endpoint uses hardcoded credentials check, so we need to send Basic Auth
        import base64
        import requests
        auth_string = f"{woo_client.consumer_key}:{woo_client.consumer_secret}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')

        # Create a new session for custom endpoint (without session.auth to avoid conflicts)
        custom_session = requests.Session()
        custom_session.headers.update({
            'Accept': '*/*',
            'User-Agent': 'curl/7.68.0',
            'Accept-Encoding': 'gzip, deflate',
            'Authorization': f'Basic {auth_b64}'
        })
        logger.info(f"Created custom session for PFM Tools endpoint with explicit Authorization header")
        logger.debug(f"Authorization header (first 30 chars): Basic {auth_b64[:30]}...")

        all_orders = []
        all_order_ids = []
        page_num = 1
        total_pages = None
        fetch_start_time = time.time()

        logger.info(f"Starting to fetch orders from URL: {orders_url}")
        logger.info(f"Request parameters: {params}")

        # Helper function to update progress if job_id and db are provided
        def update_progress(progress, message):
            if job_id and db:
                try:
                    job = db.query(Job).filter(Job.id == job_id).first()
                    if job:
                        new_options = dict(job.options) if job.options else {}
                        new_options['progress'] = progress
                        new_options['status_message'] = message
                        job.options = new_options
                        db.commit()
                        logger.debug(f"Progress updated: {progress}% - {message}")
                except Exception as e:
                    logger.warning(f"Failed to update progress: {str(e)}")

        while True:
            logger.info(f"=== Fetching page {page_num} ===")

            try:
                request_start_time = time.time()
                full_url = f"{orders_url}?date_after={params['date_after']}&date_before={params['date_before']}&per_page={params['per_page']}&page={params['page']}"

                # Use custom session for PFM Tools endpoint
                response = custom_session.get(orders_url, params=params, timeout=30)

                request_end_time = time.time()
                request_duration = request_end_time - request_start_time

                # Extract total pages from response headers
                if 'X-WP-TotalPages' in response.headers:
                    total_pages = int(response.headers['X-WP-TotalPages'])
                    logger.debug(f"Total pages available: {total_pages}")

                if response.status_code != 200:
                    logger.error(f"=== AUTHENTICATION ERROR ===")
                    logger.error(f"Status code: {response.status_code}")
                    logger.error(f"Request URL: {response.request.url}")
                    logger.error(f"Request method: {response.request.method}")

                    # Log request headers (mask auth)
                    req_headers = dict(response.request.headers)
                    if 'Authorization' in req_headers:
                        auth_val = req_headers['Authorization']
                        if auth_val.startswith('Basic '):
                            # Show first 30 chars to verify it's being sent
                            logger.error(f"Authorization header present: {auth_val[:30]}...")
                            req_headers['Authorization'] = f"Basic {auth_val[6:30]}..."  # Mask
                    else:
                        logger.error("WARNING: Authorization header NOT found in request!")
                    logger.error(f"All request headers: {req_headers}")

                    # Log full response for debugging
                    logger.error(f"Response headers: {dict(response.headers)}")
                    logger.error(f"Response text (first 1000 chars): {response.text[:1000]}")
                    logger.error(f"=== END AUTHENTICATION ERROR ===")
                    response.raise_for_status()

                orders = response.json()

                # Update progress during pagination (30-50% range)
                if total_pages and job_id and db:
                    pagination_progress = 30 + int((page_num / total_pages) * 20)  # 30-50%
                    update_progress(pagination_progress, f'Fetching WooCommerce orders... Page {page_num}/{total_pages} ({len(all_orders)} orders)')

                if not orders:
                    logger.info(f"No orders returned for page {page_num}, stopping pagination")
                    break

                all_orders.extend(orders)
                logger.info(f"Total orders collected so far: {len(all_orders)}")

                # Collect order IDs for logging
                page_order_ids = [str(order.get('id', '')) for order in orders if order.get('id')]
                all_order_ids.extend(page_order_ids)
                logger.debug(f"Page {page_num}: Fetched {len(orders)} orders")

                # Check if there are more pages
                if len(orders) < params['per_page']:
                    logger.info(f"Received {len(orders)} orders (less than per_page {params['per_page']}), this is the last page")
                    break

                page_num += 1
                params['page'] = page_num
                logger.debug(f"More pages available, continuing to page {page_num}")

            except Exception as e:
                logger.error(f"Error fetching page {page_num}: {str(e)}", exc_info=True)
                raise

        fetch_end_time = time.time()
        total_fetch_duration = fetch_end_time - fetch_start_time
        logger.info(f"Fetched {len(all_orders)} orders in {total_fetch_duration:.3f} seconds ({page_num} pages)")
        processing_start_time = time.time()

        # Update progress to processing phase (50%)
        update_progress(50, f'Processing {len(all_orders)} orders...')

        # Process orders and fetch refunds separately
        # Note: We only fetch refunds for orders that were loaded, matching the CSV structure
        # where refunds are only included if their parent order is in the CSV
        processed_count = 0
        refund_fetch_count = 0
        total_orders = len(all_orders)
        total_refund_request_time = 0.0

        for order in all_orders:
            processed_count += 1
            if processed_count % 100 == 0:
                logger.info(f"Processing order {processed_count}/{total_orders}...")
                # Update progress during processing (50-70% range)
                if job_id and db:
                    processing_progress = 50 + int((processed_count / total_orders) * 20)  # 50-70%
                    update_progress(processing_progress, f'Processing orders... {processed_count}/{total_orders} (refunds: {refund_fetch_count})')

            order_id = str(order.get('id', ''))
            if not order_id:
                logger.warning(f"Skipping order with no ID: {order}")
                continue

            status = order.get('status', '')
            total = float(order.get('total', '0') or '0')

            logger.debug(f"Processing order {order_id}: status={status}, total={total}")

            # Include ALL orders in the comparison, including refunded ones
            # Refunded orders are still orders that exist in WooCommerce and should be compared
            # Previously we were filtering them out, which caused them to appear in
            # "Orders in Complyt but not in WooCommerce" even though they exist in WooCommerce
            result['orders'][order_id] = order
            result['order_amounts'][order_id] = total
            logger.debug(f"Added order {order_id} to orders list (status: {status})")

            # Check if order has refunds using the has_refunds flag from custom endpoint
            # The custom endpoint provides a has_refunds boolean flag
            # We only fetch refunds for loaded orders (matching CSV structure)
            has_refunds = order.get('has_refunds', False)

            if has_refunds:
                refund_fetch_count += 1
                # Fetch refunds from dedicated endpoint to get proper refund IDs
                refunds_url = f"{api_base}/orders/{order_id}/refunds"
                refund_request_start = time.time()
                try:
                    # Use custom session for refunds endpoint
                    refunds_response = custom_session.get(refunds_url, timeout=10)
                    refund_request_end = time.time()
                    refund_duration = refund_request_end - refund_request_start
                    total_refund_request_time += refund_duration
                    refunds_response.raise_for_status()
                    refunds_data = refunds_response.json()
                    logger.debug(f"Found {len(refunds_data)} refunds for order {order_id}")

                    for refund in refunds_data:
                        refund_id = str(refund.get('id', ''))
                        if refund_id:
                            # Custom endpoint uses 'amount' field instead of 'total'
                            refund_amount = float(refund.get('amount', '0') or '0')
                            # Ensure order_id is stored in refund data for later reference
                            refund['order_id'] = order_id
                            result['refunds'][refund_id] = refund
                            result['refund_amounts'][refund_id] = abs(refund_amount)
                            logger.debug(f"Added refund {refund_id} for order {order_id}, amount: {abs(refund_amount)}")
                except Exception as e:
                    logger.warning(f"Failed to fetch refunds for order {order_id}: {str(e)}", exc_info=True)

        processing_end_time = time.time()
        total_processing_duration = processing_end_time - processing_start_time
        logger.info(f"[TIMING SUMMARY] Total processing time: {total_processing_duration:.3f} seconds")
        logger.info(f"[TIMING SUMMARY] Time spent on refund requests: {total_refund_request_time:.3f} seconds ({refund_fetch_count} requests)")
        logger.info(f"[TIMING SUMMARY] Average time per refund request: {total_refund_request_time / refund_fetch_count:.3f} seconds" if refund_fetch_count > 0 else "[TIMING SUMMARY] No refund requests made")
        logger.info(f"Processed {processed_count} orders, fetched refunds for {refund_fetch_count} orders")

        logger.info(f"Processed {len(result['orders'])} orders and {len(result['refunds'])} refunds")

    except Exception as e:
        logger.error(f"Error fetching WooCommerce orders: {str(e)}", exc_info=True)
        raise

    return result


def generate_comparison_report(
    complyt_data: Dict[str, Any],
    woo_data: Dict[str, Any]
) -> str:
    """
    Generate a text report comparing Complyt and WooCommerce data.
    """
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("ORDER COMPARISON REPORT")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Counts
    complyt_order_count = len(complyt_data['invoices'])
    complyt_taxable_refund_count = len(complyt_data['taxable_refunds'])
    complyt_refund_count = len(complyt_data['refunds'])
    complyt_total_refund_count = complyt_taxable_refund_count + complyt_refund_count

    woo_order_count = len(woo_data['orders'])
    woo_refund_count = len(woo_data['refunds'])

    report_lines.append("COUNTS:")
    report_lines.append(f"Complyt orders: {complyt_order_count}")
    report_lines.append(f"Complyt TAXABLE REFUNDs: {complyt_taxable_refund_count}")
    report_lines.append(f"Complyt REFUNDs: {complyt_refund_count}")
    report_lines.append(f"Complyt total refunds: {complyt_total_refund_count}")
    report_lines.append(f"WooCommerce orders: {woo_order_count}")
    report_lines.append(f"WooCommerce refunds: {woo_refund_count}")
    report_lines.append("")

    # Find differences
    complyt_order_ids = set(complyt_data['invoices'])
    woo_order_ids = set(woo_data['orders'].keys())

    complyt_refund_ids = set(complyt_data['taxable_refunds'] + complyt_data['refunds'])
    woo_refund_ids = set(woo_data['refunds'].keys())

    # Check if any refund IDs are incorrectly in the orders dictionary and remove them
    refund_ids_in_orders = woo_order_ids & woo_refund_ids
    if refund_ids_in_orders:
        woo_order_ids = woo_order_ids - refund_ids_in_orders

    # Orders in Complyt but not in WooCommerce
    orders_in_complyt_not_woo = sorted(complyt_order_ids - woo_order_ids, key=lambda x: int(x) if x.isdigit() else 0)

    # Orders in WooCommerce but not in Complyt
    orders_in_woo_not_complyt = sorted(woo_order_ids - complyt_order_ids, key=lambda x: int(x) if x.isdigit() else 0)

    # Refunds in Complyt but not in WooCommerce
    refunds_in_complyt_not_woo = sorted(complyt_refund_ids - woo_refund_ids, key=lambda x: int(x) if x.isdigit() else 0)

    # Refunds in WooCommerce but not in Complyt
    refunds_in_woo_not_complyt = sorted(woo_refund_ids - complyt_refund_ids, key=lambda x: int(x) if x.isdigit() else 0)

    report_lines.append("DIFFERENCES:")
    report_lines.append("")

    report_lines.append("orders ids that are in complyt but not in woo:")
    if orders_in_complyt_not_woo:
        report_lines.append(f"  {', '.join(orders_in_complyt_not_woo)}")
    else:
        report_lines.append("  None")
    report_lines.append("")

    report_lines.append("orders ids that are in woo but not in complyt:")
    if orders_in_woo_not_complyt:
        report_lines.append(f"  {', '.join(orders_in_woo_not_complyt)}")
    else:
        report_lines.append("  None")
    report_lines.append("")

    report_lines.append("REFUNDs ids that are in complyt but not in woo:")
    if refunds_in_complyt_not_woo:
        report_lines.append(f"  {', '.join(refunds_in_complyt_not_woo)}")
    else:
        report_lines.append("  None")
    report_lines.append("")

    report_lines.append("REFUNDs ids that are in woo but not in complyt:")
    if refunds_in_woo_not_complyt:
        report_lines.append(f"  {', '.join(refunds_in_woo_not_complyt)}")
    else:
        report_lines.append("  None")
    report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("=" * 80)

    return "\n".join(report_lines)


def generate_comparison_report_pdf(
    complyt_data: Dict[str, Any],
    woo_data: Dict[str, Any],
    output_path: str,
    date_from: str = None,
    date_to: str = None
) -> str:
    """
    Generate a PDF report comparing Complyt and WooCommerce data.

    Returns:
        Path to the generated PDF file
    """
    # Create PDF document
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    story = []

    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )

    # Style for section titles (like "Orders in Complyt but not in WooCommerce")
    section_title_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Normal'],
        fontSize=13,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=8,
        spaceBefore=12,
        fontName='Helvetica-Bold',
        leading=16
    )

    normal_style = styles['Normal']
    normal_style.fontSize = 10
    normal_style.leading = 14

    # Title
    title = Paragraph("ORDER COMPARISON REPORT", title_style)
    story.append(title)
    story.append(Spacer(1, 0.2*inch))

    # Date range info
    if date_from and date_to:
        date_info = Paragraph(f"<b>Date Range:</b> {date_from} to {date_to}", normal_style)
        story.append(date_info)
        story.append(Spacer(1, 0.1*inch))

    report_date = Paragraph(
        f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        normal_style
    )
    story.append(report_date)
    story.append(Spacer(1, 0.3*inch))

    # Counts section
    complyt_order_count = len(complyt_data['invoices'])
    complyt_taxable_refund_count = len(complyt_data['taxable_refunds'])
    complyt_refund_count = len(complyt_data['refunds'])
    complyt_total_refund_count = complyt_taxable_refund_count + complyt_refund_count

    woo_order_count = len(woo_data['orders'])
    woo_refund_count = len(woo_data['refunds'])

    counts_heading = Paragraph("COUNTS", heading_style)
    story.append(counts_heading)

    # Create counts table
    counts_data = [
        ['Source', 'Orders', 'Taxable Refunds', 'Refunds', 'Total Refunds'],
        [
            'Complyt',
            str(complyt_order_count),
            str(complyt_taxable_refund_count),
            str(complyt_refund_count),
            str(complyt_total_refund_count)
        ],
        [
            'WooCommerce',
            str(woo_order_count),
            '-',
            str(woo_refund_count),
            str(woo_refund_count)
        ]
    ]

    counts_table = Table(counts_data, colWidths=[2*inch, 1*inch, 1.2*inch, 1*inch, 1.2*inch])
    counts_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
    ]))

    story.append(counts_table)
    story.append(Spacer(1, 0.4*inch))

    # Differences section
    differences_heading = Paragraph("DIFFERENCES", heading_style)
    story.append(differences_heading)

    # Find differences
    complyt_order_ids = set(complyt_data['invoices'])
    woo_order_ids = set(woo_data['orders'].keys())

    complyt_refund_ids = set(complyt_data['taxable_refunds'] + complyt_data['refunds'])
    woo_refund_ids = set(woo_data['refunds'].keys())

    # Check if any refund IDs are incorrectly in the orders dictionary and remove them
    refund_ids_in_orders = woo_order_ids & woo_refund_ids
    if refund_ids_in_orders:
        woo_order_ids = woo_order_ids - refund_ids_in_orders

    orders_in_complyt_not_woo = sorted(complyt_order_ids - woo_order_ids, key=lambda x: int(x) if x.isdigit() else 0)
    orders_in_woo_not_complyt = sorted(woo_order_ids - complyt_order_ids, key=lambda x: int(x) if x.isdigit() else 0)
    refunds_in_complyt_not_woo = sorted(complyt_refund_ids - woo_refund_ids, key=lambda x: int(x) if x.isdigit() else 0)
    refunds_in_woo_not_complyt = sorted(woo_refund_ids - complyt_refund_ids, key=lambda x: int(x) if x.isdigit() else 0)

    # Orders in Complyt but not in WooCommerce
    if orders_in_complyt_not_woo:
        story.append(Paragraph(
            f"Orders in Complyt but not in WooCommerce ({len(orders_in_complyt_not_woo)}):",
            section_title_style
        ))
        # Split into chunks for better formatting
        chunk_size = 10
        for i in range(0, len(orders_in_complyt_not_woo), chunk_size):
            chunk = orders_in_complyt_not_woo[i:i+chunk_size]
            ids_text = ', '.join(chunk)
            story.append(Paragraph(f"  {ids_text}", normal_style))
        story.append(Spacer(1, 0.15*inch))
    else:
        story.append(Paragraph(
            "Orders in Complyt but not in WooCommerce: None",
            section_title_style
        ))
        story.append(Spacer(1, 0.15*inch))

    # Orders in WooCommerce but not in Complyt
    if orders_in_woo_not_complyt:
        story.append(Paragraph(
            f"Orders in WooCommerce but not in Complyt ({len(orders_in_woo_not_complyt)}):",
            section_title_style
        ))
        chunk_size = 10
        for i in range(0, len(orders_in_woo_not_complyt), chunk_size):
            chunk = orders_in_woo_not_complyt[i:i+chunk_size]
            ids_text = ', '.join(chunk)
            story.append(Paragraph(f"  {ids_text}", normal_style))
        story.append(Spacer(1, 0.15*inch))
    else:
        story.append(Paragraph(
            "Orders in WooCommerce but not in Complyt: None",
            section_title_style
        ))
        story.append(Spacer(1, 0.15*inch))

    # Refunds in Complyt but not in WooCommerce
    if refunds_in_complyt_not_woo:
        story.append(Paragraph(
            f"Refunds in Complyt but not in WooCommerce ({len(refunds_in_complyt_not_woo)}):",
            section_title_style
        ))
        # Create table with Refund ID (Complyt doesn't have order IDs for refunds)
        refund_table_data = [['Refund ID']]
        for refund_id in refunds_in_complyt_not_woo:
            refund_table_data.append([refund_id])

        refund_table = Table(refund_table_data, colWidths=[2*inch])
        refund_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))
        story.append(refund_table)
        story.append(Spacer(1, 0.15*inch))
    else:
        story.append(Paragraph(
            "Refunds in Complyt but not in WooCommerce: None",
            section_title_style
        ))
        story.append(Spacer(1, 0.15*inch))

    # Refunds in WooCommerce but not in Complyt
    if refunds_in_woo_not_complyt:
        story.append(Paragraph(
            f"Refunds in WooCommerce but not in Complyt ({len(refunds_in_woo_not_complyt)}):",
            section_title_style
        ))
        # Create table with Refund ID and Order ID columns
        refund_table_data = [['Refund ID', 'Order ID']]
        for refund_id in refunds_in_woo_not_complyt:
            # Get order ID from refund data
            refund_data = woo_data['refunds'].get(refund_id, {})
            order_id = str(refund_data.get('order_id', 'N/A'))
            refund_table_data.append([refund_id, order_id])

        refund_table = Table(refund_table_data, colWidths=[1.5*inch, 1.5*inch])
        refund_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))
        story.append(refund_table)
        story.append(Spacer(1, 0.15*inch))
    else:
        story.append(Paragraph(
            "Refunds in WooCommerce but not in Complyt: None",
            section_title_style
        ))
        story.append(Spacer(1, 0.15*inch))

    # Build PDF
    try:
        doc.build(story)
        logger.info(f"PDF successfully generated at: {output_path}")
    except Exception as e:
        logger.error(f"Error building PDF: {str(e)}", exc_info=True)
        raise

    return output_path

