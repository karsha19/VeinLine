from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SMSDeliveryError(Exception):
    pass


def send_sms(phone_e164: str, message: str) -> dict:
    """
    Sends an SMS using the configured provider.

    This contains real HTTP calls, but requires a valid API key in `.env`.
    In development, you can keep the key empty; the function will log and no-op.
    """

    api_key = getattr(settings, "VEINLINE_SMS_API_KEY", "")
    provider = getattr(settings, "VEINLINE_SMS_PROVIDER", "fast2sms")

    if not api_key:
        logger.warning("SMS not sent (missing SMS_API_KEY). To enable, set SMS_API_KEY in .env.")
        return {"ok": False, "skipped": True, "reason": "missing_api_key"}

    if provider == "fast2sms":
        # Fast2SMS quick send endpoint (example; verify params per your Fast2SMS plan)
        url = "https://www.fast2sms.com/dev/bulkV2"
        headers = {"authorization": api_key}
        payload = {
            "route": "v3",
            "numbers": phone_e164.lstrip("+"),  # Fast2SMS typically expects digits without '+'
            "message": message,
            "sender_id": getattr(settings, "VEINLINE_SMS_SENDER", "VEINLN"),
        }
        resp = requests.post(url, data=payload, headers=headers, timeout=20)
    elif provider == "textlocal":
        # Textlocal API
        url = "https://api.textlocal.in/send/"
        payload = {
            "apikey": api_key,
            "numbers": phone_e164.lstrip("+"),
            "message": message,
            "sender": getattr(settings, "VEINLINE_SMS_SENDER", "VEINLN"),
        }
        resp = requests.post(url, data=payload, timeout=20)
    else:
        raise SMSDeliveryError(f"Unsupported SMS_PROVIDER: {provider}")

    if resp.status_code >= 400:
        raise SMSDeliveryError(f"SMS provider error {resp.status_code}: {resp.text[:300]}")

    try:
        return {"ok": True, "provider": provider, "response": resp.json()}
    except Exception:
        return {"ok": True, "provider": provider, "response_text": resp.text}


