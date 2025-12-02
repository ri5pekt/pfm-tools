#!/usr/bin/env python3
"""
Verification script to check scheduled jobs after deployment.
Run this after deploying v1.3.0 to ensure scheduled jobs are still working.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.core.db import SessionLocal
from app.jobs.models import ScheduledExport
from rq_scheduler import Scheduler
from app.jobs.queues import get_redis_connection

def main():
    """Verify scheduled jobs are properly registered."""
    print("=" * 80)
    print("Scheduled Jobs Verification - v1.3.0")
    print("=" * 80)
    print()

    db = SessionLocal()
    try:
        # Get all enabled scheduled exports from database
        scheduled_exports = db.query(ScheduledExport).filter(
            ScheduledExport.enabled == True
        ).all()

        print(f"Found {len(scheduled_exports)} enabled scheduled export(s) in database:")
        print()

        if not scheduled_exports:
            print("⚠️  WARNING: No enabled scheduled exports found in database")
            print("   This may be normal if you don't use scheduled exports")
            return

        # Check Redis scheduler
        conn = get_redis_connection()
        scheduler = Scheduler(connection=conn)

        # Get all scheduled jobs from RQ Scheduler
        rq_jobs = scheduler.get_jobs()
        rq_job_ids = {job.id for job in rq_jobs}

        print("Database Scheduled Exports:")
        print("-" * 80)
        all_good = True

        for export in scheduled_exports:
            status = "✓" if export.rq_job_id and export.rq_job_id in rq_job_ids else "✗"
            if export.rq_job_id and export.rq_job_id not in rq_job_ids:
                all_good = False

            print(f"{status} ID {export.id}: {export.name}")
            print(f"    Feature: {export.feature}")
            print(f"    Schedule: Every {export.frequency} {export.period}(s)")
            print(f"    RQ Job ID: {export.rq_job_id or 'NOT REGISTERED'}")
            print(f"    Enabled: {export.enabled}")

            if export.rq_job_id:
                if export.rq_job_id in rq_job_ids:
                    try:
                        rq_job = scheduler.get_job(export.rq_job_id)
                        if rq_job:
                            print(f"    Next run: {rq_job.scheduled_time}")
                        else:
                            print(f"    ⚠️  RQ job not found (may need re-registration)")
                            all_good = False
                    except Exception as e:
                        print(f"    ⚠️  Error checking RQ job: {e}")
                        all_good = False
                else:
                    print(f"    ⚠️  RQ job ID not found in scheduler (needs re-registration)")
                    all_good = False
            else:
                print(f"    ⚠️  No RQ job ID stored (needs initial registration)")
                all_good = False

            print()

        print("RQ Scheduler Jobs:")
        print("-" * 80)
        if rq_jobs:
            for job in rq_jobs:
                print(f"  - {job.id}: Next run at {job.scheduled_time}")
        else:
            print("  No jobs found in RQ Scheduler")

        print()
        print("=" * 80)
        if all_good:
            print("✓ All scheduled jobs are properly registered!")
        else:
            print("⚠️  Some scheduled jobs need attention:")
            print("   - Restart the scheduler: docker-compose restart scheduler")
            print("   - Check scheduler logs: docker-compose logs scheduler")
        print("=" * 80)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

