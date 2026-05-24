import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def send_slack_webhook(webhook_url: str, text: str, blocks: Optional[list] = None) -> bool:
    """
    Send a message to a Slack incoming webhook URL.

    Returns True if successful, False otherwise.
    """
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks

    try:
        response = requests.post(webhook_url, json=payload, timeout=15)
        response.raise_for_status()
        logger.info("Successfully sent Slack notification")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Slack notification: {str(e)}")
        return False
