#!/usr/bin/env python3
"""Compare order IDs between our export and Metorik export."""

import csv
import sys

def extract_order_ids_from_metorik(csv_path):
    """Extract order IDs from Metorik CSV (first column)."""
    order_ids = set()
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        for row in reader:
            if row and row[0].strip().isdigit():
                order_ids.add(row[0].strip())
    return order_ids

def extract_order_ids_from_our_export(csv_path):
    """Extract order IDs from our export CSV (Order IDs column)."""
    order_ids = set()
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)

        # Find the Order IDs column index
        try:
            order_ids_col_idx = headers.index('Order IDs')
        except ValueError:
            print("Error: 'Order IDs' column not found in our export CSV")
            return order_ids

        for row in reader:
            if len(row) > order_ids_col_idx and row[order_ids_col_idx]:
                # Split comma-separated order IDs
                ids_str = row[order_ids_col_idx].strip()
                if ids_str:
                    ids = [id.strip() for id in ids_str.split(',') if id.strip().isdigit()]
                    order_ids.update(ids)

    return order_ids

def main():
    metorik_csv = 'orders-export/metorik-export.csv'
    # Use the CSV file in orders-export folder
    import os
    our_csv = None

    # Check for CSV files in orders-export folder
    orders_export_dir = 'orders-export'
    if os.path.exists(orders_export_dir):
        csv_files = [f for f in os.listdir(orders_export_dir) if f.endswith('.csv') and 'daily_orders_export' in f]
        if csv_files:
            # Use the most recent one (by filename)
            csv_files.sort(reverse=True)
            our_csv = os.path.join(orders_export_dir, csv_files[0])
            print(f"Using export file: {our_csv}")

    if not our_csv or not os.path.exists(our_csv):
        print("Error: Could not find our export CSV file in orders-export folder")
        sys.exit(1)

    print("Extracting order IDs from Metorik export...")
    metorik_ids = extract_order_ids_from_metorik(metorik_csv)
    print(f"Metorik: {len(metorik_ids)} order IDs")
    print(f"  Range: {min(metorik_ids)} to {max(metorik_ids)}")

    print("\nExtracting order IDs from our export...")
    our_ids = extract_order_ids_from_our_export(our_csv)
    print(f"Our export: {len(our_ids)} order IDs")
    if our_ids:
        print(f"  Range: {min(our_ids)} to {max(our_ids)}")

    print("\n" + "="*60)
    print("COMPARISON RESULTS")
    print("="*60)

    # Find missing IDs
    missing_in_ours = metorik_ids - our_ids
    extra_in_ours = our_ids - metorik_ids

    print(f"\nMissing in our export (in Metorik but not in ours): {len(missing_in_ours)}")
    if missing_in_ours:
        sorted_missing = sorted([int(id) for id in missing_in_ours])
        print(f"  First 20: {sorted_missing[:20]}")
        print(f"  Last 20: {sorted_missing[-20:]}")
        print(f"  Full list: {sorted_missing}")

    print(f"\nExtra in our export (in ours but not in Metorik): {len(extra_in_ours)}")
    if extra_in_ours:
        sorted_extra = sorted([int(id) for id in extra_in_ours])
        print(f"  List: {sorted_extra}")

    # Save missing IDs to a file
    if missing_in_ours:
        missing_file = 'orders-export/missing_order_ids.txt'
        with open(missing_file, 'w') as f:
            for order_id in sorted([int(id) for id in missing_in_ours]):
                f.write(f"{order_id}\n")
        print(f"\nSaved missing order IDs to: {missing_file}")

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Metorik total: {len(metorik_ids)}")
    print(f"Our export total: {len(our_ids)}")
    print(f"Difference: {len(metorik_ids) - len(our_ids)}")
    print(f"Match rate: {len(metorik_ids & our_ids) / len(metorik_ids) * 100:.2f}%")

if __name__ == '__main__':
    main()

