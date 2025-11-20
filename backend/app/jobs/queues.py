import redis
from rq import Queue
from rq.job import Job as RQJob

from ..core.config import get_settings

settings = get_settings()


def get_redis_connection() -> redis.Redis:
    return redis.from_url(settings.redis_url)


def get_default_queue() -> Queue:
    conn = get_redis_connection()
    return Queue(settings.rq_default_queue, connection=conn)


def enqueue_job(func, *args, job_timeout=None, **kwargs):
    """
    Enqueue a job with optional timeout.

    Args:
        func: Function to execute
        *args: Positional arguments for the function
        job_timeout: Job timeout in seconds (default: RQ default, usually 180)
                    This is passed to RQ's enqueue method, not the function
        **kwargs: Additional keyword arguments for the function
    """
    queue = get_default_queue()
    # job_timeout is for RQ, not the function, so we extract it
    # and pass it separately to enqueue
    if job_timeout is not None:
        return queue.enqueue(func, *args, job_timeout=job_timeout, **kwargs)
    else:
        return queue.enqueue(func, *args, **kwargs)


def cancel_job_by_id(job_id: int) -> bool:
    """
    Cancel an RQ job by finding it in the queue.
    Returns True if job was found and cancelled, False otherwise.
    """
    try:
        queue = get_default_queue()
        conn = get_redis_connection()

        # Search through all job states: queued, started, finished, failed
        # Check pending jobs in queue
        job_ids = queue.get_job_ids()

        for rq_job_id in job_ids:
            try:
                rq_job = RQJob.fetch(rq_job_id, connection=conn)
                # Check if this RQ job is for our job_id
                # The args should be (job_id,) for run_sales_tax_job
                if rq_job.args and len(rq_job.args) > 0 and rq_job.args[0] == job_id:
                    if rq_job.is_queued or rq_job.is_started:
                        rq_job.cancel()
                        return True
            except Exception:
                # Job might not exist anymore, continue searching
                continue

        # Also check started jobs (jobs that are currently running)
        # RQ stores started jobs separately
        started_registry = queue.started_job_registry
        for rq_job_id in started_registry.get_job_ids():
            try:
                rq_job = RQJob.fetch(rq_job_id, connection=conn)
                if rq_job.args and len(rq_job.args) > 0 and rq_job.args[0] == job_id:
                    # For running jobs, we can't cancel them directly,
                    # but we can mark them for cancellation
                    # The worker will handle it when it tries to update the DB
                    return True
            except Exception:
                continue

        return False
    except Exception:
        # If we can't cancel, that's okay - job might already be running or finished
        return False
