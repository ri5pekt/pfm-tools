from datetime import time as dt_time
from typing import Optional, List

from fastapi import HTTPException

TIME_REGEX = r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$"


def parse_time_string(time_str: str) -> dt_time:
    try:
        normalized = normalize_time_format(time_str)
        time_parts = normalized.split(":")
        return dt_time(int(time_parts[0]), int(time_parts[1]))
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid time format: {time_str}. Use HH:MM format.",
        )


def normalize_time_format(time_str: str) -> str:
    time_parts = time_str.strip().split(":")
    hour = int(time_parts[0])
    minute = int(time_parts[1]) if len(time_parts) > 1 else 0
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Invalid time")
    return f"{hour:02d}:{minute:02d}"


def normalize_times(times: Optional[list] = None, time_str: Optional[str] = None) -> List[str]:
    """Normalize and dedupe daily run times."""
    import re

    result = []
    seen = set()

    for value in (times or []):
        if not value:
            continue
        try:
            normalized = normalize_time_format(str(value))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid time format: {value}. Use HH:MM format.")
        if not re.match(TIME_REGEX, normalized):
            raise HTTPException(status_code=400, detail=f"Invalid time format: {value}. Use HH:MM format.")
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    if time_str:
        try:
            normalized = normalize_time_format(time_str)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid time format: {time_str}. Use HH:MM format.")
        if normalized not in seen:
            result.append(normalized)

    return sorted(result)


def get_alert_daily_times(alert) -> List[str]:
    """Return daily run times from alert config."""
    if alert.times:
        return normalize_times(times=alert.times)
    if alert.time:
        return [alert.time.strftime("%H:%M")]
    return []


def validate_schedule_fields(
    period: str,
    frequency: int,
    time_str: Optional[str] = None,
    day_of_week: Optional[int] = None,
    day_of_month: Optional[int] = None,
    times: Optional[list] = None,
) -> None:
    if frequency < 1:
        raise HTTPException(status_code=400, detail="frequency must be at least 1")

    if period == "minute":
        return
    if period == "weekly":
        if day_of_week is None:
            raise HTTPException(status_code=400, detail="day_of_week is required for weekly period")
        if time_str is None:
            raise HTTPException(status_code=400, detail="time is required for weekly period")
    elif period == "monthly":
        if day_of_month is None:
            raise HTTPException(status_code=400, detail="day_of_month is required for monthly period")
        if time_str is None:
            raise HTTPException(status_code=400, detail="time is required for monthly period")
    elif period == "daily":
        daily_times = normalize_times(times=times, time_str=time_str)
        if not daily_times:
            raise HTTPException(
                status_code=400,
                detail="At least one time is required for daily period (use times or time)",
            )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown period: {period}")


def validate_slack_webhook_url(url: str) -> None:
    if not url or not url.strip().startswith("https://hooks.slack.com/"):
        raise HTTPException(
            status_code=400,
            detail="Slack Webhook URL must start with https://hooks.slack.com/",
        )


def normalize_excluded_skus(excluded_skus: Optional[list]) -> list:
    if not excluded_skus:
        return []
    return [str(sku).strip() for sku in excluded_skus if sku and str(sku).strip()]


def get_alert_rq_job_ids(alert) -> List[str]:
    job_ids = list(alert.rq_job_ids or [])
    if alert.rq_job_id and alert.rq_job_id not in job_ids:
        job_ids.append(alert.rq_job_id)
    return job_ids


def get_alert_thresholds(alert) -> tuple:
    """Return (klb_threshold, shipbob_threshold) with legacy fallback."""
    fallback = alert.threshold if alert.threshold is not None else 0
    klb = alert.klb_threshold if alert.klb_threshold is not None else fallback
    shipbob = alert.shipbob_threshold if alert.shipbob_threshold is not None else fallback
    return klb, shipbob


def resolve_thresholds(
    threshold: Optional[int] = None,
    klb_threshold: Optional[int] = None,
    shipbob_threshold: Optional[int] = None,
) -> tuple:
    """Resolve thresholds from request fields."""
    if klb_threshold is not None and shipbob_threshold is not None:
        return klb_threshold, shipbob_threshold

    if klb_threshold is not None and shipbob_threshold is None:
        if threshold is not None:
            return klb_threshold, threshold
        raise HTTPException(status_code=400, detail="shipbob_threshold is required when klb_threshold is set alone")

    if shipbob_threshold is not None and klb_threshold is None:
        if threshold is not None:
            return threshold, shipbob_threshold
        raise HTTPException(status_code=400, detail="klb_threshold is required when shipbob_threshold is set alone")

    if threshold is not None:
        return threshold, threshold

    raise HTTPException(
        status_code=400,
        detail="klb_threshold and shipbob_threshold are required (or provide threshold for both)",
    )


def validate_thresholds(klb_threshold: int, shipbob_threshold: int) -> None:
    if klb_threshold < 0 or shipbob_threshold < 0:
        raise HTTPException(status_code=400, detail="thresholds must be 0 or greater")


def low_stock_alert_to_dict(alert) -> dict:
    daily_times = get_alert_daily_times(alert) if alert.period == "daily" else []
    job_ids = get_alert_rq_job_ids(alert)
    klb_threshold, shipbob_threshold = get_alert_thresholds(alert)

    return {
        "id": alert.id,
        "feature": alert.feature,
        "name": alert.name,
        "period": alert.period,
        "frequency": alert.frequency if alert.frequency else 1,
        "time": alert.time.strftime("%H:%M") if alert.time else None,
        "times": daily_times if alert.period == "daily" else (alert.times or []),
        "day_of_week": alert.day_of_week,
        "day_of_month": alert.day_of_month,
        "timezone": alert.timezone,
        "enabled": alert.enabled,
        "rq_job_id": job_ids[0] if job_ids else alert.rq_job_id,
        "rq_job_ids": job_ids,
        "threshold": alert.threshold,
        "klb_threshold": klb_threshold,
        "shipbob_threshold": shipbob_threshold,
        "slack_webhook_url": alert.slack_webhook_url,
        "excluded_skus": alert.excluded_skus or [],
        "created_at": alert.created_at,
        "updated_at": alert.updated_at,
    }
