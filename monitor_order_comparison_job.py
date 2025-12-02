#!/usr/bin/env python3
"""
Monitor Order Comparison job progress and status.
Shows real-time progress, errors, and job details.
"""
import sys
import os
import time
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.core.db import SessionLocal
from app.jobs.models import Job
from rq import Queue
from rq.job import Job as RQJob
from app.jobs.queues import get_redis_connection, get_default_queue


def format_time(seconds):
    """Format seconds into human-readable time."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds // 60:.0f}m {seconds % 60:.0f}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours:.0f}h {minutes:.0f}m"


def get_rq_job_status(db_job_id: int):
    """Get RQ job status for a database job ID."""
    try:
        queue = get_default_queue()
        conn = get_redis_connection()

        # Check queued jobs
        job_ids = queue.get_job_ids()
        for rq_job_id in job_ids:
            try:
                rq_job = RQJob.fetch(rq_job_id, connection=conn)
                if rq_job.args and len(rq_job.args) > 0 and rq_job.args[0] == db_job_id:
                    return {
                        'status': rq_job.get_status(),
                        'created_at': rq_job.created_at,
                        'started_at': rq_job.started_at,
                        'ended_at': rq_job.ended_at,
                        'exc_info': rq_job.exc_info,
                        'meta': rq_job.meta,
                    }
            except Exception:
                continue

        # Check started jobs
        started_registry = queue.started_job_registry
        for rq_job_id in started_registry.get_job_ids():
            try:
                rq_job = RQJob.fetch(rq_job_id, connection=conn)
                if rq_job.args and len(rq_job.args) > 0 and rq_job.args[0] == db_job_id:
                    return {
                        'status': rq_job.get_status(),
                        'created_at': rq_job.created_at,
                        'started_at': rq_job.started_at,
                        'ended_at': rq_job.ended_at,
                        'exc_info': rq_job.exc_info,
                        'meta': rq_job.meta,
                    }
            except Exception:
                continue

        # Check failed jobs
        failed_registry = queue.failed_job_registry
        for rq_job_id in failed_registry.get_job_ids():
            try:
                rq_job = RQJob.fetch(rq_job_id, connection=conn)
                if rq_job.args and len(rq_job.args) > 0 and rq_job.args[0] == db_job_id:
                    return {
                        'status': rq_job.get_status(),
                        'created_at': rq_job.created_at,
                        'started_at': rq_job.started_at,
                        'ended_at': rq_job.ended_at,
                        'exc_info': rq_job.exc_info,
                        'meta': rq_job.meta,
                    }
            except Exception:
                continue

        return None
    except Exception as e:
        return {'error': str(e)}


def display_job_info(job: Job, rq_status=None, watch_mode=False):
    """Display job information."""
    print("\n" + "=" * 80)
    print(f"Order Comparison Job #{job.id}")
    print("=" * 80)

    # Basic info
    print(f"Status: {job.status.upper()}")
    print(f"Created: {job.created_at}")
    print(f"Updated: {job.updated_at}")

    if job.input_filename:
        file_size = os.path.getsize(job.input_filename) if os.path.exists(job.input_filename) else 0
        file_size_mb = file_size / (1024 * 1024)
        print(f"Input File: {os.path.basename(job.input_filename)} ({file_size_mb:.2f} MB)")

    if job.output_filename:
        print(f"Output File: {os.path.basename(job.output_filename)}")

    # Options info
    if job.options:
        date_from = job.options.get('date_from', 'N/A')
        date_to = job.options.get('date_to', 'N/A')
        usa_only = job.options.get('usa_only', True)
        exclude_states = job.options.get('exclude_states', [])

        print(f"\nDate Range: {date_from} to {date_to}")
        print(f"USA Only: {usa_only}")
        if exclude_states:
            print(f"Exclude States: {', '.join(exclude_states)}")

    # Progress info
    if job.options:
        progress = job.options.get('progress', 0)
        status_message = job.options.get('status_message', '')

        print(f"\nProgress: {progress}%")
        if status_message:
            print(f"Status: {status_message}")
        else:
            if progress < 5:
                print(f"Status: Initializing...")
            elif progress < 10:
                print(f"Status: Parsing Complyt CSV...")
            elif progress < 98:
                print(f"Status: Fetching WooCommerce orders...")
            elif progress < 100:
                print(f"Status: Generating comparison report...")
            else:
                print(f"Status: Completed")

    # Error info
    if job.error_message:
        print("\n" + "-" * 80)
        print("ERROR MESSAGE:")
        print("-" * 80)
        print(job.error_message)
        print("-" * 80)

    # RQ status
    if rq_status:
        print("\n" + "-" * 80)
        print("RQ Job Status:")
        print("-" * 80)
        if 'error' in rq_status:
            print(f"Error getting RQ status: {rq_status['error']}")
        else:
            print(f"Status: {rq_status.get('status', 'unknown')}")
            if rq_status.get('created_at'):
                print(f"RQ Created: {rq_status['created_at']}")
            if rq_status.get('started_at'):
                print(f"RQ Started: {rq_status['started_at']}")
                if rq_status.get('started_at') and not rq_status.get('ended_at'):
                    runtime = (datetime.now(rq_status['started_at'].tzinfo) - rq_status['started_at']).total_seconds()
                    print(f"Runtime: {format_time(runtime)}")
            if rq_status.get('ended_at'):
                print(f"RQ Ended: {rq_status['ended_at']}")
            if rq_status.get('exc_info'):
                print(f"\nRQ Exception Info:")
                print(rq_status['exc_info'])

    print("=" * 80)

    if watch_mode and job.status in ['pending', 'running']:
        print("\nWatching for updates... (Press Ctrl+C to stop)")
    elif watch_mode:
        print(f"\nJob finished with status: {job.status}")
        return False

    return True


def main():
    """Main monitoring function."""
    import argparse

    parser = argparse.ArgumentParser(description='Monitor Order Comparison job')
    parser.add_argument('--job-id', type=int, help='Specific job ID to monitor')
    parser.add_argument('--watch', action='store_true', help='Watch mode: continuously monitor job')
    parser.add_argument('--interval', type=int, default=5, help='Update interval in seconds (default: 5)')
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # Get job
        if args.job_id:
            job = db.query(Job).filter(
                Job.id == args.job_id,
                Job.feature == "order_comparison"
            ).first()
            if not job:
                print(f"ERROR: Job #{args.job_id} not found")
                sys.exit(1)
        else:
            # Get most recent job
            job = db.query(Job).filter(
                Job.feature == "order_comparison"
            ).order_by(Job.created_at.desc()).first()

            if not job:
                print("ERROR: No Order Comparison jobs found")
                sys.exit(1)

        # Watch mode
        if args.watch:
            try:
                while True:
                    db.refresh(job)
                    rq_status = get_rq_job_status(job.id)
                    should_continue = display_job_info(job, rq_status, watch_mode=True)

                    if not should_continue:
                        break

                    time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\n\nMonitoring stopped by user")
        else:
            # Single check
            rq_status = get_rq_job_status(job.id)
            display_job_info(job, rq_status, watch_mode=False)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

